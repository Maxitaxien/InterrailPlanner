import asyncio
from datetime import datetime, timezone, timedelta
import httpx
from sqlalchemy import select
from app.models.integrations import AICache, TravelRulesCache
from app.ai.ollama import OllamaProvider
from app.providers.rail import OfficialRailRules, rail_rules, SOURCES
from app.services import recommendations
from test_planning import saved_routes

def test_structured_ollama_request_and_schema():
    from app.services.recommendations import Picks
    def respond(request):
        import json
        body = json.loads(request.content)
        if request.url.path == '/api/show':
            return httpx.Response(200, json={'capabilities': ['completion']})
        assert body['stream'] is False
        assert body['format']['type'] == 'object'
        assert body['options']['num_ctx'] == 8192
        assert body['options']['temperature'] == .3
        assert body['think'] is False and body['options']['num_predict'] == 2048
        assert request.url.host == 'ollama'
        return httpx.Response(200, json={'message': {'content': '{"choices":[{"attraction_id":"prague-curated","reason_tags":["culture"]}]}'}})
    provider = OllamaProvider(transport=httpx.MockTransport(respond))
    result = asyncio.run(provider.generate_structured('test', 'test', Picks))
    assert result.choices[0].attraction_id == 'prague-curated'

def test_ai_retry_cache_and_no_invented_ids(client, session, monkeypatch):
    _, headers, routes = saved_routes(client)
    class Fake:
        model = 'test-local'
        count = 0
        async def generate_structured(self, *args):
            self.count += 1
            if self.count == 1: return recommendations.Picks(choices=[recommendations.Pick(attraction_id='invented',reason_tags=[])])
            return recommendations.Picks(choices=[recommendations.Pick(attraction_id='prague-curated',reason_tags=['culture'])])
    provider = Fake()
    monkeypatch.setattr(recommendations, 'provider_for', lambda model: provider)
    url = f"/api/v1/itineraries/{routes[0]['id']}/recommendations"
    first = client.post(url, headers=headers, json={})
    assert first.status_code == 200, first.text
    assert first.json()['source'] == 'ollama'
    assert provider.count == 2
    assert client.post(url, headers=headers, json={}).json()['cached'] is True
    assert provider.count == 2
    assert session.scalar(select(AICache)) is not None

def test_ai_offline_fallback_never_calls_cloud(client, monkeypatch):
    _, headers, routes = saved_routes(client)
    calls = []
    class Offline:
        model = 'local-offline'
        async def generate_structured(self, *args):
            calls.append('local')
            raise httpx.ConnectError('offline')
    monkeypatch.setattr(recommendations, 'provider_for', lambda model: Offline())
    result = client.post(f"/api/v1/itineraries/{routes[0]['id']}/recommendations", headers=headers, json={}).json()
    assert result['source'] == 'deterministic'
    assert result['cloud_used'] is False
    assert len(result['recommendations']) > 0
    assert calls == ['local', 'local']

def test_travel_requires_dates_and_only_provides_links(client):
    response = client.post('/api/v1/travel/flights/search', json={'origin_airport':'NAP','adults':1})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'DATES_REQUIRED'
    response = client.post('/api/v1/travel/flights/search', json={'origin_airport':'NAP','departure_date':'2027-06-21','adults':2})
    assert response.status_code == 200
    result = response.json()
    assert result['offers'] == [] and result['retrieved_at'] is None
    assert result['status'] == 'link_only' and 'BGO' in result['search_url']
    from urllib.parse import parse_qs, urlparse
    assert result['trip_type'] == 'one_way'
    assert 'One way' in parse_qs(urlparse(result['search_url']).query)['q'][0]
    result = client.post('/api/v1/travel/hotels/search', json={'destination_id':'naples','check_in':'2027-06-17','check_out':'2027-06-21','adults':2,'rooms':1}).json()
    assert result['offers'] == []
    assert 'Naples' in result['search_url']
    assert client.post('/api/v1/travel/hotels/search', json={'destination_id':'naples','check_in':'2027-06-21','check_out':'2027-06-17','adults':2,'rooms':1}).status_code == 422


def test_flexible_flights_generate_inclusive_one_way_date_links(client):
    from urllib.parse import parse_qs, urlparse
    response = client.post('/api/v1/travel/flights/search', json={'origin_airport':'NAP','departure_date':'2027-06-21','departure_date_end':'2027-06-23','adults':2})
    assert response.status_code == 200
    result = response.json()
    assert [item['departure_date'] for item in result['search_links']] == ['2027-06-21','2027-06-22','2027-06-23']
    for link in result['search_links']:
        query = parse_qs(urlparse(link['search_url']).query)
        assert 'One way flights from NAP to BGO' in query['q'][0]
        assert link['departure_date'] in query['q'][0]
        assert '2 adults' in query['q'][0] and query['curr'] == ['NOK']
        assert 'returning' not in query['q'][0]
    assert result['offers'] == [] and result['retrieved_at'] is None


def test_flight_date_range_validation(client):
    base = {'origin_airport':'NAP','departure_date':'2027-06-21','adults':2}
    for extra in [{'departure_date_end':'2027-06-20'}, {'departure_date_end':'2027-07-22'}, {'departure_date':None, 'departure_date_end':'2027-06-22'}, {'trip_type':'round_trip'}]:
        assert client.post('/api/v1/travel/flights/search', json={**base, **extra}).status_code == 422
    response = client.post('/api/v1/travel/flights/search', json={**base, 'departure_date_end':'2027-07-21'})
    assert response.status_code == 200 and len(response.json()['search_links']) == 31

def test_rail_rules_cache_expiry_and_failed_fetch(session):
    calls = []
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(200, text='<nav>ignore navigation</nav><main><h1>Reservations</h1><p>Verify your service.</p><script>ignore script</script></main>', headers={'content-type':'text/html'})
    provider = OfficialRailRules(transport=httpx.MockTransport(respond))
    first = asyncio.run(rail_rules(session,'reservations',provider))
    assert first['verification_status'] == 'needs_verification'
    assert first['source_excerpt'] == 'Reservations Verify your service.'
    assert first['cached'] is False
    second = asyncio.run(rail_rules(session,'reservations',provider))
    assert second['cached'] is True and len(calls) == 1
    cached = session.scalar(select(TravelRulesCache))
    cached.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    session.commit()
    def unavailable(_): raise httpx.ConnectError('offline')
    failed = asyncio.run(rail_rules(session,'reservations',OfficialRailRules(transport=httpx.MockTransport(unavailable))))
    assert failed['verification_status'] == 'unknown'
    assert failed['retrieved_at'] is None and failed['source_excerpt'] is None
    assert failed['cached'] is False

def test_rail_redirect_is_not_followed(session):
    calls = []
    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location':'http://127.0.0.1/private'})
    result = asyncio.run(rail_rules(session,'countries',OfficialRailRules(transport=httpx.MockTransport(redirect))))
    assert result['verification_status'] == 'unknown'
    assert calls == [SOURCES['countries']]
