"""Explicit schedule research using the public All Aboard GraphQL contract.

No offers, mutations, retries, background requests or persisted provider results.
DateTime is documented as station-local and naive; keep it as such. These
results cannot become MOTIS snapshots until timezone and storage rights are known.
Contract reviewed: https://docs.allaboard.eu/ref/types (17 October 2026).
"""
from datetime import datetime, timezone
from uuid import uuid4
from typing import Literal
import json

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings

LOCATIONS = """query Locations($filter: LocationsFilter!) {
  locations(filter: $filter, first: 10) {
    edges { node { uid name countryCode isMeta } }
  }
}"""
JOURNEYS = """query Journeys($origin: LocationInput!, $destination: LocationInput!, $date: Date!) {
  journeys(origin: $origin, destination: $destination, date: $date,
           filter: {types: [NON_STOP]}) {
    id status itinerary {
      __typename
      ... on SegmentCollection { segments {
        origin { name } destination { name }
        departureAt arrivalAt transport identifier operator { name }
      } }
      ... on Stopover { location { name } duration }
    }
  }
}"""
NOTICE = "Station-local timetable research only. Seats, pass acceptance and reservations are unverified. Results are not saved or applied to your itinerary."


class ProviderError(ValueError):
    pass


class Location(BaseModel):
    uid: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=300)
    countryCode: str = Field(pattern=r"^[A-Z]{2}$")
    isMeta: bool


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=300)


class Segment(BaseModel):
    origin: Named
    destination: Named
    departureAt: str = Field(max_length=40, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
    arrivalAt: str = Field(max_length=40, pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
    transport: Literal["NIGHT_TRAIN", "TRAIN", "BUS", "FERRY", "NIGHT_BUS"]
    identifier: str | None = Field(default=None, max_length=100)
    operator: Named

    def checked(self):
        departure = datetime.fromisoformat(self.departureAt)
        arrival = datetime.fromisoformat(self.arrivalAt)
        # Naive station-local times can go backwards across timezones. Do not
        # invent an elapsed duration or offset from the origin city's timezone.
        if departure.tzinfo or arrival.tzinfo:
            if not departure.tzinfo or not arrival.tzinfo or arrival < departure:
                raise ValueError("Inconsistent provider times")
        return self.model_dump()


class AllAboardTimetables:
    def __init__(self, settings=None, transport=None):
        self.settings = settings or get_settings()
        self.transport = transport

    def readiness(self):
        key = self.settings.allaboard_api_key
        configured = bool(key and key.get_secret_value().strip())
        return {"provider": "allaboard", "configured": configured,
                "enabled": self.settings.allaboard_enabled,
                "environment": self.settings.allaboard_environment,
                "status": "ready" if configured and self.settings.allaboard_enabled else "not_configured"}

    async def query(self, query, variables):
        if self.readiness()['status'] != 'ready':
            raise ProviderError("All Aboard is disabled or missing its server-side key.")
        host = "api-gateway.allaboard.eu" if self.settings.allaboard_environment == "live" else "test.api-gateway.allaboard.eu"
        headers = {"api-key": self.settings.allaboard_api_key.get_secret_value(),
                   "session": str(uuid4()), "Accept": "application/graphql-response+json"}
        try:
            async with httpx.AsyncClient(timeout=self.settings.allaboard_timeout_seconds,
                                         transport=self.transport, follow_redirects=False) as client:
                async with client.stream("POST", f"https://{host}/graphql", headers=headers,
                                         json={"query": query, "variables": variables}) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000:
                            raise ValueError("Response too large")
            payload = json.loads(raw)
            if not isinstance(payload, dict) or payload.get('errors') or not isinstance(payload.get('data'), dict):
                raise ValueError("Invalid GraphQL response")
            return payload['data']
        except (httpx.HTTPError, ValueError, TypeError):
            # Never return provider errors, URLs, headers or exception strings.
            raise ProviderError("All Aboard could not complete this request. Check access, environment and provider status; no automatic retry was made.") from None

    async def locations(self, city):
        base = {**self.readiness(), "locations": []}
        if base['status'] != 'ready':
            return {**base, "message": "All Aboard requires approved access, enablement and a server-side API key."}
        try:
            data = await self.query(LOCATIONS, {"filter": {
                "countryCode": city.country_code,
                "near": {"type": "Point", "coordinates": [city.longitude, city.latitude]},
                "radius": 10000}})
            nodes = [Location.model_validate(edge['node']) for edge in data['locations']['edges']]
            nodes = [node for node in nodes if node.countryCode == city.country_code]
            nodes.sort(key=lambda node: not node.isMeta)
            return {**base, "status": "ok", "locations": [node.model_dump() for node in nodes],
                    "message": "Choose a city or station. Nearby locations do not establish journey coverage."}
        except (ProviderError, ValidationError, KeyError, TypeError, ValueError):
            return {**base, "status": "unavailable", "message": "Provider locations could not be loaded. Check API access and environment."}

    async def search(self, request):
        base = {**self.readiness(), "journeys": [], "checked_at": None, "notice": NOTICE,
                "persistent_storage": False, "reservation_status": "unknown", "price": None}
        if base['status'] != 'ready':
            return {**base, "message": "All Aboard requires approved access, enablement and a server-side API key."}
        try:
            data = await self.query(JOURNEYS, {"origin": {"uid": request.origin_uid},
                                    "destination": {"uid": request.destination_uid},
                                    "date": request.departure_date.isoformat()})
            if not isinstance(data['journeys'], list):
                raise ValueError("Invalid journeys")
            journeys, pending, rejected = [], False, False
            for item in data['journeys']:
                if item['status'] != 'SUCCESS':
                    pending = pending or item['status'] == 'LOADING'
                    rejected = rejected or item['status'] != 'LOADING'
                    continue
                segments = []
                # Do not silently discard a stopover or turn a bus/ferry into rail.
                if not item['itinerary'] or any(part['__typename'] != 'SegmentCollection' for part in item['itinerary']):
                    rejected = True
                    continue
                for part in item['itinerary']:
                    if not part['segments']:
                        raise ValueError("Incomplete journey")
                    segments.extend(Segment.model_validate(value).checked() for value in part['segments'])
                journeys.append({"segments": segments})
            status = 'scheduled' if journeys else 'pending' if pending else 'unavailable' if rejected else 'no_journeys'
            return {**base, "status": status, "journeys": journeys[:10],
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "message": {"scheduled": "Provider departures; station-local times as supplied. No prices or seats queried.",
                                "pending": "The provider is still resolving journeys. Search again explicitly later.",
                                "unavailable": "The provider returned incomplete or unsupported journeys.",
                                "no_journeys": "No provider journeys returned. Access, publication dates or coverage may be limited."}[status]}
        except (ProviderError, ValidationError, KeyError, TypeError, ValueError):
            return {**base, "status": "unavailable", "message": "Provider journeys could not be validated. Check access and try again explicitly."}
