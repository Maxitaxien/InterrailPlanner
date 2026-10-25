import json
from pathlib import Path

from sqlalchemy import func, select

from app.models.entities import Destination, RailConnection
from app.models.integrations import Attraction
from app.schemas.trips import TripRequest
from app.scripts.seed_data import seed
from app.services.route_engine.graph import RailGraph
from app.services.route_engine.generator import generate

DATA = json.loads((Path(__file__).resolve().parents[1] / 'data/coastal_expansion.json').read_text())


def test_every_new_coastal_stay_generates_with_honest_access_modes(session):
    rail = RailGraph(session)
    for city in DATA['destinations']:
        request = TripRequest.model_validate({'total_days': 35, 'required_stops': ['prague', 'venice'],
            'preferences': {'endpoint_id': city['id']}, 'pass': {'travel_days_total': 15}})
        route = generate(request, rail)[0]
        assert route['endpoint_id'] == city['id']
        assert route['stops'][-1]['nights'] == 4
        assert route['stay_nights'] + route['transit_nights_estimate'] == 34
        if city['country_code'] == 'GR':
            via = [point for leg in route['legs'] for point in leg['via']]
            assert {'bari', 'brindisi', 'ancona'} & set(via) and 'athens' not in via
            assert ({'patras'} if city['id'] in {'patras', 'kefalonia', 'zakynthos', 'ithaca'} else {'corfu'} if city['id'] == 'paxos' else {'igoumenitsa'}) & set(via)
            assert route['legs'][-1]['mode'] == 'ferry_transfer'
            assert route['legs'][-1]['travel_days_estimate'] == 0
        if city['id'] == 'cefalu':
            assert route['legs'][-1]['mode'] == 'rail'
            assert route['legs'][-1]['travel_days_estimate'] >= 1
            assert any(leg['mode'] == 'ferry_transfer' for leg in route['legs'])


def test_ionian_access_preserves_ground_transfers_and_second_ferries(session):
    rail = RailGraph(session)
    lefkada = rail.edge('igoumenitsa', 'lefkada')
    assert [component['mode'] for component in lefkada['components']] == ['ground_transfer']
    assert 'bridge' in lefkada['reservation_warning']
    assert 'No ferry' in lefkada['reservation_warning']
    zakynthos = rail.edge('patras', 'zakynthos')
    assert [component['mode'] for component in zakynthos['components']] == ['ground_transfer', 'ferry', 'buffer']
    assert zakynthos['components'][1]['origin'] == 'Kyllini'
    for origin, destination in [('bari', 'igoumenitsa'), ('bari', 'patras'), ('patras', 'kefalonia'), ('naples', 'lipari')]:
        edge = rail.edge(origin, destination)
        assert edge['estimate_quality'] == 'illustrative'
        assert sum(part['estimated_minutes'] for part in edge['components']) == edge['estimated_minutes']


def test_seed_is_idempotent_with_unique_highlights_and_no_fake_island_airports(session, client):
    models = [Destination, RailConnection, Attraction]
    before = [session.scalar(select(func.count()).select_from(model)) for model in models]
    seed(session)
    assert before == [session.scalar(select(func.count()).select_from(model)) for model in models]
    assert before[:2] == [146, 466]
    assert session.get(Destination, 'lefkada').airport is None
    for city in DATA['destinations']:
        result = client.get('/api/v1/destinations/' + city['id'])
        assert result.status_code == 200
        assert any(item['id'] == city['id'] + '-coastal' for item in result.json()['attractions'])


def test_sorrento_booking_guide_links_to_local_operator(client):
    guide = client.post('/api/v1/travel/rail/booking-guide', json={'origin_id': 'naples', 'destination_id': 'sorrento'}).json()
    assert any(link['url'] == 'https://www.eavsrl.it/' for link in guide['operators'])
    assert any('Interrail inclusion is not assumed' in note for note in guide['notes'])
