from copy import deepcopy
from datetime import datetime
import json

import httpx
import pytest
from sqlalchemy import func, select

from app.models.entities import Destination, Itinerary, Trip
from app.models.integrations import RailJourneySnapshot
from app.schemas.integrations import EndpointComparisonRequest
from app.services.endpoint_comparison import compare_endpoints
from app.services.endpoint_transfers import endpoint_transfers
from app.services.route_engine.graph import RailGraph


def compare(client, ids, origin='bari'):
    return client.post('/api/v1/travel/endpoints/compare', json={'origin_id': origin, 'endpoint_ids': ids})


def test_corfu_crete_and_lefkada_show_real_model_differences(client, session, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('Local comparisons cannot call providers')
    monkeypatch.setattr(httpx.AsyncClient, 'stream', forbidden)
    result = compare(client, ['corfu', 'crete', 'lefkada', 'capri', 'cefalu']).json()
    assert result['origin_id'] == 'bari'
    corfu, crete, lefkada, capri, cefalu = result['comparisons']
    assert corfu['ferry_crossings'] == 1 and crete['ferry_crossings'] == 2
    assert crete['estimated_minutes'] > corfu['estimated_minutes']
    assert crete['transit_nights_lower_bound'] >= 2
    assert lefkada['ferry_crossings'] == 1 and lefkada['onward_ground_legs'] == 1
    assert 'Igoumenitsa' in lefkada['route_names']
    assert lefkada['airport_access']['airport'] == 'PVK'
    assert capri['airport_access']['airport'] == 'NAP' and capri['airport_access']['ferry_crossings'] == 1
    assert cefalu['breakdown_minutes']['rail'] > 0 and cefalu['ferry_crossings'] == 1
    for item in result['comparisons']:
        assert sum(item['breakdown_minutes'].values()) == item['estimated_minutes']
        assert item['arrival_time_status'] == 'unknown'
    for model in (Trip, Itinerary, RailJourneySnapshot):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_all_endpoints_have_explicit_comparison_access_without_pretending_airport_times(session):
    rail = RailGraph(session)
    endpoints = [city.id for city in rail.destinations.values() if city.is_endpoint]
    for offset in range(0, len(endpoints), 6):
        request = EndpointComparisonRequest(origin_id='naples', endpoint_ids=endpoints[offset:offset+6])
        for item in compare_endpoints(request, rail)['comparisons']:
            assert item['status'] == 'modeled'
            assert sum(item['breakdown_minutes'].values()) == item['estimated_minutes']
            assert sum(step['estimated_minutes'] for step in item['connections']) == item['estimated_minutes']
            if item['airport_access']['status'] == 'access_not_timed':
                assert item['airport_access']['estimated_minutes'] is None


@pytest.mark.parametrize('changes', [{'origin_id': 'athens'}, {'origin_id': 'sicily'}, {'origin_id': 'unknown'},
    {'endpoint_ids': ['prague']}, {'endpoint_ids': ['unknown']}, {'endpoint_ids': []},
    {'endpoint_ids': ['corfu', 'corfu']}, {'endpoint_ids': ['corfu'] * 7}, {'url': 'https://untrusted.example'}])
def test_comparison_validation(client, changes):
    response = client.post('/api/v1/travel/endpoints/compare', json={'endpoint_ids': ['corfu'], **changes})
    assert response.status_code == 422


def test_unmodeled_route_is_not_a_false_impossibility_or_selectable(session):
    rail = RailGraph(session)
    rail.graph.remove_edges_from(list(rail.graph.in_edges('corfu', keys=True)))
    result = compare_endpoints(EndpointComparisonRequest(endpoint_ids=['corfu']), rail)['comparisons'][0]
    assert result['status'] == 'no_modeled_route' and not result['selectable']
    assert 'does not prove' in result['notice']


def test_explicit_steps_reuse_existing_budgets_exactly_once(session):
    edges = endpoint_transfers({city.id for city in session.scalars(select(Destination))})
    for edge in edges:
        plan = edge['connection_plan']
        assert sum(step['estimated_minutes'] for step in plan['steps']) == edge['estimated_minutes']
        assert sum(part['estimated_minutes'] for part in edge['components']) == edge['estimated_minutes']
        if plan['ferry_count']:
            kinds = [step['kind'] for step in plan['steps']]
            assert kinds.index('port_access') < kinds.index('check_in') < kinds.index('ferry') < kinds.index('disembarkation')
    zakynthos = next(edge for edge in edges if edge['destination_id'] == 'zakynthos')
    kinds = [step['kind'] for step in zakynthos['connection_plan']['steps']]
    assert kinds.index('ground_before_ferry') < kinds.index('check_in') < kinds.index('ferry')
    lefkada = next(edge for edge in edges if edge['destination_id'] == 'lefkada')
    assert lefkada['connection_plan']['ferry_count'] == 0


BASE_CHECK = {'connection_id': 'bari-corfu-ferry-transfer', 'ferry_departure': '2027-06-10T22:00',
              'ferry_arrival': '2027-06-11T06:00'}


def check(client, **changes):
    return client.post('/api/v1/travel/connections/check', json={**BASE_CHECK, **changes})


def test_check_handles_country_timezones_overnight_and_early_arrival(client):
    result = check(client).json()
    assert result['status'] == 'times_only'
    assert result['crossing_minutes'] == 420  # Italy and Greece are one hour apart.
    assert result['arrival_day_change'] == 1 and result['early_or_late_arrival']
    assert result['latest_arrival_at_start'].endswith('+02:00')
    assert result['ready_at_destination'].endswith('+03:00')
    assert result['warnings'] and 'not verified or saved' in result['notice']


def test_tight_connection_reports_both_shortfalls_and_extra_night(client):
    result = check(client, arrival_at_start='2027-06-10T20:00', onward_departure='2027-06-11T07:00').json()
    assert result['status'] == 'insufficient_margin'
    assert result['before_margin_minutes'] < 0 and result['onward_margin_minutes'] < 0
    assert any('extra overnight' in note for note in result['warnings'])
    fit = check(client, arrival_at_start='2027-06-10T17:00', onward_departure='2027-06-11T10:00').json()
    assert fit['status'] == 'fits_allowances'
    assert fit['before_margin_minutes'] > 0 and fit['onward_margin_minutes'] > 0


def test_ticket_and_transfer_overrides_change_only_this_check(client):
    original = check(client).json()
    adjusted = check(client, ferry_check_in_minutes=180, port_access_minutes=120).json()
    assert adjusted['before_departure_minutes'] - original['before_departure_minutes'] == 165
    assert check(client).json() == original


@pytest.mark.parametrize('changes', [
    {'ferry_departure': '2026-10-25T02:30', 'ferry_arrival': '2026-10-25T10:00'},
    {'ferry_departure': '2026-03-29T02:30', 'ferry_arrival': '2026-03-29T10:00'},
    {'ferry_arrival': '2027-06-10T10:00'}, {'ferry_arrival': '2027-07-10T10:00'},
    {'ferry_departure': '2027-06-10T22:00+02:00'}, {'connection_id': 'missing'},
    {'connection_id': 'igoumenitsa-lefkada-ground-transfer'}, {'ferry_check_in_minutes': -1},
    {'port_access_minutes': 721}, {'onward_check_in_minutes': 361}])
def test_connection_validation(client, changes):
    assert check(client, **changes).status_code == 422


def test_reopened_old_route_gets_profiles_without_changing_saved_data_or_revision(client, session):
    trip = client.post('/api/v1/trips', json={'total_days': 35, 'required_stops': [],
        'preferences': {'endpoint_id': 'lefkada'}, 'pass': {'travel_days_total': 15}}).json()
    headers = {'X-Edit-Token': trip['edit_token']}
    generated = client.post(f"/api/v1/trips/{trip['id']}/generate", headers=headers).json()
    itinerary = session.get(Itinerary, generated[0]['id'])
    old = deepcopy(itinerary.result)
    old.pop('airport_access', None)
    for leg in old['legs']:
        for edge in leg['connections']:
            edge.pop('connection_plan', None)
    itinerary.result = old
    session.commit()
    before = json.dumps(itinerary.result, sort_keys=True)
    revision = itinerary.revision
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()['itineraries'][0]
    assert reopened['airport_access']['airport'] == 'PVK'
    assert any(edge.get('connection_plan') for leg in reopened['legs'] for edge in leg['connections'])
    session.refresh(itinerary)
    assert itinerary.revision == revision and json.dumps(itinerary.result, sort_keys=True) == before
    assert session.get(Destination, 'lefkada').airport is None


def test_late_ground_arrival_and_airport_access_are_not_hidden(client):
    late = check(client, connection_id='bari-athens-ferry-transfer', ferry_arrival='2027-06-11T21:00').json()
    assert late['early_or_late_arrival'] and late['ready_day_change'] == 1
    base = check(client, onward_departure='2027-06-11T10:00').json()
    airport = check(client, onward_departure='2027-06-11T10:00', onward_transfer_minutes=120).json()
    assert base['onward_margin_minutes'] - airport['onward_margin_minutes'] == 120
