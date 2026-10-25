import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
from urllib.error import HTTPError
from zipfile import ZipFile

import pytest

# The standalone tools intentionally have no app/settings/.env dependency.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import download_sweden as downloader

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
FAKE_KEY = 'synthetic-key-for-tests-only'


@pytest.fixture
def feed_bytes():
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as archive:
        for name, contents in {
            'agency.txt': 'agency_name,agency_url,agency_timezone\nFixture,https://example.com,Europe/Stockholm\n',
            'stops.txt': 'stop_id,stop_name,stop_lat,stop_lon\na,A,59.3,18.0\nb,B,57.7,12.0\n',
            'routes.txt': 'route_id,route_type\nr,2\n',
            'trips.txt': 'route_id,service_id,trip_id\nr,s,t\n',
            'stop_times.txt': 'trip_id,stop_id,stop_sequence\nt,a,1\nt,b,2\n',
            'calendar_dates.txt': 'service_id,date,exception_type\ns,20261020,1\n',
        }.items():
            archive.writestr(name, contents)
    return stream.getvalue()


def forbidden(*args, **kwargs):
    raise AssertionError('Unexpected credential read or network request')


def fake_opener(payload, calls):
    def open_url(request, timeout):
        calls.append(request)
        assert timeout == 60
        return io.BytesIO(payload)
    return open_url


def test_default_does_not_fetch_or_read_any_key_file(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader, 'read_key', forbidden)
    with pytest.raises(downloader.DownloadError, match='--refresh'):
        downloader.download(tmp_path, env_file=tmp_path / 'never-read', open_url=forbidden)


def test_explicit_download_is_saved_and_default_reuses_without_credentials(tmp_path, feed_bytes, monkeypatch):
    calls = []
    first = downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fake_opener(feed_bytes, calls), now=NOW)
    assert first['status'] == 'downloaded' and first['requests_made'] == 1
    assert first['local_attempts_last_30_days'] == 1
    assert (tmp_path / 'sweden.zip').read_bytes() == feed_bytes
    assert FAKE_KEY not in (tmp_path / 'sweden-status.json').read_text()
    assert FAKE_KEY.encode() not in (tmp_path / 'trafiklab-requests.sqlite3').read_bytes()
    monkeypatch.setattr(downloader, 'read_key', forbidden)
    # The saved archive remains usable when old or offline; no automatic refresh.
    cached = downloader.download(tmp_path, now=NOW + timedelta(days=40), open_url=forbidden)
    assert cached['status'] == 'cached' and cached['requests_made'] == 0
    fresh = downloader.download(tmp_path, refresh=True, now=NOW + timedelta(hours=2), open_url=forbidden)
    assert fresh['status'] == 'cached' and len(calls) == 1


def test_refresh_after_one_day_is_one_new_explicit_request(tmp_path, feed_bytes):
    calls = []
    for day in [0, 2]:
        result = downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fake_opener(feed_bytes, calls), now=NOW + timedelta(days=day))
        assert result['requests_made'] == 1
    assert result['local_attempts_last_30_days'] == 2
    assert len(calls) == 2


def test_http_errors_are_redacted_counted_and_not_retried(tmp_path, capsys):
    calls = []
    def fail(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 403, 'secret upstream response', {}, None)
    with pytest.raises(downloader.DownloadError) as caught:
        downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fail, now=NOW)
    assert len(calls) == 1
    assert FAKE_KEY not in str(caught.value) and 'secret upstream' not in str(caught.value)
    with sqlite3.connect(tmp_path / 'trafiklab-requests.sqlite3') as db:
        assert db.execute('SELECT COUNT(*), SUM(succeeded) FROM attempts').fetchone() == (1, 0)
    with pytest.raises(downloader.DownloadError, match='60 seconds'):
        downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=forbidden, now=NOW + timedelta(seconds=30))
    assert FAKE_KEY not in capsys.readouterr().out


