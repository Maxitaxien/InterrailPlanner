from datetime import date
from hypothesis import given, strategies as st
import pytest
from sqlalchemy import select, func
from app.models.entities import TripStop, TripLeg, Itinerary
from app.schemas.trips import TripRequest
from app.services.route_engine.graph import RailGraph
from app.services.route_engine.generator import generate, build_path
from app.services.errors import PlanningError

REQUEST = {'total_days': 21, 'required_stops': ['prague', 'venice']}

def test_unreachable_preferred_city_does_not_block_feasible_route(session):
    request = TripRequest.model_validate({**REQUEST, 'preferred_stops': ['athens']})
    routes = generate(request, RailGraph(session))
    assert routes
    assert {'prague', 'venice'} <= {stop['destination_id'] for stop in routes[0]['stops']}
    assert any('Optional cities omitted' in warning and 'Athens' in warning for warning in routes[0]['warnings'])

def test_legacy_daily_limit_is_ignored_and_long_legs_are_advisory(session):
    request = TripRequest.model_validate({'required_stops': ['copenhagen'], 'preferences': {'endpoint_id': 'bari', 'max_daily_travel_hours': 4}})
    routes = generate(request, RailGraph(session))
    assert routes and routes[0]['endpoint_id'] == 'bari'
    long_legs = [leg for leg in routes[0]['legs'] if leg['is_long_journey']]
    assert long_legs and any(leg['estimated_minutes'] > 480 for leg in long_legs)
    assert any(leg['suggested_stop_ids'] for leg in long_legs)
    assert all('intermediate' in leg['travel_advice'] or 'overnight' in leg['travel_advice'] for leg in long_legs)

def test_north_to_south_honeymoon_route_remains_feasible(session):
    request = TripRequest.model_validate({'total_days': 28, 'required_stops': ['copenhagen', 'hamburg', 'munich', 'milan'], 'preferences': {'endpoint_id': 'bari'}, 'pass': {'travel_days_total': 15}})
    routes = generate(request, RailGraph(session))
    assert routes and routes[0]['endpoint_id'] == 'bari'
    assert {'copenhagen', 'hamburg', 'munich', 'milan'} <= {stop['destination_id'] for stop in routes[0]['stops']}


def test_endpoint_transfer_is_not_an_intermediate_rail_shortcut(session):
    rail = RailGraph(session).daytime()
    assert build_path(['oslo', 'athens'], rail)[-2:] == ['bari', 'athens']
    with pytest.raises(PlanningError) as caught:
        build_path(['oslo', 'athens', 'bari'], rail)
    assert caught.value.code == 'ROUTE_NOT_FOUND'


def test_multiday_rail_time_advances_calendar_without_a_daily_cap(session):
    from app.services.scheduler import schedule
    rail = RailGraph(session)
    rail.graph.add_edge('oslo', 'bari', key='test-long-leg', minutes=3000, mode='rail', night_train=False)
    request = TripRequest.model_validate({'total_days': 7, 'start_date': '2027-06-01', 'date_mode': 'exact', 'preferences': {'endpoint_id': 'bari', 'final_stay_nights': 4, 'max_daily_travel_hours': 1}, 'pass': {'travel_days_total': 3, 'valid_until': '2027-06-03'}})
    result = schedule(['oslo', 'bari'], request, rail)
    assert result['transit_nights_estimate'] == 2
    assert result['travel_days_estimate'] == 3
    assert result['stops'][-1]['arrival_date'] == '2027-06-03'
    assert result['stops'][-1]['nights'] == 4
    assert result['total_nights'] == 6
    request.pass_details.travel_days_total = 2
    with pytest.raises(PlanningError) as caught:
        schedule(['oslo', 'bari'], request, rail)
    assert caught.value.code == 'PASS_LIMIT_EXCEEDED'


def test_switch_to_greece_and_reopen_preserves_transfer_mode(client):
    trip, headers, routes = saved_routes(client)
    route = routes[0]
    response = client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers, json={'expected_revision': 1, 'operation': 'change_endpoint', 'destination_id': 'athens'})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['legs'][-1]['mode'] == 'ferry_transfer'
    assert updated['stops'][-1]['nights'] == 4
    assert updated['total_nights'] == 20
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()
    assert next(route for route in reopened['itineraries'] if route['id'] == updated['id']) == updated


