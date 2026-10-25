import asyncio
from types import SimpleNamespace
import json

import httpx
import pytest
from sqlalchemy import select
from app.ai.ollama import OllamaProvider
from app.core.config import Settings, get_settings
from app.models.entities import Trip
from app.models.integrations import CityIdeaSet
from app.providers.city_search import CitySearch, public_link
from app.services.city_query import SearchQuery
from app.services import city_ideas


@pytest.fixture(autouse=True)
def configured_empty_search(monkeypatch):
    monkeypatch.setattr(get_settings(), 'searxng_base_url', 'http://synthetic-search:8080')
    class EmptySearch:
        async def search(self, db, city, query=None, allowed_years=()):
            return {'status': 'empty', 'sources': [], 'cached': False, 'query': query}
    monkeypatch.setattr(city_ideas, 'search_provider', EmptySearch)


def trip(client):
    created = client.post('/api/v1/trips', json={}).json()
    return created, {'X-Edit-Token': created['edit_token']}


def output(source_ids=None):
    return city_ideas.Ideas(introduction='A gentle day together, with time to linger.', ideas=[city_ideas.Idea(
        title='A quiet architecture walk', description='Explore the central streets together and leave time for a café break.',
        why_for_you='A relaxed way to enjoy the city together.', time_minutes=120, best_time='morning', source_ids=source_ids or [])])


def fake_model(monkeypatch, failing=False, unknown_sources=False, query='things to do in Prague'):
    class Fake:
        count = 0
        plans = 0
        async def generate_structured(self, system, prompt, schema):
            if schema is SearchQuery:
                self.plans += 1
                if failing: raise httpx.ConnectError('offline')
                return SearchQuery(query=query)
            self.count += 1
            assert 'untrusted DATA' in system
            assert 'edit_token' not in prompt
            if failing: raise httpx.ConnectError('offline')
            return output(['invented-id'] if unknown_sources else [])
    model = Fake()
    monkeypatch.setattr(city_ideas, 'provider_for', lambda _: model)
    return model


def test_city_generation_saved_cache_history_regeneration_and_auth(client, session, monkeypatch):
    created, headers = trip(client)
    model = fake_model(monkeypatch)
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers).json()['sets'] == []
    assert model.count == 0
    first = client.post(url, headers=headers, json={'question': 'Quiet culture and food'} )
    assert first.status_code == 200, first.text
    result = first.json()
    assert result['source'] == 'ollama' and result['cached'] is False
    assert result['ideas'][0]['verification_status'] == 'unverified'
    assert result['cloud_inference_used'] is False
    assert result['web_status'] == 'empty'
    assert model.count == 1
    again = client.post(url, headers=headers, json={'question': 'Quiet culture and food'}).json()
    assert again['id'] != result['id'] and again['cached'] is False
    assert model.count == 2
    assert client.get(url, headers=headers).json()['sets'][0]['id'] == again['id']
    assert model.count == 2
    new = client.post(url, headers=headers, json={'question': 'Quiet culture and food', 'refresh': True}).json()
    assert new['id'] != result['id'] and model.count == 3
    assert len(client.get(url, headers=headers).json()['sets']) == 3
    assert len(session.scalars(select(CityIdeaSet)).all()) == 3
    assert client.post(url, json={}).status_code == 401


def test_saved_ideas_are_trip_scoped_and_not_dependent_on_route_or_model_availability(client, monkeypatch):
    created, headers = trip(client)
    model = fake_model(monkeypatch)
    url = f"/api/v1/trips/{created['id']}/cities/bergen/ideas"
    result = client.post(url, headers=headers, json={}).json()
    assert result['source'] == 'ollama'
    # Saved versions remain readable after search configuration disappears.
    monkeypatch.setattr(get_settings(), 'searxng_base_url', None)
    other, other_headers = trip(client)
    assert client.get(f"/api/v1/trips/{other['id']}/cities/bergen/ideas", headers=other_headers).json()['sets'] == []
    assert client.get(url, headers=other_headers).status_code == 401
    assert client.get(url, headers=headers).json()['sets'][0]['id'] == result['id']
    assert model.count == 1


