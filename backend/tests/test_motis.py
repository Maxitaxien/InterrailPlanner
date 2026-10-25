import asyncio
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.providers.motis import MotisTimetables, coverage_report
from app.schemas.integrations import RailTimetableRequest

ORIGIN = SimpleNamespace(latitude=53.55, longitude=10.0, country_code="DE")
DESTINATION = SimpleNamespace(latitude=48.14, longitude=11.58, country_code="DE")
REQUEST = RailTimetableRequest(origin_id="hamburg", destination_id="munich", departure_date=date(2026, 10, 20))


def response_plan(**extra):
    leg = {"mode": "LONG_DISTANCE", "startTime": "2026-10-20T06:01:00Z", "endTime": "2026-10-20T12:01:00Z", "duration": 21600,
           "from": {"name": "Hamburg Hbf", "lat": 53.55, "lon": 10, "tz": "Europe/Berlin"},
           "to": {"name": "München Hbf", "lat": 48.14, "lon": 11.58, "tz": "Europe/Berlin"},
           "agencyName": "DB", "displayName": "ICE 123", **extra}
    return {"itineraries": [{"startTime": leg["startTime"], "endTime": leg["endTime"], "duration": 21600, "transfers": 0, "legs": [leg]}]}


def run(handler, request=REQUEST, origin=ORIGIN):
    settings = Settings(motis_base_url="http://motis:8080")
    return asyncio.run(MotisTimetables(settings, httpx.MockTransport(handler)).search(request, origin, DESTINATION))


def test_motis_sends_origin_local_time_and_rail_only_parameters():
    def handler(request):
        assert request.url.path == "/api/v6/plan"
        assert request.url.params["time"] == "2026-10-20T08:00:00+02:00"
        assert request.url.params["radius"] == "3000"
        assert request.url.params["directModes"] == ""
        assert "BUS" not in request.url.params["transitModes"]
        return httpx.Response(200, json=response_plan(reservationRequired=False))
    result = run(handler)
    assert result["status"] == "scheduled"
    assert result["journeys"][0]["duration_minutes"] == 360
    assert result["journeys"][0]["legs"][0]["train"] == "ICE 123"
    assert result["price"] is None and result["reservation_status"] == "unknown"
    assert result["journeys"][0]["legs"][0]["reservation_status"] == "unknown"
    assert result["checked_at"]


@pytest.mark.parametrize("extra", [{"cancelled": True}, {"loopedCalendarSince": "2026-10-01T00:00:00Z"}, {"mode": "BUS"}, {"mode": "WALK"}])
def test_motis_does_not_offer_cancelled_extrapolated_or_nonrail_journeys(extra):
    result = run(lambda _: httpx.Response(200, json=response_plan(**extra)))
    assert result["status"] == "no_journeys" and result["journeys"] == []
    assert "does not mean no rail route" in result["message"]


@pytest.mark.parametrize("payload", [{}, {"itineraries": [{}]}, {"itineraries": None}, response_plan(startTime="2026-10-20T08:00:00")])
def test_malformed_motis_is_unavailable_not_no_route(payload):
    assert run(lambda _: httpx.Response(200, json=payload))["status"] == "unavailable"


def test_motis_timeout_redirect_and_empty_results():
    def timeout(request): raise httpx.ReadTimeout("offline", request=request)
    for handler in [timeout, lambda _: httpx.Response(503), lambda _: httpx.Response(302, headers={"Location": "https://example.com"})]:
        result = run(handler)
        assert result["status"] == "unavailable" and result["checked_at"] is None
    assert run(lambda _: httpx.Response(200, json={"itineraries": []}))["status"] == "no_journeys"


def test_disabled_motis_never_makes_a_request():
    def forbidden(_): raise AssertionError("No network expected")
    settings = Settings(motis_base_url=None)
    result = asyncio.run(MotisTimetables(settings, httpx.MockTransport(forbidden)).search(REQUEST, ORIGIN, DESTINATION))
    assert result["status"] == "not_configured"


def test_prepared_source_metadata_is_not_called_import_verification(tmp_path):
    import json
    from app.providers.motis import feed_sources
    path = tmp_path / "feeds-status.json"
    path.write_text(json.dumps({"feeds": [{"id": "de", "name": "Test feed", "sha256": "abc", "secret_download_url": "hidden"}]}))
    settings = Settings(motis_feed_status_path=str(path))
    sources = feed_sources(settings)
    assert sources[0]["name"] == "Test feed"
    assert "secret_download_url" not in sources[0]
    assert "verified" not in sources[0]
    path.write_text("broken")
    assert feed_sources(settings) == []


def test_oversized_response_is_unavailable():
    assert run(lambda _: httpx.Response(200, content=b" " * 2_000_001))["status"] == "unavailable"


@pytest.mark.parametrize("day,hour", [("2026-03-29", "02:30"), ("2026-10-25", "02:30")])
def test_dst_gap_and_overlap_require_an_unambiguous_time(day, hour):
    def forbidden(_): raise AssertionError("No network expected")
    request = RailTimetableRequest(origin_id="hamburg", destination_id="munich", departure_date=day, departure_time=hour)
    assert run(forbidden, request)["status"] == "invalid_local_time"