def test_adding_suggested_stop_breaks_up_long_rail_leg(client):
    _, headers, routes = saved_routes(client)
    route = routes[0]
    leg = next(leg for leg in route['legs'] if leg['suggested_stop_ids'])
    city = leg['suggested_stop_ids'][0]
    response = client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers, json={'expected_revision': 1, 'operation': 'add_stop', 'destination_id': city})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert any(stop['destination_id'] == city and stop['nights'] > 0 for stop in updated['stops'])
    assert updated['total_nights'] == 20 and updated['stops'][-1]['nights'] == 4
    assert not any(candidate['origin_id'] == leg['origin_id'] and candidate['destination_id'] == leg['destination_id'] for candidate in updated['legs'])
def saved_routes(client):
    created = client.post('/api/v1/trips', json=REQUEST)
    assert created.status_code == 201, created.text
    trip = created.json()
    headers = {'X-Edit-Token': trip['edit_token']}
    generated = client.post(f"/api/v1/trips/{trip['id']}/generate", headers=headers)
    assert generated.status_code == 200, generated.text
    return trip, headers, generated.json()

def test_sprint_acceptance(client, session):
    trip, headers, routes = saved_routes(client)
    assert len(routes) == 3
    for r in routes:
        cities = {s['destination_id'] for s in r['stops']}
        assert {'oslo', 'prague', 'venice'} <= cities
        assert r['stops'][-1]['country_code'] == 'IT'
        assert sum(s['nights'] for s in r['stops']) + r['transit_nights_estimate'] == 20
        assert r['stops'][-1]['nights'] == 4
        assert r['travel_days_estimate'] <= 7
        assert all(l['is_long_journey'] == (l['estimated_minutes'] > 480) for l in r['legs'])
        assert r['pass_status'] == 'needs_verification'
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()
    assert len(reopened['itineraries']) == 3
    assert 'edit_token' not in reopened
    assert 'edit_token_hash' not in reopened
    assert session.scalar(select(func.count()).select_from(TripStop)) > 0
    assert session.scalar(select(func.count()).select_from(TripLeg)) > 0

def test_auth_and_stale_edit(client):
    trip, headers, routes = saved_routes(client)
    route = routes[0]
    url = f"/api/v1/itineraries/{route['id']}"
    edit = {'expected_revision': 1, 'operation': 'lock_stop', 'destination_id': 'prague', 'locked': True}
    assert client.patch(url, json=edit).status_code == 401
    changed = client.patch(url, headers=headers, json=edit)
    assert changed.status_code == 200, changed.text
    assert changed.json()['revision'] == 2
    assert client.patch(url, headers=headers, json=edit).status_code == 409
    rejected = client.patch(url, headers=headers, json={**edit, 'expected_revision': 2, 'operation': 'set_nights', 'nights': 8})
    assert rejected.status_code == 422
    assert rejected.json()['error']['code'] == 'STOP_LOCKED'

def test_impossible_edit_is_atomic(client):
    trip, headers, routes = saved_routes(client)
    route = routes[0]
    response = client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers, json={'expected_revision': 1, 'operation': 'set_nights', 'destination_id': 'prague', 'nights': 30})
    assert response.status_code == 422
    stored = client.get(f"/api/v1/trips/{trip['id']}/itineraries").json()
    assert next(r for r in stored if r['id'] == route['id']) == route

def test_pass_and_duration_failures(client):
    for request, expected in [
        ({**REQUEST, 'pass': {'travel_days_total': 2}}, 'PASS_LIMIT_EXCEEDED'),
        ({**REQUEST, 'total_days': 5}, 'TRIP_DURATION_EXCEEDED'),
        ({**REQUEST, 'pass': {'type': 'one_country', 'country_code': 'IT'}}, 'PASS_INCOMPATIBLE'),
    ]:
        trip = client.post('/api/v1/trips', json=request).json()
        result = client.post(f"/api/v1/trips/{trip['id']}/generate", headers={'X-Edit-Token': trip['edit_token']})
        assert result.status_code == 422, result.text
        assert result.json()['error']['code'] == expected

