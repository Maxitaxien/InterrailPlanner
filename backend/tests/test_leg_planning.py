import json
from pathlib import Path
from sqlalchemy import select
from app.models.entities import Itinerary, TripStop
from app.schemas.trips import TripRequest
from app.services.route_engine.graph import RailGraph
from app.services.route_engine.generator import generate


def saved(client, **extra):
    trip = client.post('/api/v1/trips', json={'total_days': 28, 'required_stops': ['prague', 'venice'], 'preferences': {'endpoint_id': 'bari'}, 'pass': {'travel_days_total': 15}, **extra}).json()
    headers = {'X-Edit-Token': trip['edit_token']}
    response = client.post(f"/api/v1/trips/{trip['id']}/generate", headers=headers)
    assert response.status_code == 200, response.text
    return trip, headers, response.json()[0]


def test_stop_ideas_include_split_stay_and_preview_without_writes(client):
    trip, _, route = saved(client)
    before = client.get(f"/api/v1/trips/{trip['id']}").json()
    response = client.get(f"/api/v1/itineraries/{route['id']}/legs/0/stop-suggestions")
    assert response.status_code == 200
    ideas = response.json()['suggestions']
    assert ideas and any(idea['can_add'] for idea in ideas)
    for idea in ideas:
        assert idea['before_minutes'] > 0 and idea['after_minutes'] > 0
        assert idea['suggested_nights'] > 0 and idea['reason']
        assert idea['destination_id'] not in {stop['destination_id'] for stop in route['stops']}
        if idea['can_add']:
            assert idea['planned_nights'] > 0 and idea['extra_pass_days'] is not None
    assert client.get(f"/api/v1/trips/{trip['id']}").json() == before
    assert client.get(f"/api/v1/itineraries/{route['id']}/legs/999/stop-suggestions").status_code == 404


def test_stop_preview_reports_calendar_constraints(client):
    trip, headers, route = saved(client, total_days=7, preferences={'endpoint_id': 'bari', 'final_stay_nights': 4})
    response = client.get(f"/api/v1/itineraries/{route['id']}/legs/0/stop-suggestions")
    assert any(not idea['can_add'] and idea['limitation'] for idea in response.json()['suggestions'])


def test_required_removal_is_explicit_revision_checked_and_updates_other_alternatives(client, session):
    trip, headers, route = saved(client)
    url = f"/api/v1/itineraries/{route['id']}"
    action = {'operation': 'remove_stop', 'destination_id': 'prague', 'expected_revision': 1, 'remove_required': True, 'expected_trip_revision': 1}
    assert client.patch(url, json=action).status_code == 401
    assert client.patch(url, headers=headers, json={**action, 'expected_trip_revision': 99}).status_code == 409
    assert client.patch(url, headers=headers, json={k:v for k,v in action.items() if k != 'expected_trip_revision'}).status_code == 422
    response = client.patch(url, headers=headers, json=action)
    assert response.status_code == 200, response.text
    assert response.json()['trip_revision'] == 2
    assert 'prague' not in {stop['destination_id'] for stop in response.json()['stops']}
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()
    assert reopened['request']['required_stops'] == ['venice']
    assert all(not stop['is_required'] for r in reopened['itineraries'] for stop in r['stops'] if stop['destination_id'] == 'prague')
    assert not any(stop.is_required for stop in session.scalars(select(TripStop).where(TripStop.destination_id == 'prague')).all())
    assert client.patch(url, headers=headers, json=action).status_code == 409


def test_failed_required_removal_preserves_request_and_routes(client):
    trip, headers, route = saved(client)
    url = f"/api/v1/itineraries/{route['id']}"
    locked = client.patch(url, headers=headers, json={'operation': 'lock_stop', 'destination_id': 'prague', 'locked': True, 'expected_revision': 1})
    assert locked.status_code == 200
    before = client.get(f"/api/v1/trips/{trip['id']}").json()
    response = client.patch(url, headers=headers, json={'operation': 'remove_stop', 'destination_id': 'prague', 'expected_revision': 2, 'remove_required': True, 'expected_trip_revision': 1})
    assert response.status_code == 422
    assert client.get(f"/api/v1/trips/{trip['id']}").json() == before


def test_all_island_endpoints_have_explicit_feasible_terminal_corridors(session):
    islands = json.loads((Path(__file__).resolve().parents[1]/'data/island_endpoints.json').read_text())
    coastal = json.loads((Path(__file__).resolve().parents[1]/'data/coastal_expansion.json').read_text())
    islands += [city for city in coastal['destinations'] if city['category'] == 'island']
    assert len(islands) == 25
    rail = RailGraph(session)
    for island in islands:
        request = TripRequest.model_validate({'total_days': 35, 'required_stops': ['prague', 'venice'], 'preferences': {'endpoint_id': island['id']}, 'pass': {'travel_days_total': 15}})
        route = generate(request, rail)[0]
        assert route['endpoint_id'] == island['id']
        assert route['legs'][-1]['mode'] == 'ferry_transfer'
        assert route['legs'][-1]['travel_days_estimate'] == 0
        assert route['stops'][-1]['nights'] == 4
        assert route['stay_nights'] + route['transit_nights_estimate'] == 34


def test_greek_island_tail_can_be_edited_and_changed_back_to_italy(client):
    trip, headers, route = saved(client, preferences={'endpoint_id': 'naxos'})
    url = f"/api/v1/itineraries/{route['id']}"
    assert [leg['mode'] for leg in route['legs']][-2:] == ['ferry_transfer', 'ferry_transfer']
    response = client.patch(url, headers=headers, json={'operation': 'set_nights', 'destination_id': 'prague', 'nights': 4, 'expected_revision': 1})
    assert response.status_code == 200, response.text
    changed = client.patch(url, headers=headers, json={'operation': 'change_endpoint', 'destination_id': 'capri', 'expected_revision': 2})
    assert changed.status_code == 200, changed.text
    assert changed.json()['endpoint_id'] == 'capri'
    assert 'athens' not in {s['destination_id'] for s in changed.json()['stops']}


def test_islands_region_only_returns_islands(client):
    _, _, route = saved(client, preferences={'endpoint_region': 'islands'})
    assert route['endpoint_id'] in {'corfu','naxos','paros','santorini','crete','syros','milos','sicily','sardinia','capri','ischia','procida','corsica','hvar','vis','brac','korcula','lefkada','kefalonia','zakynthos','lipari','elba','paxos','ithaca','meganisi'}