def test_timetable_endpoint_validation_and_disabled_provider(client, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "motis_base_url", None)
    base = {"origin_id": "hamburg", "destination_id": "munich", "departure_date": "2026-10-20"}
    assert client.post("/api/v1/travel/rail/timetables", json=base).json()["status"] == "not_configured"
    for change in [{"origin_id": "missing"}, {"departure_date": None}, {"destination_id": "hamburg"}, {"departure_time": "08:00+02:00"}, {"url": "http://example.com"}]:
        assert client.post("/api/v1/travel/rail/timetables", json={**base, **change}).status_code == 422


def prepared_settings(tmp_path, feeds):
    import json
    path = tmp_path / 'feeds-status.json'
    path.write_text(json.dumps({'feeds': feeds}))
    return Settings(motis_base_url='http://motis:8080', motis_feed_status_path=str(path))


def test_coverage_is_local_advisory_not_proof_of_connectivity(tmp_path):
    settings = prepared_settings(tmp_path, [{'id': 'de', 'name': 'Synthetic', 'rail_trip_count': 2, 'rail_service_start': '2026-10-01', 'rail_service_end': '2026-10-31', 'city_stop_counts': {'hamburg': 1, 'munich': 1, 'oslo': 0}, 'secret_download_url': 'hidden'}])
    report = coverage_report(settings, 'hamburg', 'munich', date(2026, 10, 20))
    assert report['status'] == 'prepared_candidates'
    assert report['import_verified'] is False
    assert report['sources'][0]['date_status'] == 'within_envelope'
    assert 'secret_download_url' not in report['sources'][0]
    assert coverage_report(settings, 'oslo', 'munich', date(2026, 10, 20))['status'] == 'missing_prepared_stops'
    assert coverage_report(settings, 'newcity', 'munich', date(2026, 10, 20))['status'] == 'not_audited'
    assert coverage_report(settings, 'hamburg', 'munich', date(2027, 6, 1))['status'] == 'outside_prepared_dates'
    assert coverage_report(settings, 'hamburg', 'munich')['sources'][0]['date_status'] == 'not_checked'


def test_longer_norwegian_calendar_does_not_extend_german_coverage(tmp_path):
    settings = prepared_settings(tmp_path, [
        {'id': 'de', 'rail_trip_count': 2, 'rail_service_start': '2026-10-01', 'rail_service_end': '2026-10-31', 'city_stop_counts': {'hamburg': 1, 'munich': 1, 'oslo': 0}},
        {'id': 'no', 'rail_trip_count': 2, 'rail_service_start': '2026-10-01', 'rail_service_end': '2027-02-01', 'city_stop_counts': {'hamburg': 0, 'munich': 0, 'oslo': 1}},
    ])
    report = coverage_report(settings, 'hamburg', 'munich', date(2027, 1, 1))
    assert report['status'] == 'endpoint_dates_missing'


def test_old_or_malformed_metadata_does_not_claim_audited_coverage(tmp_path):
    settings = prepared_settings(tmp_path, [{'id': 'old', 'service_start': '2026-10-01', 'service_end': '2027-01-01', 'rail_service_start': 123, 'rail_service_end': 'invalid'}])
    report = coverage_report(settings, 'hamburg', 'munich', date(2026, 10, 20))
    assert report['status'] == 'not_audited'
    assert report['sources'][0]['date_status'] == 'unknown'


def test_prepared_out_of_range_date_does_not_block_running_motis(tmp_path):
    settings = prepared_settings(tmp_path, [{'id': 'old', 'rail_trip_count': 1, 'rail_service_start': '2020-01-01', 'rail_service_end': '2020-01-02'}])
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response_plan())
    result = asyncio.run(MotisTimetables(settings, httpx.MockTransport(handler)).search(REQUEST, ORIGIN, DESTINATION))
    assert len(calls) == 1 and result['status'] == 'scheduled'
    assert result['coverage']['status'] == 'outside_prepared_dates'


def test_coverage_endpoint_validates_cities_without_contacting_motis(client, monkeypatch, tmp_path):
    from app.core.config import get_settings
    settings = prepared_settings(tmp_path, [])
    monkeypatch.setattr(get_settings(), 'motis_base_url', settings.motis_base_url)
    monkeypatch.setattr(get_settings(), 'motis_feed_status_path', settings.motis_feed_status_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('Coverage endpoint must not contact a timetable service')
    monkeypatch.setattr(httpx.AsyncClient, 'stream', forbidden)
    response = client.post('/api/v1/travel/rail/coverage', json={'origin_id': 'oslo', 'destination_id': 'bergen'})
    assert response.status_code == 200 and response.json()['status'] == 'no_metadata'
    assert client.post('/api/v1/travel/rail/coverage', json={'origin_id': 'missing', 'destination_id': 'bergen'}).status_code == 422
