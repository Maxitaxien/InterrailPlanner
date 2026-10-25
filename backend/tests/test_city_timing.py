from datetime import date
from types import SimpleNamespace

import httpx
from app.core.config import get_settings
from app.models.entities import Destination, Itinerary, Trip, TripStop
from app.providers.city_search import CitySearch, validated_query
from app.services import city_ideas
from app.services.city_query import SearchQuery
from app.services.city_timing import seasonal_context, travel_context


def dated_trip(client, start='2027-05-28', days=21):
    result = client.post('/api/v1/trips', json={'start_date': start, 'date_mode': 'exact', 'total_days': days})
    assert result.status_code == 201, result.text
    return result.json()


def itinerary(session, trip_id, start, end, selected=True, city='paris', position=1):
    route = Itinerary(trip_id=trip_id, name='Timing fixture', score=1, result={}, is_selected=selected)
    session.add(route)
    session.flush()
    add_visit(session, route, start, end, city, position)
    return route


def add_visit(session, route, start, end, city='paris', position=1):
    trip = session.get(Trip, route.trip_id)
    arrival, departure = date.fromisoformat(start), date.fromisoformat(end)
    session.add(TripStop(itinerary_id=route.id, destination_id=city, position=position,
        arrival_day=(arrival-trip.start_date).days, departure_day=(departure-trip.start_date).days,
        arrival_date=arrival, departure_date=departure, nights=(departure-arrival).days, is_required=False))
    session.flush()


def test_city_dates_override_trip_start_and_preview_can_override_selected_route(client, session):
    saved = dated_trip(client)
    trip, city = session.get(Trip, saved['id']), session.get(Destination, 'paris')
    selected = itinerary(session, trip.id, '2027-05-30', '2027-05-31')
    preview = itinerary(session, trip.id, '2027-06-01', '2027-06-03', selected=False)
    assert travel_context(session, trip, city)['periods'] == [{'month': 'May', 'year': 2027, 'season': 'spring'}]
    timing = travel_context(session, trip, city, preview.id)
    assert timing['scope'] == 'city_visit' and timing['start_date'] == '2027-06-01'
    assert timing['periods'] == [{'month': 'June', 'year': 2027, 'season': 'summer'}]
    assert timing['visits'][0]['nights'] == 2
    assert seasonal_context(timing)['periods'] == timing['periods']
    assert '2027-06-01' not in str(seasonal_context(timing))


def test_non_route_city_uses_overall_window_across_new_year_and_no_dates_stay_unknown(client, session):
    saved = dated_trip(client, start='2027-12-28')
    trip, city = session.get(Trip, saved['id']), session.get(Destination, 'paris')
    timing = travel_context(session, trip, city)
    assert timing['scope'] == 'trip_window' and timing['visits'] == []
    assert timing['periods'] == [{'month': 'December', 'year': 2027, 'season': 'winter'}, {'month': 'January', 'year': 2028, 'season': 'winter'}]
    flexible = client.post('/api/v1/trips', json={}).json()
    assert travel_context(session, session.get(Trip, flexible['id']), city) is None


def test_repeated_and_zero_night_visits_keep_all_relevant_months(client, session):
    saved = dated_trip(client, days=60)
    trip, city = session.get(Trip, saved['id']), session.get(Destination, 'paris')
    route = itinerary(session, trip.id, '2027-05-30', '2027-05-30')
    add_visit(session, route, '2027-06-30', '2027-07-02', position=3)
    timing = travel_context(session, trip, city)
    assert [period['month'] for period in timing['periods']] == ['May', 'June', 'July']
    assert timing['visits'][0]['nights'] == 0 and len(timing['visits']) == 2


def test_foreign_itinerary_cannot_supply_dates(client, session):
    first, other = dated_trip(client), dated_trip(client)
    foreign = itinerary(session, other['id'], '2027-06-01', '2027-06-02')
    response = client.post(f"/api/v1/trips/{first['id']}/cities/paris/ideas", headers={'X-Edit-Token': first['edit_token']}, json={'itinerary_id': foreign.id})
    assert response.status_code == 404


def test_both_model_steps_get_timing_but_search_only_gets_a_coarse_query(client, session, monkeypatch):
    import json
    settings = get_settings()
    monkeypatch.setattr(settings, 'searxng_base_url', 'http://synthetic-search:8080')
    saved = dated_trip(client)
    route = itinerary(session, saved['id'], '2027-06-01', '2027-06-03')
    stages = []
    class Model:
        async def generate_structured(self, system, prompt, schema):
            data = json.loads(prompt)
            if schema is SearchQuery:
                stages.append('plan')
                assert data['seasonal_context']['periods'] == [{'month': 'June', 'year': 2027, 'season': 'summer'}]
                assert '2027-06-01' not in prompt and '2027-06-03' not in prompt and '2027-05-28' not in prompt
                assert 'only when helpful' in system
                return SearchQuery(query='outdoor activities in Paris June 2027')
            stages.append('answer')
            assert data['travel_context']['start_date'] == '2027-06-01'
            assert data['travel_context']['visits'][0]['nights'] == 2
            assert 'Do not claim future opening dates' in system
            return city_ideas.Ideas(introduction='Check seasonal suitability and future opening dates before planning.', ideas=[])
    monkeypatch.setattr(city_ideas, 'provider_for', lambda _: Model())
    def respond(request):
        stages.append('search')
        assert request.url.params['q'] == 'outdoor activities in Paris June 2027'
        assert '2027-06-01' not in str(request.url)
        return httpx.Response(200, json={'results': []})
    monkeypatch.setattr(city_ideas, 'search_provider', lambda: CitySearch(settings, httpx.MockTransport(respond)))
    url = f"/api/v1/trips/{saved['id']}/cities/paris/ideas"
    headers = {'X-Edit-Token': saved['edit_token']}
    response = client.post(url, headers=headers, json={'question': 'Something outdoors', 'itinerary_id': route.id})
    assert response.status_code == 200, response.text
    assert stages == ['plan', 'search', 'answer']
    timing = response.json()['request']['travel_context']
    assert timing['scope'] == 'city_visit' and timing['start_date'] == '2027-06-01'
    # Reading saved versions preserves their original timing and runs neither step.
    assert client.get(url, headers=headers).json()['sets'][0]['request']['travel_context'] == timing
    assert stages == ['plan', 'search', 'answer']
