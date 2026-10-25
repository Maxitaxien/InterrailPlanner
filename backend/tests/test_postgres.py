"""Opt-in PostgreSQL tests. TEST_DATABASE_URL must point to a disposable test database."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.database import get_db
from app.main import app
from app.scripts.seed_data import seed

pytestmark = pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'), reason='Set TEST_DATABASE_URL to an isolated PostgreSQL test database')

@pytest.fixture
def postgres_client():
    url = os.environ['TEST_DATABASE_URL']
    assert url.startswith('postgresql+psycopg://'), 'Use the psycopg PostgreSQL driver for integration tests'
    schema = 'interrail_test_' + uuid4().hex
    admin = create_engine(url)
    scoped = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA {schema}'))
        scoped = create_engine(url, connect_args={'options': f'-csearch_path={schema}'})
        backend = Path(__file__).resolve().parents[1]
        config = Config(str(backend / 'alembic.ini'))
        config.set_main_option('script_location', str(backend / 'migrations'))
        with scoped.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
            command.check(config)
        sessions = sessionmaker(scoped, expire_on_commit=False)
        with sessions() as db: seed(db)
        def override():
            with sessions() as db: yield db
        app.dependency_overrides[get_db] = override
        with TestClient(app) as client:
            yield client, scoped
    finally:
        app.dependency_overrides.clear()
        if scoped: scoped.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()

def test_postgres_migrations_persistence_and_jsonb(postgres_client):
    client, engine = postgres_client
    created = client.post('/api/v1/trips',json={'required_stops':['prague','venice'],'budget':{'total':'30000.50'}})
    assert created.status_code == 201, created.text
    trip = created.json()
    headers = {'X-Edit-Token':trip['edit_token']}
    result = client.post(f"/api/v1/trips/{trip['id']}/generate",headers=headers)
    assert result.status_code == 200, result.text
    assert len(client.get(f"/api/v1/trips/{trip['id']}").json()['itineraries']) == 3
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT data_type FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = 'trips' AND column_name = 'request'")) == 'jsonb'
        assert str(connection.scalar(text('SELECT total_budget FROM trips WHERE id = :id'), {'id':trip['id']})) == '30000.50'
    assert client.delete(f"/api/v1/trips/{trip['id']}",headers=headers).status_code == 204
    with engine.connect() as connection:
        assert connection.scalar(text('SELECT count(*) FROM trip_stops')) == 0
        assert connection.scalar(text('SELECT count(*) FROM trip_legs')) == 0

def test_postgres_concurrent_edit_has_one_winner(postgres_client):
    client, _ = postgres_client
    trip = client.post('/api/v1/trips',json={'required_stops':['prague','venice']}).json()
    headers = {'X-Edit-Token':trip['edit_token']}
    route = client.post(f"/api/v1/trips/{trip['id']}/generate",headers=headers).json()[0]
    def edit():
        return client.patch(f"/api/v1/itineraries/{route['id']}",headers=headers,json={'expected_revision':1,'operation':'set_nights','destination_id':'prague','nights':5}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: edit(), range(2)))
    assert sorted(statuses) == [200,409]
