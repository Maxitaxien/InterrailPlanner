"""Read-only adapter for our own MOTIS v2.11.3 (plan API v6).

City coordinates + radius work without OSM; the radius is not a station match
or a guarantee of coverage. Never interpret MOTIS reservation defaults as
Interrail entitlement or seat inventory.
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import json
from pathlib import Path

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings

TIMEZONES = {
    "NO": "Europe/Oslo", "SE": "Europe/Stockholm", "DK": "Europe/Copenhagen",
    "DE": "Europe/Berlin", "IT": "Europe/Rome", "AT": "Europe/Vienna",
    "CH": "Europe/Zurich", "FR": "Europe/Paris", "ES": "Europe/Madrid",
    "PT": "Europe/Lisbon", "GB": "Europe/London", "IE": "Europe/Dublin",
    "NL": "Europe/Amsterdam", "BE": "Europe/Brussels", "LU": "Europe/Luxembourg",
    "CZ": "Europe/Prague", "PL": "Europe/Warsaw", "HU": "Europe/Budapest",
    "SK": "Europe/Bratislava", "SI": "Europe/Ljubljana", "HR": "Europe/Zagreb",
    "GR": "Europe/Athens", "RO": "Europe/Bucharest", "BG": "Europe/Sofia",
    "FI": "Europe/Helsinki", "EE": "Europe/Tallinn", "LV": "Europe/Riga",
    "LT": "Europe/Vilnius", "RS": "Europe/Belgrade", "BA": "Europe/Sarajevo",
    "ME": "Europe/Podgorica", "MK": "Europe/Skopje",
}
RAIL_MODES = {"RAIL", "HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_RAIL", "REGIONAL_FAST_RAIL", "SUBURBAN"}
NOTICE = "Published timetable only, not a booking or confirmation of Interrail validity. Reservations, supplements and seats must be checked separately."


def feed_sources(settings):
    if not settings.motis_feed_status_path:
        return []
    try:
        feeds = json.loads(Path(settings.motis_feed_status_path).read_text())["feeds"]
        if not isinstance(feeds, list) or not all(isinstance(feed, dict) for feed in feeds):
            raise ValueError("Invalid prepared feed metadata")
        # This records prepared inputs, not proof of what the running server loaded.
        return [{k: feed.get(k) for k in ("id", "name", "source_url", "license_url", "attribution", "coverage", "downloaded_at", "service_start", "service_end", "rail_service_start", "rail_service_end", "rail_route_count", "rail_trip_count", "rail_stop_count", "city_stop_counts", "city_radius_meters", "sha256")} for feed in feeds]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def coverage_report(settings, origin_id, destination_id, departure_date=None):
    """Local preparation diagnostics only. Never veto a query to the running engine."""
    sources = feed_sources(settings)
    day = departure_date.isoformat() if departure_date else None
    assessed = []
    for source in sources:
        # Old metadata has only an all-mode envelope; retain it as explicitly unknown.
        start, end = source.get("rail_service_start"), source.get("rail_service_end")
        date_status = "not_checked" if not day else "unknown"
        if source.get("rail_trip_count") == 0:
            date_status = "no_rail_trips"
        elif day and isinstance(start, str) and isinstance(end, str):
            try:
                first, last = date.fromisoformat(start), date.fromisoformat(end)
                if first <= last:
                    date_status = "within_envelope" if first <= departure_date <= last else "outside_envelope"
            except ValueError:
                pass
        counts = source.get("city_stop_counts")
        def city_status(city):
            if not isinstance(counts, dict) or city not in counts:
                return "not_audited"
            return "present" if isinstance(counts[city], int) and counts[city] > 0 else "absent"
        assessed.append({**source, "date_status": date_status,
                         "origin_stops": city_status(origin_id), "destination_stops": city_status(destination_id)})
    def endpoint_status(key, inputs=None):
        values = [source[key] for source in (assessed if inputs is None else inputs)]
        return "present" if "present" in values else "not_audited" if not values or "not_audited" in values else "absent"
    origin_status, destination_status = endpoint_status("origin_stops"), endpoint_status("destination_stops")
    dated_sources = [source for source in assessed if source["date_status"] not in {"outside_envelope", "no_rail_trips"}]
    if not settings.motis_base_url:
        status, message = "not_configured", "Self-hosted timetables are not configured. Prepare feeds, import them and start MOTIS."
    elif not sources:
        status, message = "no_metadata", "Prepared feed metadata is unavailable. You can still search the running MOTIS server."
    elif day and all(source["date_status"] in {"outside_envelope", "no_rail_trips"} for source in assessed):
        status, message = "outside_prepared_dates", "Your date is outside every prepared rail calendar envelope. Newer timetables may not be published yet; check or refresh the feeds."
    elif "absent" in (origin_status, destination_status):
        status, message = "missing_prepared_stops", "Prepared feeds have no audited rail stops within 3 km of one or both cities. More feed coverage or a different station may be needed."
    elif day and any(endpoint_status(key, dated_sources) == "absent" for key in ("origin_stops", "destination_stops")):
        status, message = "endpoint_dates_missing", "A city's prepared rail stops appear only in feeds outside your search date. The other feeds' longer calendars do not extend this city's coverage."
    elif "not_audited" in (origin_status, destination_status):
        status, message = "not_audited", "These inputs have not been audited for both cities. Run feed preparation again to add city and rail-calendar diagnostics."
    else:
        status, message = "prepared_candidates", "Prepared feeds contain rail stops near both cities. Only a dated search can establish whether a connecting journey is available."
    return {"status": status, "message": message, "configured": bool(settings.motis_base_url),
            "origin_stops": origin_status, "destination_stops": destination_status,
            "departure_date": day, "sources": assessed, "import_verified": False,
            "notice": "Prepared files are not proof of what the running MOTIS server imported. Calendar envelopes can contain gaps; nearby stops do not prove a rail connection. Search remains available."}


class Place(BaseModel):
    name: str
    lat: float
    lon: float
    stopId: str | None = None
    tz: str | None = None


class Leg(BaseModel):
    mode: str
    startTime: datetime
    endTime: datetime
    duration: int = Field(ge=0)
    from_: Place = Field(alias="from")
    to: Place
    agencyName: str | None = None
    displayName: str | None = None
    routeShortName: str | None = None
    tripShortName: str | None = None
    tripId: str | None = None
    realTime: bool = False
    cancelled: bool = False
    loopedCalendarSince: str | None = None
    interlineWithPreviousLeg: bool = False


class Journey(BaseModel):
    startTime: datetime
    endTime: datetime
    duration: int = Field(ge=0)
    transfers: int = Field(ge=0)
    legs: list[Leg] = Field(min_length=1)


class Plan(BaseModel):
    itineraries: list[Journey]


class MotisTimetables:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport

    async def search(self, request, origin, destination):
        zone = TIMEZONES.get(origin.country_code)
        base = {"provider": "self-hosted-motis", "journeys": [], "notice": NOTICE,
                "checked_at": None, "origin_timezone": zone, "reservation_status": "unknown", "price": None,
                "prepared_sources": feed_sources(self.settings),
                "coverage": coverage_report(self.settings, request.origin_id, request.destination_id, request.departure_date)}
        if not self.settings.motis_base_url:
            return {**base, "status": "not_configured", "message": "Self-hosted timetables are not enabled yet. Import feeds and start the MOTIS Docker service."}
        if not zone:
            return {**base, "status": "unsupported_origin", "message": "The origin timezone has not been configured. No timetable search was made."}
        # Reject DST gaps/ambiguous times rather than silently picking a train an hour off.
        naive = datetime.combine(request.departure_date, request.departure_time)
        local = naive.replace(tzinfo=ZoneInfo(zone))
        if local.astimezone(timezone.utc).astimezone(ZoneInfo(zone)).replace(tzinfo=None) != naive or local.utcoffset() != local.replace(fold=1).utcoffset():
            return {**base, "status": "invalid_local_time", "message": "This local time is ambiguous or skipped by a daylight-saving change. Choose another departure time."}
        params = {
            "fromPlace": f"{origin.latitude},{origin.longitude}",
            "toPlace": f"{destination.latitude},{destination.longitude}",
            "radius": 3000, "time": local.isoformat(),
            "transitModes": "HIGHSPEED_RAIL,LONG_DISTANCE,NIGHT_RAIL,REGIONAL_RAIL,SUBURBAN",
            "directModes": "", "numItineraries": 3, "maxItineraries": 3,
            "minTransferTime": 10, "detailedLegs": "false", "timetableView": "true",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.motis_timeout_seconds, transport=self.transport, follow_redirects=False) as client:
                async with client.stream("GET", self.settings.motis_base_url.rstrip("/") + "/api/v6/plan", params=params) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise ValueError("MOTIS response too large")
            plan = Plan.model_validate_json(raw)
            journeys = []
            for journey in plan.itineraries:
                if not any(leg.mode in RAIL_MODES for leg in journey.legs):
                    continue
                if any(leg.cancelled or leg.loopedCalendarSince or leg.mode not in RAIL_MODES | {"WALK"} for leg in journey.legs):
                    continue
                if any(value.tzinfo is None for value in [journey.startTime, journey.endTime, *[v for leg in journey.legs for v in (leg.startTime, leg.endTime)]]):
                    raise ValueError("MOTIS returned times without offsets")
                journeys.append({
                    "departure": journey.startTime.isoformat(), "arrival": journey.endTime.isoformat(),
                    "duration_minutes": round(journey.duration / 60), "transfers": journey.transfers,
                    "legs": [{"mode": leg.mode, "origin": leg.from_.name, "destination": leg.to.name,
                              "origin_timezone": leg.from_.tz or zone, "destination_timezone": leg.to.tz,
                              "departure": leg.startTime.isoformat(), "arrival": leg.endTime.isoformat(),
                              "operator": leg.agencyName, "train": leg.displayName or leg.tripShortName or leg.routeShortName,
                              "trip_id": leg.tripId, "train_number": leg.tripShortName,
                              "real_time": leg.realTime, "stay_seated": leg.interlineWithPreviousLeg,
                              "reservation_status": "unknown"} for leg in journey.legs],
                })
            return {**base, "checked_at": datetime.now(timezone.utc).isoformat(), "journeys": journeys[:3],
                    "status": "scheduled" if journeys else "no_journeys",
                    "message": "Departures from imported timetable feeds; walking access is estimated within 3 km of each city centre." if journeys else "No journeys found in the imported feeds for this search. Coverage may be missing, dates may be unpublished, or stations may be outside the 3 km search radius. This does not mean no rail route exists."}
        except (httpx.HTTPError, ValidationError, ValueError, TypeError):
            return {**base, "status": "unavailable", "message": "MOTIS could not complete this search. Check the service, feed coverage, imported date range and API version; your estimated itinerary is unchanged."}