def test_exact_dates_and_pass_expiry(client):
    request = {**REQUEST, 'date_mode': 'exact', 'start_date': '2027-06-01'}
    trip = client.post('/api/v1/trips', json=request).json()
    routes = client.post(f"/api/v1/trips/{trip['id']}/generate", headers={'X-Edit-Token': trip['edit_token']}).json()
    assert routes[0]['return_date'] == '2027-06-21'
    assert routes[0]['stops'][-1]['departure_date'] == '2027-06-21'
    request['pass'] = {'valid_until': '2027-06-02'}
    trip = client.post('/api/v1/trips', json=request).json()
    result = client.post(f"/api/v1/trips/{trip['id']}/generate", headers={'X-Edit-Token': trip['edit_token']})
    assert result.status_code == 422
    assert result.json()['error']['code'] == 'PASS_INCOMPATIBLE'

def test_delete_cascades_and_selection(client, session):
    trip, headers, routes = saved_routes(client)
    assert client.post(f"/api/v1/itineraries/{routes[1]['id']}/select", headers=headers).status_code == 200
    stored = client.get(f"/api/v1/trips/{trip['id']}/itineraries").json()
    assert sum(r['is_selected'] for r in stored) == 1
    assert client.delete(f"/api/v1/trips/{trip['id']}").status_code == 401
    assert client.delete(f"/api/v1/trips/{trip['id']}", headers=headers).status_code == 204
    assert session.scalar(select(func.count()).select_from(TripStop)) == 0
    assert session.scalar(select(func.count()).select_from(TripLeg)) == 0

def test_seed_idempotent(session):
    from app.scripts.seed_data import seed
    from app.models.entities import Destination
    before = session.scalar(select(func.count()).select_from(Destination))
    seed(session)
    assert session.scalar(select(func.count()).select_from(Destination)) == before

def test_unknown_and_validation(client):
    assert client.post('/api/v1/trips', json={**REQUEST, 'required_stops': ['atlantis']}).status_code == 422
    assert client.post('/api/v1/trips', json={**REQUEST, 'date_mode': 'exact'}).status_code == 422
    assert client.post('/api/v1/trips', json={**REQUEST, 'budget': {'total': -1}}).status_code == 422

@given(days=st.integers(min_value=12,max_value=90), final=st.integers(min_value=1,max_value=6))
def test_calendar_properties(days, final):
    # Pure scheduler property with an isolated graph, no database fixture lifecycle.
    import json
    from types import SimpleNamespace
    from pathlib import Path
    import networkx as nx
    from app.services.scheduler import schedule
    data = Path(__file__).resolve().parents[1] / 'data'
    rail = SimpleNamespace(destinations={d['id']: SimpleNamespace(**d) for d in json.loads((data/'destinations.json').read_text())})
    rail.graph = nx.MultiDiGraph()
    for e in json.loads((data/'rail_connections.json').read_text()): rail.graph.add_edge(e['origin_id'],e['destination_id'],minutes=e['estimated_minutes'])
    rail.edge = lambda a,b: min(rail.graph[a][b].values(), key=lambda e:e['minutes'])
    request = TripRequest.model_validate({**REQUEST, 'total_days':days, 'preferences': {'final_stay_nights': final}})
    path = ['oslo','gothenburg','copenhagen','hamburg','berlin','prague','vienna','venice','bologna','florence','rome','naples']
    result = schedule(path, request, rail)
    assert sum(s['nights'] for s in result['stops']) == days-1
    assert result['stops'][-1]['departure_day'] == days-1
    assert all(s['departure_day']-s['arrival_day'] == s['nights'] >= 0 for s in result['stops'])
    for a,b in zip(result['stops'],result['stops'][1:]): assert a['departure_day'] == b['arrival_day']

