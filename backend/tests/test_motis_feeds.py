import importlib.util
import json
import io
from pathlib import Path
from zipfile import ZipFile, BadZipFile

import pytest

spec = importlib.util.spec_from_file_location("motis_prepare", Path(__file__).resolve().parents[2] / "motis" / "prepare.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def manifest(tmp_path):
    with ZipFile(tmp_path / "input.zip", "w") as archive:
        for name, text in {
            "agency.txt": "agency_name,agency_url,agency_timezone\nTest,https://example.com,Europe/Berlin\n",
            "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\na,A,53,10\nb,B,48,11\n",
            "routes.txt": "route_id,route_type\nr,2\n", "trips.txt": "route_id,service_id,trip_id\nr,s,t\n",
            "stop_times.txt": "trip_id,stop_id,stop_sequence,arrival_time,departure_time\nt,a,1,08:00:00,08:00:00\nt,b,2,14:00:00,14:00:00\n",
            "calendar_dates.txt": "service_id,date,exception_type\ns,20261020,1\ns,20261022,1\ns,20261023,2\n",
        }.items(): archive.writestr(name, text)
    feed = {"id": "test", "name": "Synthetic test fixture", "path": "input.zip", "source_url": "https://example.com", "license_url": "https://example.com/license", "attribution": "Test only", "coverage": "No real service"}
    path = tmp_path / "feeds.json"
    path.write_text(json.dumps({"feeds": [feed]}))
    return path, feed


def test_preparation_records_provenance_and_never_extends_calendars(tmp_path):
    path, _ = manifest(tmp_path)
    work = tmp_path / "work"
    records = prepare.prepare(path, work)
    assert records[0]["service_start"] == "2026-10-20"
    assert records[0]["service_end"] == "2026-10-22"
    assert len(records[0]["sha256"]) == 64
    config = json.loads((work / "config.yml").read_text())
    assert config["timetable"]["datasets"]["test"] == {"path": "feeds/test.zip", "extend_calendar": False}
    assert not config["street_routing"] and not config["geocoding"]


def test_bad_feed_preserves_prepared_configuration(tmp_path):
    path, feed = manifest(tmp_path)
    work = tmp_path / "work"
    prepare.prepare(path, work)
    old = (work / "config.yml").read_bytes(), (work / "feeds/test.zip").read_bytes()
    (tmp_path / "input.zip").write_bytes(b"not a zip")
    with pytest.raises(BadZipFile): prepare.prepare(path, work)
    assert old == ((work / "config.yml").read_bytes(), (work / "feeds/test.zip").read_bytes())


@pytest.mark.parametrize("changes", [{"id": "bad_tag"}, {"license_url": ""}, {"path": None, "url": "http://example.com/feed.zip"}])
def test_unreviewed_and_unsafe_manifest_rejected(tmp_path, changes):
    path, feed = manifest(tmp_path)
    path.write_text(json.dumps({"feeds": [{**feed, **changes}]}))
    with pytest.raises(ValueError): prepare.prepare(path, tmp_path / "work")


def test_rail_calendar_and_city_audit_excludes_bus_only_stops(tmp_path):
    path, _ = manifest(tmp_path)
    source = tmp_path / "input.zip"
    with ZipFile(source) as archive:
        tables = {name: archive.read(name).decode() for name in archive.namelist()}
    tables['routes.txt'] += 'bus,3\n'
    tables['trips.txt'] += 'bus,bs,bt\n'
    tables['stops.txt'] += 'c,Bus stop,50,12\n'
    tables['stop_times.txt'] += 'bt,c,1,08:00:00,08:00:00\n'
    tables['calendar_dates.txt'] += 'bs,20280101,1\n'
    with ZipFile(source, 'w') as archive:
        for name, contents in tables.items():
            archive.writestr(name, contents)
    cities = [{'id': 'railcity', 'latitude': 53, 'longitude': 10}, {'id': 'buscity', 'latitude': 50, 'longitude': 12}, {'id': 'faraway', 'latitude': 60, 'longitude': 10}]
    audit = prepare.audit(source, cities)
    assert audit['rail_trip_count'] == 1 and audit['trip_count'] == 2
    assert audit['rail_route_count'] == 1 and audit['rail_stop_count'] == 2
    assert audit['service_end'] == '2028-01-01'
    assert audit['rail_service_end'] == '2026-10-22'
    assert audit['city_stop_counts'] == {'railcity': 1, 'buscity': 0, 'faraway': 0}


def test_extra_manifests_merge_without_dropping_existing_feeds(tmp_path):
    path, feed = manifest(tmp_path)
    extra_dir = tmp_path / 'other'
    extra_dir.mkdir()
    extra_path, extra_feed = manifest(extra_dir)
    extra_path.write_text(json.dumps({'feeds': [{**extra_feed, 'id': 'second'}]}))
    records = prepare.prepare(path, tmp_path / 'work', extra_manifests=[extra_path])
    assert [record['id'] for record in records] == ['test', 'second']
    config = json.loads((tmp_path / 'work/config.yml').read_text())
    assert set(config['timetable']['datasets']) == {'test', 'second'}
    # Duplicate identities are rejected before downloads or configuration replacement.
    extra_path.write_text(json.dumps({'feeds': [feed]}))
    with pytest.raises(ValueError):
        prepare.prepare(path, tmp_path / 'work', extra_manifests=[extra_path])


def test_download_identification_and_cache_respect_publisher_interval(tmp_path, monkeypatch):
    path, feed = manifest(tmp_path)
    raw = (tmp_path / 'input.zip').read_bytes()
    remote = {**feed, 'url': 'https://example.com/feed.zip', 'headers': {'ET-Client-Name': 'interrailhelper-test'}, 'min_download_interval_hours': 24}
    remote.pop('path')
    path.write_text(json.dumps({'feeds': [remote]}))
    requests = []
    def download(request, timeout):
        requests.append(request)
        assert request.get_header('Et-client-name') == 'interrailhelper-test'
        stream = io.BytesIO(raw)
        stream.url = 'https://example.com/feed.zip'
        return stream
    monkeypatch.setattr(prepare, 'urlopen', download)
    work = tmp_path / 'work'
    first = prepare.prepare(path, work)
    second = prepare.prepare(path, work)
    assert len(requests) == 1
    assert first[0]['downloaded_at'] == second[0]['downloaded_at']
    (work / 'feeds/test.zip').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='missing or changed'):
        prepare.prepare(path, work)
    assert len(requests) == 1  # Do not bypass the publisher interval after cache damage.


