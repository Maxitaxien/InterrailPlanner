import asyncio
from datetime import date
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.models.integrations import RailJourneySnapshot
from app.providers.allaboard import AllAboardTimetables
from app.schemas.integrations import ExternalRailSearch

REQUEST = ExternalRailSearch(origin_id='milan', destination_id='bari', origin_uid='milan-uid', destination_uid='bari-uid', departure_date=date(2026, 10, 20))
CITY = SimpleNamespace(country_code='IT', longitude=9.19, latitude=45.46)


def settings(**changes):
    return Settings(_env_file=None, allaboard_enabled=True, allaboard_api_key='synthetic-private-key', **changes)


def payload():
    return {'data': {'journeys': [{'id': 'private-id', 'status': 'SUCCESS', 'itinerary': [
        {'__typename': 'SegmentCollection', 'segments': [
            {'origin': {'name': 'Milano Centrale'}, 'destination': {'name': 'Bari Centrale'},
             'departureAt': '2026-10-20T09:00', 'arrivalAt': '2026-10-20T17:00',
             'transport': 'TRAIN', 'operator': {'name': 'Trenitalia'}, 'identifier': '123'}]}]}]}}


def run(handler, config=None):
    return asyncio.run(AllAboardTimetables(config or settings(), httpx.MockTransport(handler)).search(REQUEST))


def test_documented_graphql_auth_and_research_only_response():
    def handler(request):
        assert str(request.url) == 'https://test.api-gateway.allaboard.eu/graphql'
        assert request.headers['api-key'] == 'synthetic-private-key'
        assert request.headers['session']
        assert request.headers['accept'] == 'application/graphql-response+json'
        body = json.loads(request.content)
        assert body['variables'] == {'origin': {'uid': 'milan-uid'}, 'destination': {'uid': 'bari-uid'}, 'date': '2026-10-20'}
        assert 'NON_STOP' in body['query']
        assert not any(word in body['query'] for word in ('offers', 'availability', 'mutation', 'journeyOffer'))
        return httpx.Response(200, json=payload())
    answer = run(handler)
    assert answer['status'] == 'scheduled'
    assert answer['journeys'][0]['segments'][0]['departureAt'] == '2026-10-20T09:00'
    assert answer['persistent_storage'] is False and answer['price'] is None
    assert 'selection_id' not in json.dumps(answer)
    assert 'synthetic-private-key' not in json.dumps(answer)
    assert 'synthetic-private-key' not in repr(settings())


def test_disabled_or_missing_key_makes_no_request():
    def forbidden(_): raise AssertionError('Network forbidden')
    for config in [Settings(_env_file=None), Settings(_env_file=None, allaboard_enabled=True), Settings(_env_file=None, allaboard_api_key='unused')]:
        assert run(forbidden, config)['status'] == 'not_configured'


@pytest.mark.parametrize('response', [httpx.Response(401), httpx.Response(429), httpx.Response(503),
    httpx.Response(302, headers={'location': 'https://untrusted.example'}),
    httpx.Response(200, json={'errors': [{'message': 'synthetic-private-key'}], 'data': payload()['data']}),
    httpx.Response(200, json={'data': {'journeys': None}}), httpx.Response(200, content=b' ' * 2_000_001)])
def test_failures_are_bounded_redacted_and_never_retried(response):
    calls = []
    def handler(request):
        calls.append(request)
        return response
    answer = run(handler)
    assert len(calls) == 1 and answer['status'] == 'unavailable'
    assert answer['checked_at'] is None and answer['journeys'] == []
    assert 'synthetic-private-key' not in json.dumps(answer)


def test_timeout_is_unavailable():
    def handler(request): raise httpx.ReadTimeout('secret', request=request)
    assert run(handler)['status'] == 'unavailable'


@pytest.mark.parametrize('status,expected', [('LOADING', 'pending'), ('ERROR', 'unavailable')])
def test_incomplete_provider_results_are_not_empty_coverage(status, expected):
    body = payload(); body['data']['journeys'][0]['status'] = status
    assert run(lambda _: httpx.Response(200, json=body))['status'] == expected


def test_empty_results_and_stopovers_are_distinguished():
    assert run(lambda _: httpx.Response(200, json={'data': {'journeys': []}}))['status'] == 'no_journeys'
    body = payload(); body['data']['journeys'][0]['itinerary'].append({'__typename': 'Stopover'})
    assert run(lambda _: httpx.Response(200, json=body))['status'] == 'unavailable'


def test_non_rail_transport_is_not_relabelled_as_a_train():
    body = payload(); body['data']['journeys'][0]['itinerary'][0]['segments'][0]['transport'] = 'BUS'
    answer = run(lambda _: httpx.Response(200, json=body))
    assert answer['journeys'][0]['segments'][0]['transport'] == 'BUS'


def test_location_lookup_preserves_choice_and_prefers_city_locations():
    def handler(request):
        body = json.loads(request.content)
        assert body['variables']['filter'] == {'countryCode': 'IT', 'near': {'type': 'Point', 'coordinates': [9.19, 45.46]}, 'radius': 10000}
        return httpx.Response(200, json={'data': {'locations': {'edges': [
            {'node': {'uid': 'station', 'name': 'Milano Centrale', 'countryCode': 'IT', 'isMeta': False}},
            {'node': {'uid': 'city', 'name': 'Milano', 'countryCode': 'IT', 'isMeta': True}}]}}})
    answer = asyncio.run(AllAboardTimetables(settings(), httpx.MockTransport(handler)).locations(CITY))
    assert answer['status'] == 'ok' and [row['uid'] for row in answer['locations']] == ['city', 'station']


def test_endpoints_are_local_when_disabled_and_do_not_persist(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), 'allaboard_enabled', False)
    def forbidden(*args, **kwargs): raise AssertionError('No network expected')
    monkeypatch.setattr(httpx.AsyncClient, 'stream', forbidden)
    sources = client.get('/api/v1/travel/timetable-sources')
    assert sources.headers['cache-control'] == 'no-store'
    assert sources.json()['sources'][-1]['status'] == 'awaiting_partner_contract'
    assert 'api_key' not in sources.text
    response = client.post('/api/v1/travel/rail/allaboard/timetables', json=REQUEST.model_dump(mode='json'))
    assert response.json()['status'] == 'not_configured' and response.headers['cache-control'] == 'no-store'
    assert session.scalar(select(func.count()).select_from(RailJourneySnapshot)) == 0
    assert client.post('/api/v1/travel/rail/allaboard/locations', json={'city_id': 'missing'}).status_code == 422
    assert client.post('/api/v1/travel/rail/allaboard/timetables', json={**REQUEST.model_dump(mode='json'), 'url': 'https://untrusted.example'}).status_code == 422