def test_failed_validation_keeps_previous_archive_and_metadata(tmp_path, feed_bytes):
    downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fake_opener(feed_bytes, []), now=NOW)
    previous = (tmp_path / 'sweden-status.json').read_bytes()
    with pytest.raises(downloader.DownloadError, match='validation failed'):
        downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fake_opener(b'not a gtfs zip', []), now=NOW + timedelta(days=2))
    assert (tmp_path / 'sweden.zip').read_bytes() == feed_bytes
    assert (tmp_path / 'sweden-status.json').read_bytes() == previous


def test_rolling_quota_includes_failures_and_preserves_history(tmp_path):
    with sqlite3.connect(tmp_path / 'trafiklab-requests.sqlite3') as db:
        db.execute('CREATE TABLE attempts (id INTEGER PRIMARY KEY, attempted_at REAL NOT NULL, succeeded INTEGER NOT NULL DEFAULT 0)')
        db.executemany('INSERT INTO attempts (attempted_at) VALUES (?)', [(NOW.timestamp() - 1000 - i,) for i in range(50)])
    with pytest.raises(downloader.DownloadError, match='50 download attempts'):
        downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=forbidden, now=NOW)


def test_quota_attempts_older_than_30_days_expire(tmp_path, feed_bytes):
    with sqlite3.connect(tmp_path / 'trafiklab-requests.sqlite3') as db:
        db.execute('CREATE TABLE attempts (id INTEGER PRIMARY KEY, attempted_at REAL NOT NULL, succeeded INTEGER NOT NULL DEFAULT 0)')
        db.executemany('INSERT INTO attempts (attempted_at) VALUES (?)', [(NOW.timestamp() - 31 * downloader.DAY,) for _ in range(50)])
    result = downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fake_opener(feed_bytes, []), now=NOW)
    assert result['local_attempts_last_30_days'] == 1


def test_damaged_cache_does_not_bypass_daily_guard(tmp_path, feed_bytes):
    downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=fake_opener(feed_bytes, []), now=NOW)
    (tmp_path / 'sweden.zip').write_bytes(b'changed')
    with pytest.raises(downloader.DownloadError, match='cache is damaged'):
        downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=forbidden, now=NOW + timedelta(hours=2))


def test_redirects_are_not_followed():
    with pytest.raises(downloader.DownloadError, match='redirect blocked'):
        downloader.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')


@pytest.mark.parametrize('assignment', [
    'TRAFIKLAB_GTFS_API_KEY=synthetic-key-for-tests-only',
    'export TRAFIKLAB_GTFS_API_KEY="synthetic-key-for-tests-only" # test',
    "TRAFIKLAB_GTFS_API_KEY='synthetic-key-for-tests-only'",
])
def test_literal_key_file_parsing_only_uses_synthetic_fixture(tmp_path, assignment):
    path = tmp_path / 'synthetic-key-config.txt'
    path.write_text('OTHER_VALUE=$(never-execute-this)\n' + assignment + '\n')
    assert downloader.read_key(path, {}) == FAKE_KEY
    assert downloader.read_key(tmp_path / 'not-read', {downloader.KEY_NAME: FAKE_KEY}) == FAKE_KEY


def test_invalid_key_is_rejected_without_network(tmp_path):
    with pytest.raises(downloader.DownloadError, match='valid TRAFIKLAB'):
        downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: 'bad\r\nkey'}, open_url=forbidden, now=NOW)


def test_busy_ledger_makes_no_provider_request(tmp_path):
    with sqlite3.connect(tmp_path / 'trafiklab-requests.sqlite3') as db:
        db.execute('CREATE TABLE attempts (id INTEGER PRIMARY KEY, attempted_at REAL NOT NULL, succeeded INTEGER NOT NULL DEFAULT 0)')
        db.execute('BEGIN IMMEDIATE')
        with pytest.raises(downloader.DownloadError, match='busy or unavailable'):
            downloader.download(tmp_path, refresh=True, environ={downloader.KEY_NAME: FAKE_KEY}, open_url=forbidden, now=NOW)