def test_regions_and_explicit_greece_endpoint_transfer(client, session):
    for region in ['southern_france','spain','croatia']:
        request = {'total_days':28,'required_stops':[],'preferences':{'endpoint_region':region},'pass':{'travel_days_total':15}}
        trip = client.post('/api/v1/trips',json=request).json()
        result = client.post(f"/api/v1/trips/{trip['id']}/generate",headers={'X-Edit-Token':trip['edit_token']})
        assert result.status_code == 200, result.text
        assert len(result.json()) >= 1
    trip = client.post('/api/v1/trips',json={'preferences':{'endpoint_region':'greece','endpoint_id':'athens'}}).json()
    result = client.post(f"/api/v1/trips/{trip['id']}/generate",headers={'X-Edit-Token':trip['edit_token']})
    assert result.status_code == 200, result.text
    route = result.json()[0]
    assert route['endpoint_id'] == 'athens'
    transfer = route['legs'][-1]
    assert transfer['mode'] == 'ferry_transfer' and transfer['origin_id'] == 'bari'
    assert transfer['travel_days_estimate'] == 0 and transfer['rail_minutes'] == 0
    assert transfer['travel_nights_estimate'] == 1
    assert transfer['connections'][0]['components'][0]['destination'] == 'Patras'
    assert route['has_non_rail_transfer'] and route['transit_nights_estimate'] >= 1
    assert sum(stop['nights'] for stop in route['stops']) + route['transit_nights_estimate'] == 20
    assert route['stops'][-1]['arrival_day'] == route['stops'][-2]['departure_day'] + 1
    assert any('ferry' in warning and 'unverified' in warning for warning in route['warnings'])
    stored_leg = session.scalar(select(TripLeg).where(TripLeg.itinerary_id == route['id'], TripLeg.mode == 'ferry_transfer'))
    assert stored_leg is not None and stored_leg.travel_days_estimate == 0

def test_preference_patch_is_revision_checked_and_recalculates(client):
    trip, headers, routes = saved_routes(client)
    response = client.patch(f"/api/v1/trips/{trip['id']}",headers=headers,json={'expected_revision':1,'total_days':24,'budget':{'total':'32000'},'preferences':{'interests':['history']}})
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated['revision'] == 2
    assert updated['request']['preferences']['interests'] == ['history']
    assert updated['request']['preferences']['final_stay_nights'] == 4
    assert all(r['total_nights']==23 and r['revision']==2 for r in updated['itineraries'])
    assert client.patch(f"/api/v1/trips/{trip['id']}",headers=headers,json={'expected_revision':1,'total_days':25}).status_code == 409
    failed = client.patch(f"/api/v1/trips/{trip['id']}",headers=headers,json={'expected_revision':2,'total_days':5})
    assert failed.status_code == 422
    assert client.get(f"/api/v1/trips/{trip['id']}").json() == updated

def test_explicit_nights_survive_further_edits(client):
    trip, headers, routes = saved_routes(client)
    route=routes[0]
    url=f"/api/v1/itineraries/{route['id']}"
    changed=client.patch(url,headers=headers,json={'expected_revision':1,'operation':'set_nights','destination_id':'prague','nights':5})
    assert changed.status_code==200, changed.text
    locked=client.patch(url,headers=headers,json={'expected_revision':2,'operation':'lock_stop','destination_id':'prague','locked':True})
    assert locked.status_code==200, locked.text
    assert next(s['nights'] for s in locked.json()['stops'] if s['destination_id']=='prague')==5

def test_zero_night_required_visit_survives_edits_and_reopen(client):
    trip, headers, routes = saved_routes(client)
    route = routes[0]
    url = f"/api/v1/itineraries/{route['id']}"
    changed = client.patch(url, headers=headers, json={'expected_revision': 1, 'operation': 'set_nights', 'destination_id': 'prague', 'nights': 0})
    assert changed.status_code == 200, changed.text
    result = changed.json()
    visit = next(s for s in result['stops'] if s['destination_id'] == 'prague')
    assert visit['nights'] == 0 and visit['is_day_visit'] and visit['is_required']
    assert visit['arrival_day'] == visit['departure_day']
    assert result['night_overrides']['prague'] == 0
    assert result['total_nights'] == 20
    assert result['stay_nights'] + result['transit_nights_estimate'] == 20
    locked = client.patch(url, headers=headers, json={'expected_revision': 2, 'operation': 'lock_stop', 'destination_id': 'prague', 'locked': True})
    assert locked.status_code == 200, locked.text
    assert next(s for s in locked.json()['stops'] if s['destination_id'] == 'prague')['nights'] == 0
    patched = client.patch(f"/api/v1/trips/{trip['id']}", headers=headers, json={'expected_revision': 1, 'total_days': 22})
    assert patched.status_code == 200, patched.text
    reopened = client.get(f"/api/v1/trips/{trip['id']}").json()
    stored = next(r for r in reopened['itineraries'] if r['id'] == route['id'])
    assert next(s for s in stored['stops'] if s['destination_id'] == 'prague')['nights'] == 0
    assert stored['total_nights'] == 21