@pytest.mark.parametrize('changes', [{'headers': {'Authorization': 'secret'}}, {'headers': {'ET-Client-Name': 'bad\r\nheader'}}, {'min_download_interval_hours': -1}])
def test_credentials_and_invalid_refresh_policy_are_rejected(tmp_path, changes):
    path, feed = manifest(tmp_path)
    path.write_text(json.dumps({'feeds': [{**feed, **changes}]}))
    with pytest.raises(ValueError):
        prepare.prepare(path, tmp_path / 'work')


@pytest.mark.parametrize('filename', [
    'feeds.france.json', 'feeds.denmark.example.json',
    'feeds.austria.example.json', 'feeds.switzerland.example.json',
])
def test_expansion_manifests_merge_with_defaults_using_synthetic_data(tmp_path, monkeypatch, filename):
    """Exercise shipped metadata/configs without contacting any provider."""
    root = Path(__file__).resolve().parents[2] / 'motis'
    manifest(tmp_path)
    raw = (tmp_path / 'input.zip').read_bytes()
    expansion = json.loads((root / filename).read_text())
    feed = expansion['feeds'][0]
    if feed.get('path'):
        local = tmp_path / feed['path']
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(raw)
    extra = tmp_path / filename
    extra.write_text(json.dumps(expansion))
    requests = []

    def download(request, timeout):
        requests.append(request.full_url)
        stream = io.BytesIO(raw)
        stream.url = request.full_url
        return stream

    monkeypatch.setattr(prepare, 'urlopen', download)
    records = prepare.prepare(root / 'feeds.json', tmp_path / 'work', extra_manifests=[extra])
    default_ids = {item['id'] for item in json.loads((root / 'feeds.json').read_text())['feeds']}
    assert {record['id'] for record in records} == default_ids | {feed['id']}
    assert len(requests) == len(default_ids) + int('url' in feed)
    record = next(item for item in records if item['id'] == feed['id'])
    for key in ('name', 'source_url', 'license_url', 'attribution', 'coverage'):
        assert record[key] == feed[key]
    assert record['rail_service_end'] == '2026-10-22'
    config = json.loads((tmp_path / 'work/config.yml').read_text())
    assert all(not dataset['extend_calendar'] for dataset in config['timetable']['datasets'].values())


def test_missing_optional_archive_preserves_prepared_config(tmp_path, monkeypatch):
    path, _ = manifest(tmp_path)
    work = tmp_path / 'work'
    prepare.prepare(path, work)
    before = {name: (work / name).read_bytes() for name in ('config.yml', 'feeds-status.json', 'feeds/test.zip')}
    root = Path(__file__).resolve().parents[2] / 'motis'
    extra = tmp_path / 'denmark.json'
    extra.write_text((root / 'feeds.denmark.example.json').read_text())
    monkeypatch.setattr(prepare, 'urlopen', lambda *a, **kw: pytest.fail('Local archive must not trigger network access'))
    with pytest.raises(FileNotFoundError):
        prepare.prepare(path, work, extra_manifests=[extra])
    assert before == {name: (work / name).read_bytes() for name in before}
