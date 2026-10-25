import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from app.providers.city_search import CitySearch, validated_query
from app.services.city_query import SearchQuery, plan_query
from app.services import city_ideas

CITY = SimpleNamespace(name='Paris', country_code='FR')


@pytest.mark.parametrize('question,query', [
    ('just something fun', 'fun things to do in Paris'),
    ('cat activities please', 'cat cafes in Paris'),
    ('learn bookbinding together', 'bookbinding workshops in Paris'),
    ('urban beekeeping experiences', 'urban beekeeping experiences in Paris'),
])
def test_general_local_query_planner_preserves_arbitrary_interests(question, query):
    class Model:
        async def generate_structured(self, system, prompt, schema):
            assert schema is SearchQuery
            assert 'targeted and concise web search query' in system
            assert 'untrusted DATA' in system
            assert json.loads(prompt) == {'city': 'Paris', 'country': 'FR', 'question': question, 'research_focus': ''}
            return SearchQuery(query=query)
    result = asyncio.run(plan_query(Model(), CITY, question))
    assert result['source'] == 'local_model' and result['query'] == query


def test_planner_redacts_common_identifiers_and_passes_explicit_focus_locally():
    class Model:
        async def generate_structured(self, system, prompt, schema):
            for private in ['2027-06-01', 'person@example.com', 'https://private.example/token', '12345678-1234-4234-9234-123456789abc']:
                assert private not in prompt
            assert json.loads(prompt)['research_focus'] == 'glassblowing classes'
            return SearchQuery(query='glassblowing classes in Paris')
    result = asyncio.run(plan_query(Model(), CITY,
        '2027-06-01 person@example.com https://private.example/token 12345678-1234-4234-9234-123456789abc something fun',
        'glassblowing classes'))
    assert result['query'] == 'glassblowing classes in Paris'


@pytest.mark.parametrize('query', [
    'cat cafes in London', 'https://example.com Paris', 'site:example.com Paris',
    'cat cafes in Paris person@example.com', 'Paris 2027-06-01',
    'Paris 123 Main Street', 'Paris 12345678-1234-4234-9234-123456789abc',
    'Paris !g secret', 'private.example.com Paris',
    'Paris ' + 'word '*25,
])
def test_invalid_or_private_planned_queries_use_city_only_fallback(query):
    class Model:
        async def generate_structured(self, *args): return SearchQuery(query=query)
    result = asyncio.run(plan_query(Model(), CITY, 'private question'))
    assert result['source'] == 'city_fallback' and result['status'] == 'invalid_response'
    assert result['query'] == 'things to do in Paris'


def test_planner_outage_is_reported_without_forwarding_question():
    class Model:
        async def generate_structured(self, *args): raise httpx.ConnectError('private provider diagnostic')
    result = asyncio.run(plan_query(Model(), CITY, 'a private request'))
    assert result['status'] == 'unavailable' and result['query'] == 'things to do in Paris'
    assert 'private' not in json.dumps(result)


def test_only_supplied_years_are_allowed_and_exact_dates_remain_blocked():
    assert validated_query('summer activities in Paris June 2027', CITY, [2027]).endswith('2027')
    for query in ['Paris June 2028', 'Paris June 12 2027', 'Paris 2027-06-12']:
        with pytest.raises(ValueError): validated_query(query, CITY, [2027])


def test_search_provider_also_rejects_unvalidated_queries(session):
    from app.core.config import Settings
    calls = []
    provider = CitySearch(Settings(searxng_base_url='http://synthetic-search:8080'),
        httpx.MockTransport(lambda request: calls.append(request)))
    with pytest.raises(ValueError):
        asyncio.run(provider.search(session, CITY, query='Paris user@example.com'))
    assert calls == []