def test_zero_night_visit_uses_same_pass_day_and_final_stay_absorbs_spare(session):
    from app.services.scheduler import schedule
    rail = RailGraph(session).daytime()
    # Short synthetic corridors isolate calendar accounting from seed durations.
    rail.graph = rail.graph.copy()
    for a, b in [('oslo', 'prague'), ('prague', 'bari')]:
        rail.graph.add_edge(a, b, key='day-visit-test', minutes=60, mode='rail', night_train=False)
    request = TripRequest.model_validate({'total_days': 7, 'required_stops': ['prague'], 'start_date': '2027-06-01', 'date_mode': 'exact', 'preferences': {'endpoint_id': 'bari', 'final_stay_nights': 4}, 'pass': {'travel_days_total': 1}})
    result = schedule(['oslo', 'prague', 'bari'], request, rail, {'prague': 0})
    assert result['travel_days_estimate'] == 1
    assert result['stops'][1]['arrival_date'] == result['stops'][1]['departure_date'] == '2027-06-01'
    assert result['stops'][-1]['nights'] == 6
    assert result['total_nights'] == 6
    assert any('Remaining nights' in warning for warning in result['warnings'])
    # Never silently increase an explicitly fixed final stay.
    with pytest.raises(PlanningError) as caught:
        schedule(['oslo', 'prague', 'bari'], request, rail, {'prague': 0, 'bari': 4})
    assert caught.value.code == 'LOCKED_DURATION_CONFLICT'

def test_zero_night_endpoint_and_negative_nights_validation(client):
    _, headers, routes = saved_routes(client)
    route = routes[0]
    url = f"/api/v1/itineraries/{route['id']}"
    endpoint = route['stops'][-1]['destination_id']
    invalid = client.patch(url, headers=headers, json={'expected_revision': 1, 'operation': 'set_nights', 'destination_id': endpoint, 'nights': -1})
    assert invalid.status_code == 422
    changed = client.patch(url, headers=headers, json={'expected_revision': 1, 'operation': 'set_nights', 'destination_id': endpoint, 'nights': 0})
    assert changed.status_code == 200, changed.text
    assert changed.json()['stops'][-1]['nights'] == 0
    assert changed.json()['total_nights'] == 20
    assert TripRequest.model_validate({'preferences': {'final_stay_nights': 0}}).preferences.final_stay_nights == 0

def test_required_and_missing_connections_fail_atomically(client):
    trip, headers, routes=saved_routes(client)
    route=routes[0]
    url=f"/api/v1/itineraries/{route['id']}"
    for operation, city, code in [('remove_stop','prague','REQUIRED_STOP'),('change_endpoint','thessaloniki','INVALID_ENDPOINT')]:
        result=client.patch(url,headers=headers,json={'expected_revision':1,'operation':operation,'destination_id':city})
        assert result.status_code==422, result.text
        assert result.json()['error']['code']==code
    stored=client.get(f"/api/v1/trips/{trip['id']}/itineraries").json()
    assert next(r for r in stored if r['id']==route['id'])==route


def test_southbound_corridor_does_not_require_backtracking(session):
    rail = RailGraph(session).limited(480)
    waypoints = ['oslo', 'copenhagen', 'hamburg', 'munich', 'milan', 'bari']
    path = build_path(waypoints, rail)
    assert len(path) == len(set(path))
    assert [city for city in path if city in waypoints] == waypoints


def test_forward_alternative_is_used_when_fastest_segment_revisits_a_city():
    from types import SimpleNamespace
    import networkx as nx
    graph = nx.MultiDiGraph()
    # The greedy b→c path goes back through a. A forward alternative exists.
    for a, b, minutes in [('a', 'b', 1), ('b', 'a', 1), ('a', 'c', 1),
                           ('b', 'd', 2), ('d', 'c', 2)]:
        graph.add_edge(a, b, minutes=minutes)
    assert build_path(['a', 'b', 'c'], SimpleNamespace(graph=graph, segment_graph=lambda _: graph)) == ['a', 'b', 'd', 'c']