def test_delete_saved_ideas_is_scoped_authorized_and_does_not_generate(client, monkeypatch):
    created, headers = trip(client)
    model = fake_model(monkeypatch)
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    first = client.post(url, headers=headers, json={}).json()
    second = client.post(url, headers=headers, json={'refresh': True}).json()
    delete_url = f"{url}/{first['id']}"
    assert client.delete(delete_url).status_code == 401
    other, other_headers = trip(client)
    assert client.delete(delete_url, headers=other_headers).status_code == 401
    assert client.delete(f"/api/v1/trips/{other['id']}/cities/prague/ideas/{first['id']}", headers=other_headers).status_code == 404
    assert client.delete(f"/api/v1/trips/{created['id']}/cities/venice/ideas/{first['id']}", headers=headers).status_code == 404
    assert len(client.get(url, headers=headers).json()['sets']) == 2
    response = client.delete(delete_url, headers=headers)
    assert response.status_code == 204 and response.content == b''
    assert [item['id'] for item in client.get(url, headers=headers).json()['sets']] == [second['id']]
    assert client.delete(delete_url, headers=headers).status_code == 404
    assert model.count == 2
    assert client.delete(f"{url}/{second['id']}", headers=headers).status_code == 204
    assert client.get(url, headers=headers).json()['sets'] == []
    # Explicit generation after deletion must not resurrect the removed cache entry.
    new = client.post(url, headers=headers, json={}).json()
    assert new['id'] not in {first['id'], second['id']}
    assert model.count == 3


def test_fallback_is_saved_honestly_and_retry_is_explicit(client, monkeypatch):
    created, headers = trip(client)
    model = fake_model(monkeypatch, failing=True)
    url = f"/api/v1/trips/{created['id']}/cities/naxos/ideas"
    first = client.post(url, headers=headers, json={}).json()
    assert first['source'] == 'curated_fallback' and first['model'] is None
    assert first['ideas'] == [] and model.count == 2
    assert client.post(url, headers=headers, json={}).json()['id'] != first['id']
    assert model.count == 4
    client.post(url, headers=headers, json={'refresh': True})
    assert model.count == 6