def test_planning_timeout_keeps_the_workflow_bounded_and_labels_generic_query(client, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'searxng_base_url', 'http://synthetic-search:8080')
    monkeypatch.setattr(settings, 'llm_timeout_seconds', .09)
    monkeypatch.setattr(settings, 'ai_web_timeout_seconds', .03)
    stages = []
    class Model:
        async def generate_structured(self, system, prompt, schema):
            if schema is SearchQuery:
                stages.append('plan')
                await asyncio.sleep(1)
            stages.append('answer')
            return city_ideas.Ideas(introduction='Unverified local suggestions.', ideas=[city_ideas.Idea(
                title='A neighbourhood walk', description='Explore the city at your own pace.',
                why_for_you='A relaxed option.', time_minutes=60, best_time='flexible', source_ids=[])])
    monkeypatch.setattr(city_ideas, 'provider_for', lambda _: Model())
    def respond(request):
        stages.append('search')
        assert request.url.params['q'] == 'things to do in Paris'
        return httpx.Response(200, json={'results': []})
    monkeypatch.setattr(city_ideas, 'search_provider', lambda: CitySearch(settings, httpx.MockTransport(respond)))
    trip = client.post('/api/v1/trips', json={}).json()
    response = client.post(f"/api/v1/trips/{trip['id']}/cities/paris/ideas", headers={'X-Edit-Token': trip['edit_token']}, json={})
    assert response.status_code == 200, response.text
    assert response.json()['query_plan']['status'] == 'timeout'
    assert response.json()['query_plan']['source'] == 'city_fallback'
    assert stages == ['plan', 'search', 'answer']


def test_same_selected_model_plans_then_answers_and_history_skips_both(client, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'searxng_base_url', 'http://synthetic-search:8080')
    stages, models = [], []
    class Model:
        async def generate_structured(self, system, prompt, schema):
            data = json.loads(prompt)
            if schema is SearchQuery:
                stages.append('plan')
                assert set(data) == {'city', 'country', 'question', 'research_focus'}
                return SearchQuery(query='bookbinding classes in Paris')
            stages.append('answer')
            assert data['search_query'] == 'bookbinding classes in Paris'
            assert data['sources'][0]['excerpt'] == 'Synthetic paper studio offers bookbinding classes.'
            return city_ideas.Ideas(introduction='A source-backed starting point.', ideas=[city_ideas.Idea(
                title='Synthetic paper studio', description='Try a bookbinding class together; verify details directly.',
                why_for_you='A hands-on craft experience.', time_minutes=120, best_time='flexible', source_ids=['w1'],
                evidence=[city_ideas.Evidence(source_id='w1', quote=data['sources'][0]['excerpt'])])])
    instance = Model()
    monkeypatch.setattr(city_ideas, 'provider_for', lambda model: models.append(model) or instance)
    def respond(request):
        stages.append('search')
        assert request.url.params['q'] == 'bookbinding classes in Paris'
        return httpx.Response(200, json={'results': [{'title': 'Synthetic paper studio', 'url': 'https://example.com/paper', 'content': 'Synthetic paper studio offers bookbinding classes.'}]})
    monkeypatch.setattr(city_ideas, 'search_provider', lambda: CitySearch(settings, httpx.MockTransport(respond)))
    trip = client.post('/api/v1/trips', json={}).json()
    url = f"/api/v1/trips/{trip['id']}/cities/paris/ideas"
    headers = {'X-Edit-Token': trip['edit_token']}
    body = {'question': 'Learn bookbinding together', 'model': 'qwen3:14b'}
    response = client.post(url, headers=headers, json=body)
    assert response.status_code == 200, response.text
    assert stages == ['plan', 'search', 'answer'] and models == ['qwen3:14b']
    assert response.json()['query_plan']['model'] == 'qwen3:14b'
    client.get(url, headers=headers)
    assert stages == ['plan', 'search', 'answer']
    repeated = client.post(url, headers=headers, json=body).json()
    assert not repeated['cached'] and repeated['id'] != response.json()['id']
    assert stages == ['plan', 'search', 'answer'] * 2
    assert models == ['qwen3:14b'] * 2
