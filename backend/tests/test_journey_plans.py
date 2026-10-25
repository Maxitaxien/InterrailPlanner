"""Synthetic journeys only: no provider, dotenv or credential access in these tests."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from app.models.integrations import RailJourneySnapshot
from app.providers.motis import MotisTimetables
from app.schemas.trips import TripRequest
from app.services.errors import PlanningError
from app.services.journey_plans import leg_keys, timing
from app.services.route_engine.graph import RailGraph
from app.services.scheduler import schedule


def synthetic_journey(departure='2027-06-01T22:00:00+02:00', arrival='2027-06-02T06:00:00+02:00'):
    return {'departure': departure, 'arrival': arrival, 'duration_minutes': 480, 'transfers': 0,
            'legs': [{'mode': 'NIGHT_RAIL', 'origin': 'Synthetic A', 'destination': 'Synthetic B',
                'departure': departure, 'arrival': arrival, 'origin_timezone': 'Europe/Oslo',
                'destination_timezone': 'Europe/Prague', 'operator': 'Synthetic operator',
                'train': 'Synthetic night service', 'real_time': False, 'stay_seated': False}]}


def saved(client):
    trip = client.post('/api/v1/trips', json={'total_days': 21, 'date_mode': 'exact', 'start_date': '2027-06-01', 'required_stops': ['prague', 'venice']}).json()
    headers = {'X-Edit-Token': trip['edit_token']}
    route = client.post(f"/api/v1/trips/{trip['id']}/generate", headers=headers).json()[0]
    return trip, headers, route


def research(client, monkeypatch, leg, journey=None):
    async def fake_search(self, request, origin, destination):
        return {'status': 'scheduled', 'journeys': [journey or synthetic_journey()],
                'prepared_sources': [], 'notice': 'Synthetic fixture; not a real train', 'checked_at': datetime.now(timezone.utc).isoformat()}
    monkeypatch.setattr(MotisTimetables, 'search', fake_search)
    response = client.post('/api/v1/travel/rail/timetables', json={'origin_id': leg['origin_id'], 'destination_id': leg['destination_id'], 'departure_date': '2027-06-01'})
    assert response.status_code == 200, response.text
    return response.json()['journeys'][0]['selection_id']


def edit(client, headers, route, operation, index=0, **fields):
    return client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers, json={
        'expected_revision': route['revision'], 'operation': operation,
        'destination_id': route['legs'][index]['origin_id'], 'leg_index': index, **fields})


def test_overnight_intent_is_persistent_separate_from_booking_and_reversible(client):
    trip, headers, route = saved(client)
    response = edit(client, headers, route, 'set_leg_plan', index=1)
    assert response.status_code == 200, response.text
    result = response.json()
    leg = result['legs'][1]
    assert leg['travel_plan']['kind'] == 'overnight_intent'
    assert leg['travel_nights_estimate'] >= 1 and leg['travel_plan']['needs_recheck']
    assert leg['travel_days_estimate'] == 1 + leg['travel_nights_estimate']
    assert result['stay_nights'] + result['transit_nights_estimate'] == 20
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()
    assert next(r for r in reopened['itineraries'] if r['id'] == route['id']) == result
    cleared = edit(client, headers, result, 'clear_leg_plan', index=1)
    assert cleared.status_code == 200, cleared.text
    assert not cleared.json()['journey_plans']
    assert 'travel_plan' not in cleared.json()['legs'][1]


def test_chosen_server_snapshot_updates_calendar_persists_and_pins_departure(client, monkeypatch, session):
    trip, headers, route = saved(client)
    selection = research(client, monkeypatch, route['legs'][0])
    assert session.get(RailJourneySnapshot, selection)
    response = edit(client, headers, route, 'set_journey', journey_id=selection)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['legs'][0]['estimated_minutes'] == 480
    assert result['legs'][0]['travel_nights_estimate'] == 1
    assert result['legs'][0]['travel_days_estimate'] == 1
    assert result['stops'][1]['arrival_date'] == '2027-06-02'
    assert result['legs'][0]['travel_plan']['reservation_status'] == 'unknown'
    assert result['legs'][0]['travel_plan']['price'] is None
    assert result['stay_nights'] + result['transit_nights_estimate'] == 20
    # A trip-length edit retains the actual selected departure rather than shifting it.
    changed = client.patch(f"/api/v1/trips/{trip['id']}", headers=headers, json={'expected_revision': 1, 'total_days': 22})
    assert changed.status_code == 200, changed.text
    updated = next(r for r in changed.json()['itineraries'] if r['id'] == route['id'])
    assert updated['legs'][0]['travel_plan']['journey']['departure'] == synthetic_journey()['departure']
    assert updated['stops'][1]['arrival_date'] == '2027-06-02'
    # Date changes cannot quietly carry an old departure onto another holiday.
    conflict = client.patch(f"/api/v1/trips/{trip['id']}", headers=headers, json={'expected_revision': 2, 'start_date': '2027-07-01'})
    assert conflict.status_code == 422
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()
    assert reopened['revision'] == 2


def test_snapshot_freshness_is_recomputed_without_fetching_or_erasing_saved_plan(client, monkeypatch, session):
    trip, headers, route = saved(client)
    selection = research(client, monkeypatch, route['legs'][0])
    snapshot = session.get(RailJourneySnapshot, selection)
    snapshot.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.commit()
    expired = edit(client, headers, route, 'set_journey', journey_id=selection)
    assert expired.status_code == 422 and expired.json()['error']['code'] == 'JOURNEY_EXPIRED'
    snapshot.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    session.commit()
    result = edit(client, headers, route, 'set_journey', journey_id=selection).json()
    from app.services.journey_plans import annotate_plans
    result['legs'][0]['travel_plan']['recheck_after'] = '2020-01-01T00:00:00+00:00'
    annotated = annotate_plans(result)
    assert annotated['legs'][0]['travel_plan']['needs_recheck']
    assert result['legs'][0]['travel_plan']['needs_recheck'] is False


def test_selection_requires_auth_revision_city_pair_and_server_owned_snapshot(client, monkeypatch):
    _, headers, route = saved(client)
    selection = research(client, monkeypatch, route['legs'][0])
    assert edit(client, {}, route, 'set_journey', journey_id=selection).status_code == 401
    mismatch = edit(client, headers, route, 'set_journey', index=1, journey_id=selection)
    assert mismatch.status_code == 422 and mismatch.json()['error']['code'] == 'JOURNEY_MISMATCH'
    missing = edit(client, headers, route, 'set_journey', journey_id='00000000-0000-0000-0000-000000000000')
    assert missing.status_code == 422
    assert edit(client, headers, route, 'set_journey', journey_id=selection, journey={'invented': True}).status_code == 422
    changed = edit(client, headers, route, 'set_leg_plan')
    assert changed.status_code == 200
    assert edit(client, headers, route, 'clear_leg_plan').status_code == 409


def test_flexible_dates_allow_intention_but_not_dated_selection(client, monkeypatch):
    trip = client.post('/api/v1/trips', json={'required_stops': ['prague', 'venice']}).json()
    headers = {'X-Edit-Token': trip['edit_token']}
    route = client.post(f"/api/v1/trips/{trip['id']}/generate", headers=headers).json()[0]
    selection = research(client, monkeypatch, route['legs'][0])
    assert edit(client, headers, route, 'set_journey', journey_id=selection).json()['error']['code'] == 'DATES_REQUIRED'
    assert edit(client, headers, route, 'set_leg_plan').status_code == 200


def tiny_schedule(session, journey, **pass_fields):
    rail = RailGraph(session).daytime()
    rail.graph = rail.graph.copy()
    rail.graph.add_edge('oslo', 'bari', key='synthetic', minutes=60, mode='rail', night_train=False)
    request = TripRequest.model_validate({'total_days': 7, 'start_date': '2027-06-01', 'date_mode': 'exact', 'preferences': {'endpoint_id': 'bari', 'final_stay_nights': 4}, 'pass': {'travel_days_total': 1, **pass_fields}})
    plan = {'kind': 'timetable', 'journey': journey, 'recheck_after': '2027-06-02T12:00:00+00:00'}
    return schedule(['oslo', 'bari'], request, rail, journey_plans={leg_keys(['oslo', 'bari'])[0]: plan})


def test_through_train_uses_departure_day_but_pass_must_cover_arrival(session):
    result = tiny_schedule(session, synthetic_journey(), valid_until='2027-06-02')
    assert result['travel_days_estimate'] == 1
    assert result['stops'][-1]['arrival_date'] == '2027-06-02'
    with pytest.raises(PlanningError) as caught:
        tiny_schedule(session, synthetic_journey(), valid_until='2027-06-01')
    assert caught.value.code == 'PASS_INCOMPATIBLE'


def test_change_after_midnight_counts_another_pass_day(session):
    journey = synthetic_journey()
    first = {**journey['legs'][0], 'arrival': '2027-06-01T23:50:00+02:00'}
    second = {**journey['legs'][0], 'departure': '2027-06-02T00:20:00+02:00', 'origin_timezone': 'Europe/Prague'}
    journey['legs'] = [first, second]
    assert len(timing(journey, 'NO', 'IT')['boarding_dates']) == 2
    with pytest.raises(PlanningError) as caught:
        tiny_schedule(session, journey)
    assert caught.value.code == 'PASS_LIMIT_EXCEEDED'
    assert tiny_schedule(session, journey, travel_days_total=2)['travel_days_estimate'] == 2


def test_access_walk_before_midnight_does_not_consume_a_rail_pass_day(session):
    journey = synthetic_journey('2027-06-01T23:50:00+02:00', '2027-06-02T06:00:00+02:00')
    rail = {**journey['legs'][0], 'departure': '2027-06-02T00:20:00+02:00'}
    walk = {**journey['legs'][0], 'mode': 'WALK', 'arrival': rail['departure']}
    journey['legs'] = [walk, rail]
    result = tiny_schedule(session, journey, valid_from='2027-06-02', valid_until='2027-06-02')
    assert result['travel_days_estimate'] == 1
    assert result['legs'][0]['pass_day_offsets'] == [1]


def test_malformed_timing_is_not_selectable():
    journey = synthetic_journey()
    journey['legs'][0]['arrival'] = '2027-06-01T20:00:00+02:00'
    with pytest.raises(PlanningError):
        timing(journey, 'NO', 'CZ')


def test_later_departure_is_pinned_and_split_corridor_drops_old_plan(client, monkeypatch):
    trip, headers, route = saved(client)
    day = date.fromisoformat(route['stops'][1]['departure_date'])
    journey = synthetic_journey(f'{day}T22:00:00+02:00', f'{day + timedelta(days=1)}T06:00:00+02:00')
    selection = research(client, monkeypatch, route['legs'][1], journey)
    response = edit(client, headers, route, 'set_journey', index=1, journey_id=selection)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['stops'][1]['departure_date'] == day.isoformat()
    changed = client.patch(f"/api/v1/trips/{trip['id']}", headers=headers, json={'expected_revision': 1, 'total_days': 24})
    assert changed.status_code == 200, changed.text
    result = next(r for r in changed.json()['itineraries'] if r['id'] == route['id'])
    assert result['stops'][1]['departure_date'] == day.isoformat()
    # A city insertion changes the pair; never attach the old train to a new pair.
    first = edit(client, headers, result, 'set_leg_plan')
    assert first.status_code == 200, first.text
    result = first.json()
    split = client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers, json={'expected_revision': result['revision'], 'operation': 'add_stop', 'destination_id': 'copenhagen', 'position': 1})
    assert split.status_code == 200, split.text
    assert not any(p['kind'] == 'overnight_intent' for p in split.json()['journey_plans'].values())
    assert any('travel plan was cleared' in w for w in split.json()['warnings'])


def test_locked_arrival_does_not_move_when_adding_overnight_intention(client):
    _, headers, route = saved(client)
    locked = client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers, json={'expected_revision': 1, 'operation': 'lock_stop', 'destination_id': route['stops'][2]['destination_id'], 'locked': True})
    assert locked.status_code == 200, locked.text
    result = edit(client, headers, locked.json(), 'set_leg_plan', index=1)
    if result.status_code == 200:
        old = locked.json()['stops'][2]
        new = result.json()['stops'][2]
        assert (old['arrival_day'], old['departure_day']) == (new['arrival_day'], new['departure_day'])
    else:
        assert result.json()['error']['code'] in {'LOCKED_SCHEDULE_CONFLICT', 'LOCKED_DURATION_CONFLICT'}
        assert client.get(f"/api/v1/trips/{route['trip_id']}/itineraries").json()[0] == locked.json()


def test_same_day_saved_connection_cannot_depart_before_arrival(session):
    rail = RailGraph(session).daytime()
    rail.graph = rail.graph.copy()
    for a, b in [('oslo', 'prague'), ('prague', 'bari')]:
        rail.graph.add_edge(a, b, key='synthetic', minutes=60, mode='rail', night_train=False)
    request = TripRequest.model_validate({'total_days': 7, 'required_stops': ['prague'], 'start_date': '2027-06-01', 'date_mode': 'exact', 'preferences': {'final_stay_nights': 4}, 'pass': {'travel_days_total': 7}})
    journeys = [synthetic_journey(), synthetic_journey('2027-06-02T05:00:00+02:00', '2027-06-02T07:00:00+02:00')]
    plans = {key: {'kind': 'timetable', 'journey': journey} for key, journey in zip(leg_keys(['oslo', 'prague', 'bari']), journeys)}
    with pytest.raises(PlanningError) as caught:
        schedule(['oslo', 'prague', 'bari'], request, rail, {'prague': 0}, journey_plans=plans)
    assert caught.value.code == 'JOURNEY_CONNECTION_CONFLICT'