def test_map_add_stop_finds_a_feasible_insertion_instead_of_appending(client):
    request = {'total_days': 28, 'required_stops': ['copenhagen', 'hamburg', 'munich', 'venice'],
               'preferences': {'endpoint_id': 'bari'}, 'pass': {'travel_days_total': 15}}
    trip = client.post('/api/v1/trips', json=request).json()
    headers = {'X-Edit-Token': trip['edit_token']}
    generated = client.post(f"/api/v1/trips/{trip['id']}/generate", headers=headers)
    assert generated.status_code == 200, generated.text
    route = generated.json()[0]
    response = client.patch(f"/api/v1/itineraries/{route['id']}", headers=headers,
        json={'expected_revision': route['revision'], 'operation': 'add_stop', 'destination_id': 'milan'})
    assert response.status_code == 200, response.text
    cities = [stop['destination_id'] for stop in response.json()['stops']]
    assert cities.index('munich') < cities.index('milan') < cities.index('bari')
    assert len(cities) == len(set(cities))


def test_map_network_covers_expanded_cities_without_orphan_edges(client):
    cities = {city['id'] for city in client.get('/api/v1/destinations').json()}
    response = client.get('/api/v1/rail-network')
    assert response.status_code == 200
    edges = response.json()
    assert {'bergen', 'brno', 'rotterdam', 'krakow', 'geneva'} <= cities
    assert len(edges) > 200
    assert all(edge['origin_id'] in cities and edge['destination_id'] in cities for edge in edges)
    assert all(edge['estimated_minutes'] > 0 and edge['estimate_quality'] == 'illustrative' for edge in edges)


@pytest.mark.parametrize('city', ['bergen', 'trondheim', 'stavanger', 'bruges', 'gdansk', 'lucerne', 'split'])
def test_branch_line_city_can_be_a_single_must_see(session, city):
    rail = RailGraph(session)
    request = TripRequest.model_validate({'total_days': 35, 'required_stops': [city], 'pass': {'travel_days_total': 15}})
    result = generate(request, rail)[0]
    assert any(stop['destination_id'] == city and stop['is_required'] for stop in result['stops'])
    assert sum(stop['nights'] for stop in result['stops']) + result['transit_nights_estimate'] == 34
    assert len(result['legs']) == len(result['stops']) - 1
    for index, stop in enumerate(result['stops']):
        assert stop['departure_day'] - stop['arrival_day'] == stop['nights']
        if index:
            assert stop['arrival_day'] == result['stops'][index - 1]['departure_day'] + result['legs'][index-1]['travel_nights_estimate']


def test_retry_after_failure_uses_updated_stops_and_pass(client):
    trip = client.post('/api/v1/trips', json={'required_stops': ['prague', 'venice'], 'pass': {'travel_days_total': 1}}).json()
    headers = {'X-Edit-Token': trip['edit_token']}
    url = f"/api/v1/trips/{trip['id']}"
    assert client.post(url + '/generate', headers=headers).status_code == 422
    updated = client.patch(url, headers=headers, json={'expected_revision': 1, 'required_stops': ['bergen'], 'pass': {'travel_days_total': 15}})
    assert updated.status_code == 200, updated.text
    response = client.post(url + '/generate', headers=headers)
    assert response.status_code == 200, response.text
    for route in response.json():
        required = {stop['destination_id'] for stop in route['stops'] if stop['is_required']}
        assert required == {'bergen'}
        assert route['total_nights'] == 20
    assert client.get(url).json()['request']['required_stops'] == ['bergen']


def test_more_than_six_required_cities_use_bounded_order_search(session):
    required = ['copenhagen', 'hamburg', 'berlin', 'prague', 'vienna', 'venice', 'bologna']
    request = TripRequest.model_validate({'total_days': 35, 'required_stops': required, 'pass': {'travel_days_total': 15}})
    results = generate(request, RailGraph(session))
    assert results
    assert set(required) <= {stop['destination_id'] for stop in results[0]['stops'] if stop['is_required']}


def test_every_connected_city_can_be_the_only_required_stop(session):
    import networkx as nx
    rail = RailGraph(session)
    connected = nx.descendants(rail.segment_graph(False), 'oslo')
    assert len(connected) >= 100
    for city in sorted(connected):
        request = TripRequest.model_validate({'total_days': 60, 'required_stops': [city], 'pass': {'travel_days_total': 30}})
        result = generate(request, rail)[0]
        assert any(stop['destination_id'] == city and stop['is_required'] for stop in result['stops']), city
        assert result['total_nights'] == 59
