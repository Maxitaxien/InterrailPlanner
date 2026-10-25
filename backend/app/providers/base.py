from typing import Protocol
from pydantic import BaseModel, Field
class SearchResult(BaseModel):
    provider: str
    status: str
    offers: list[dict]
    search_url: str
    retrieved_at: str | None = None
    currency: str
    notice: str
    trip_type: str | None = None
    search_links: list[dict] = Field(default_factory=list)
class FlightProvider(Protocol):
    async def search(self, request) -> SearchResult: ...
class AccommodationProvider(Protocol):
    async def search(self, request) -> SearchResult: ...
class RailRulesProvider(Protocol):
    async def lookup(self, topic: str) -> dict: ...
