from sqlalchemy import select

from app.models.entities import Destination
from app.schemas.trips import TripRequest
from app.services.route_engine.graph import RailGraph
from app.services.route_engine.generator import generate


def test_new_gateways_have_reachable_rail_and_separate_ferry_access(session):
    rail = RailGraph(session)
    for city_id in ['brindisi', 'ancona', 'salerno', 'piombino']:
        assert city_id in rail.rail_reachable()
        assert rail.destinations[city_id].is_endpoint
        path = rail.path('oslo', city_id, allow_endpoint_transfer=False)
        assert all(rail.edge(a, b)['mode'] == 'rail' for a, b in zip(path, path[1:]))
    brindisi = rail.edge('brindisi', 'corfu')
    assert brindisi['seasonal']
    assert 'Costa Morena' in brindisi['connection_plan']['steps'][0]['label']
    assert rail.edge('brindisi', 'igoumenitsa')['connection_plan']['ferry_count'] == 1
    assert rail.edge('salerno', 'sicily')['components'][0]['destination'] == 'Palermo'
    assert 'Piombino Marittima' in rail.edge('piombino', 'elba')['connection_plan']['steps'][0]['label']


def test_western_island_routes_preserve_ports_ground_and_single_ferry_port_calls(session):
    rail = RailGraph(session)
    paxos = rail.edge('corfu', 'paxos')
    assert paxos['seasonal'] and paxos['components'][0]['destination'] == 'Gaios (Paxos)'
    ithaca = rail.edge('patras', 'ithaca')
    assert ithaca['connection_plan']['ferry_count'] == 1
    assert any(part.get('origin') == 'Pisaetos' and part.get('destination') == 'Vathy (Ithaca)' and part['mode'] == 'ground_transfer' for part in ithaca['components'])
    meganisi = rail.edge('lefkada', 'meganisi')
    assert [part['mode'] for part in meganisi['components']] == ['ground_transfer', 'ferry', 'ground_transfer', 'buffer']
    assert meganisi['components'][0]['destination'] == 'Nydri'
    assert meganisi['components'][1]['destination'] == 'Spilia (Meganisi)'
    kinds = [step['kind'] for step in meganisi['connection_plan']['steps']]
    assert kinds.index('ground_before_ferry') < kinds.index('ferry') < kinds.index('ground_after_ferry')
    for island in ['paxos', 'ithaca', 'meganisi', 'elba']:
        assert session.get(Destination, island).airport is None
        route = generate(TripRequest.model_validate({'total_days': 35, 'required_stops': [],
            'preferences': {'endpoint_id': island}, 'pass': {'travel_days_total': 15}}), rail)[0]
        assert route['airport_access']['ferry_crossings'] == 1
        assert route['legs'][-1]['mode'] == 'ferry_transfer'
        assert route['legs'][-1]['travel_days_estimate'] == 0


def test_new_gateways_are_comparison_origins_and_seasonal_tails_stay_visible(client):
    for origin in ['brindisi', 'ancona', 'salerno', 'piombino']:
        response = client.post('/api/v1/travel/endpoints/compare', json={'origin_id': origin, 'endpoint_ids': ['paxos', 'ithaca', 'meganisi', 'elba']})
        assert response.status_code == 200
        assert all(item['status'] == 'modeled' for item in response.json()['comparisons'])
    direct = client.post('/api/v1/travel/endpoints/compare', json={'origin_id': 'brindisi', 'endpoint_ids': ['corfu', 'paxos']}).json()['comparisons']
    assert direct[0]['route_names'] == ['Brindisi', 'Corfu']
    assert direct[0]['seasonal'] and direct[1]['seasonal']
    assert direct[1]['ferry_crossings'] == 2