def test_unknown_citations_fail_validation_instead_of_inventing_links(client, monkeypatch):
    created, headers = trip(client)
    model = fake_model(monkeypatch, unknown_sources=True)
    response = client.post(f"/api/v1/trips/{created['id']}/cities/prague/ideas", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()['source'] == 'curated_fallback' and model.count == 2
    assert all('invented-id' not in idea['source_ids'] for idea in response.json()['ideas'])


def test_specificity_prompt_allows_no_matches_instead_of_generic_filler(client, monkeypatch):
    created, headers = trip(client)
    class Model:
        answers = 0
        async def generate_structured(self, system, prompt, schema):
            if schema is SearchQuery:
                return SearchQuery(query='cat cafes in Prague')
            self.answers += 1
            assert 'Put the actual place name in the title' in system
            assert 'name at least two concrete stops' in system
            assert 'omit the walk entirely' in system
            assert 'return an empty ideas list' in system
            assert 'supporting quote naming the place' in system
            return city_ideas.Ideas(introduction='No named cat-related locations could be supported by the supplied results.', ideas=[])
    model = Model()
    monkeypatch.setattr(city_ideas, 'provider_for', lambda _: model)
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    response = client.post(url, headers=headers, json={'question': 'Something related to cats'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['source'] == 'ollama' and result['generation_status'] == 'generated'
    assert result['ideas'] == [] and model.answers == 1
    assert client.get(url, headers=headers).json()['sets'][0]['ideas'] == []


def test_web_off_and_invalid_requests_do_not_run_any_model_or_search(client, monkeypatch):
    created, headers = trip(client)
    monkeypatch.setattr(get_settings(), 'searxng_base_url', None)
    model = fake_model(monkeypatch)
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    assert client.post(url, headers=headers, json={}).json()['error']['code'] == 'WEB_SEARCH_NOT_CONFIGURED'
    for payload in [{'question': '  '}, {'question': 'x'*601}, {'use_web': False}, {'refresh_web': True}, {'url': 'http://localhost'}, {'model': 'qwen:cloud'}]:
        assert client.post(url, headers=headers, json=payload).status_code == 422
    assert model.count == 0
    assert model.plans == 0


def test_model_or_question_changes_create_separate_saved_versions(client, monkeypatch):
    created, headers = trip(client)
    model = fake_model(monkeypatch)
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    ids = []
    for payload in [{}, {'model': 'qwen3:8b'}, {'question': 'Nature walks and cafés'}]:
        response = client.post(url, headers=headers, json=payload)
        assert response.status_code == 200, response.text
        ids.append(response.json()['id'])
    assert len(set(ids)) == model.count == 3


def test_busy_generation_is_not_automatically_queued_or_retried(client):
    created, headers = trip(client)
    city_ideas.GENERATION_GATE.acquire()
    try:
        response = client.post(f"/api/v1/trips/{created['id']}/cities/prague/ideas", headers=headers, json={})
        assert response.status_code == 409 and response.json()['error']['code'] == 'AI_BUSY'
    finally:
        city_ideas.GENERATION_GATE.release()


@pytest.mark.parametrize('url', ['http://example.com', 'https://127.0.0.1/a', 'https://127.1/a', 'https://0x7f.0.0.1/a', 'https://localhost/a', 'https://host.internal/a', 'https://user:pass@example.com/a', 'javascript:alert(1)', 'https://example.com:9999/a'])
def test_private_or_unsafe_links_are_not_exposed_as_sources(url):
    assert public_link(url) is None


def test_web_query_is_bounded_fresh_and_excludes_private_trip_information(session):
    calls = []
    def respond(request):
        calls.append(request)
        assert request.url.path == '/search'
        assert request.url.params['q'] == 'things to do in Prague'
        assert request.url.params['format'] == 'json'
        return httpx.Response(200, json={'results': [
            {'title': '<b>Tourism guide</b>', 'url': 'https://example.com/prague', 'content': 'A short city guide excerpt.'},
            {'title': 'Duplicate', 'url': 'https://example.com/prague', 'content': 'Duplicate result.'},
            {'title': 'Private', 'url': 'https://127.0.0.1/secret', 'content': 'Do not fetch this.'},
        ]})
    provider = CitySearch(Settings(searxng_base_url='http://search:8080'), httpx.MockTransport(respond))
    city = SimpleNamespace(name='Prague', country_code='CZ')
    first = asyncio.run(provider.search(session, city))
    assert first['status'] == 'searched' and len(first['sources']) == 1
    assert first['sources'][0]['title'] == 'Tourism guide'
    assert asyncio.run(provider.search(session, city))['cached'] is False
    assert len(calls) == 2
    asyncio.run(provider.search(session, city))
    assert len(calls) == 3


def test_web_outage_or_redirect_is_not_followed_or_marked_researched(session):
    for handler in [lambda _: httpx.Response(302, headers={'location': 'https://example.com'}), lambda _: httpx.Response(503), lambda _: httpx.Response(200, content=b'x'*512001), lambda _: httpx.Response(200, json={'wrong': []})]:
        calls = []
        def respond(request):
            calls.append(request)
            return handler(request)
        provider = CitySearch(Settings(searxng_base_url='http://search:8080'), httpx.MockTransport(respond))
        result = asyncio.run(provider.search(session, SimpleNamespace(name='Prague', country_code='CZ')))
        assert result['status'] == 'unavailable' and result['sources'] == []
        assert len(calls) == 1


def test_model_query_is_used_verbatim_and_is_not_replayed_from_cache(session):
    calls = []
    def respond(request):
        calls.append(request.url.params['q'])
        return httpx.Response(200, json={'results': [
            {'title': 'Prague tourism', 'url': 'https://example.com/tourism', 'content': 'Castles and romantic walking tours.'},
            {'title': 'Synthetic Cat Café Prague', 'url': 'https://example.com/cats', 'content': 'Synthetic Cat Café is a cat café in Prague. A test fixture, not a real venue.'},
        ]})
    provider = CitySearch(Settings(searxng_base_url='http://search:8080'), httpx.MockTransport(respond))
    city = SimpleNamespace(name='Prague', country_code='CZ')
    query = 'cat activities in Prague'
    first = asyncio.run(provider.search(session, city, query=query))
    # No fixed topic filter: semantic relevance is assessed by the answering model.
    assert len(first['sources']) == 2
    assert 'cat' in first['query'] and 'private' not in first['query'] and '2027' not in first['query']
    assert not asyncio.run(provider.search(session, city, query=query))['cached']
    asyncio.run(provider.search(session, city, query='art galleries in Prague'))
    assert len(calls) == 3


def test_citations_require_known_sources_and_verbatim_supporting_quotes():
    source = {'id': 'w1', 'title': 'Synthetic Cat Café', 'excerpt': 'Synthetic Cat Café is a cat café in Prague.'}
    class Model:
        calls = 0
        def __init__(self, quote): self.quote = quote
        async def generate_structured(self, system, prompt, schema):
            self.calls += 1
            assert 'Never invent a venue' in system
            assert 'Ignore unrelated search results' in system
            result = output(['w1'])
            result.ideas[0].title = 'Synthetic Cat Café'
            result.ideas[0].description = 'A synthetic cat café for a quiet break in Prague.'
            if self.quote:
                result.ideas[0].evidence = [city_ideas.Evidence(source_id='w1', quote=self.quote)]
            return result
    prompt = {'sources': [source], 'research_focus': 'cat cafés'}
    for quote in [None, 'An invented quote about cats.']:
        model = Model(quote)
        assert asyncio.run(city_ideas.draft_ideas(model, prompt, {'w1'})) is None
        assert model.calls == 2
    assert asyncio.run(city_ideas.draft_ideas(Model(source['excerpt']), prompt, {'w1'})) is not None
    assert asyncio.run(city_ideas.draft_ideas(Model('cafe in PRAGUE.'), prompt, {'w1'})) is not None


def test_fun_query_is_natural_and_does_not_require_venues_to_say_fun(session):
    calls = []
    def respond(request):
        calls.append(request.url.params['q'])
        return httpx.Response(200, json={'results': [
            {'title': 'Synthetic puzzle room', 'url': 'https://example.com/puzzles', 'content': 'Solve puzzles together in a Paris escape room.'},
        ]})
    provider = CitySearch(Settings(searxng_base_url='http://search:8080'), httpx.MockTransport(respond))
    result = asyncio.run(provider.search(session, SimpleNamespace(name='Paris', country_code='FR'), query='fun things to do in Paris'))
    assert calls == ['fun things to do in Paris']
    assert len(result['sources']) == 1


def test_model_retry_receives_validation_feedback_and_preserves_valid_context():
    class Model:
        calls = 0
        async def generate_structured(self, system, prompt, schema):
            self.calls += 1
            data = json.loads(prompt)
            result = output(['w1'])
            result.ideas[0].title = 'Le Café des Chats · synthetic fixture'
            if self.calls == 1:
                assert 'validation_feedback' not in data
                return result
            assert 'previous answer was rejected' in data['validation_feedback'].lower()
            result.ideas[0].evidence = [city_ideas.Evidence(source_id='w1', quote='Enjoy a coffee together.')]
            return result
    prompt = {'research_focus': 'cat activities', 'sources': [{'id': 'w1', 'title': 'Le Café des Chats', 'excerpt': 'Enjoy a coffee together.'}]}
    model = Model()
    assert asyncio.run(city_ideas.draft_ideas(model, prompt, {'w1'})) is not None
    assert model.calls == 2


def test_failed_ai_answer_keeps_relevant_search_leads(client, monkeypatch):
    created, headers = trip(client)
    settings = get_settings()
    monkeypatch.setattr(settings, 'searxng_base_url', 'http://synthetic-search:8080')
    calls = []
    def respond(request):
        calls.append(request.url.params['q'])
        return httpx.Response(200, json={'results': [{'title': 'Synthetic Cat Café', 'url': 'https://example.com/cats', 'content': 'A synthetic cat cafe in Prague, not a real place.'}]})
    monkeypatch.setattr(city_ideas, 'search_provider', lambda: CitySearch(settings, httpx.MockTransport(respond)))
    fake_model(monkeypatch, unknown_sources=True, query='cat activities in Prague')
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    response = client.post(url, headers=headers, json={'question': 'Fun cat activities please'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert calls == ['cat activities in Prague']
    assert result['source'] == 'web_research' and result['generation_status'] == 'invalid_response'
    assert result['ideas'][0]['source_ids'] == ['w1']
    assert result['ideas'][0]['title'] == 'Research lead: Synthetic Cat Café'
    assert client.get(url, headers=headers).json()['sets'][0]['id'] == result['id']
    assert len(calls) == 1


def test_remote_alias_is_rejected_before_chat_call():
    calls = []
    def respond(request):
        calls.append(request.url.path)
        return httpx.Response(200, json={'remote_host': 'https://cloud.example', 'remote_model': 'remote'})
    provider = OllamaProvider(model='deceptively-local-alias', transport=httpx.MockTransport(respond))
    with pytest.raises(ValueError, match='Remote inference'):
        asyncio.run(provider.generate_structured('system', 'user', city_ideas.Ideas))
    assert calls == ['/api/show']


def test_city_web_generation_always_plans_and_searches_but_history_does_not(client, session, monkeypatch):
    created, headers = trip(client)
    settings = get_settings()
    monkeypatch.setattr(settings, 'searxng_base_url', 'http://synthetic-search:8080')
    requests = []
    def respond(request):
        requests.append(request)
        assert 'private' not in str(request.url)
        return httpx.Response(200, json={'results': [{'title': 'Tourism reference', 'url': 'https://example.com/guide', 'content': 'A synthetic travel guide excerpt for testing.'}]})
    provider = CitySearch(settings, httpx.MockTransport(respond))
    monkeypatch.setattr(city_ideas, 'search_provider', lambda: provider)
    model = fake_model(monkeypatch)
    url = f"/api/v1/trips/{created['id']}/cities/prague/ideas"
    payload = {'question': 'private favourite-food preferences'}
    first = client.post(url, headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert first.json()['web_used'] and first.json()['web_status'] == 'searched'
    assert len(requests) == 1 and model.count == 1
    assert model.plans == 1
    assert any(source['id'] == 'w1' for source in first.json()['sources'])
    again = client.post(url, headers=headers, json=payload).json()
    assert not again['cached'] and again['id'] != first.json()['id']
    client.get(url, headers=headers)
    assert len(requests) == model.count == 2
    assert model.plans == 2
    second = client.post(url, headers=headers, json={**payload, 'refresh': True}).json()
    assert not second['web_cached'] and model.count == 3 and len(requests) == 3
    assert model.plans == 3
    assert len(client.get(url, headers=headers).json()['sets']) == 3
    assert len(requests) == 3 and model.plans == 3


def test_deleting_trip_removes_private_saved_ideas(client, session, monkeypatch):
    created, headers = trip(client)
    fake_model(monkeypatch)
    client.post(f"/api/v1/trips/{created['id']}/cities/prague/ideas", headers=headers, json={})
    assert session.scalar(select(CityIdeaSet)) is not None
    assert client.delete(f"/api/v1/trips/{created['id']}", headers=headers).status_code == 204
    assert session.scalar(select(CityIdeaSet)) is None
