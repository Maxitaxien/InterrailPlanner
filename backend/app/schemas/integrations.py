from datetime import date, time, datetime
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.schemas.trips import Contract

class ModelRequest(Contract):
    model: str | None = Field(default=None, max_length=100, pattern=r"^[a-zA-Z0-9_.:/-]+$")

class CityIdeasRequest(ModelRequest):
    question: str = Field(default='A relaxed honeymoon day with good food, culture and a few quieter spots.', min_length=3, max_length=600)
    research_focus: str = Field(default='', max_length=120)
    refresh: bool = False
    itinerary_id: UUID | None = None

    @model_validator(mode='after')
    def trimmed_question(self):
        self.question = self.question.strip()
        if len(self.question) < 3:
            raise ValueError('Describe the city ideas you would like')
        return self
class FlightSearch(Contract):
    origin_airport: str = Field(pattern=r"^[A-Z]{3}$")
    departure_date: date | None = None
    departure_date_end: date | None = None
    trip_type: Literal["one_way"] = "one_way"
    adults: int = Field(ge=1, le=9)
    currency: str = Field(default="NOK", pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def valid_departure_range(self):
        if self.departure_date_end:
            if not self.departure_date or self.departure_date_end < self.departure_date:
                raise ValueError("Choose a departure range with the latest date on or after the first date")
            if (self.departure_date_end - self.departure_date).days > 30:
                raise ValueError("Compare up to 31 departure dates at a time")
        return self
class HotelSearch(Contract):
    destination_id: str
    check_in: date | None = None
    check_out: date | None = None
    adults: int = Field(ge=1, le=30)
    rooms: int = Field(ge=1, le=15)
    currency: str = Field(default="NOK", pattern=r"^[A-Z]{3}$")
class RailRulesRequest(Contract):
    topic: Literal["reservations", "countries"] = "reservations"

class RailCoverageRequest(Contract):
    origin_id: str = Field(min_length=1, max_length=64)
    destination_id: str = Field(min_length=1, max_length=64)
    departure_date: date | None = None

class RailTimetableRequest(Contract):
    origin_id: str = Field(min_length=1, max_length=64)
    destination_id: str = Field(min_length=1, max_length=64)
    departure_date: date
    departure_time: time = time(8)

    @model_validator(mode="after")
    def valid_search(self):
        if self.origin_id == self.destination_id:
            raise ValueError("Choose different origin and destination cities")
        if self.departure_time.tzinfo is not None:
            raise ValueError("Departure time must be local to the origin, without an offset")
        return self

class RailBookingRequest(Contract):
    origin_id: str = Field(min_length=1, max_length=64)
    destination_id: str = Field(min_length=1, max_length=64)
    via: list[str] = Field(default_factory=list, max_length=500)
    departure_date: date | None = None
    adults: int = Field(default=2, ge=1, le=9)
    travel_class: Literal[1, 2] = 2
    ticket_mode: Literal["pass", "tickets"] = "pass"

    @model_validator(mode="after")
    def correct_endpoints(self):
        if self.via and (self.via[0] != self.origin_id or self.via[-1] != self.destination_id):
            raise ValueError("Via must include the origin first and destination last")
        return self


class RailLocationSearch(Contract):
    city_id: str = Field(min_length=1, max_length=64)

class ExternalRailSearch(Contract):
    origin_id: str = Field(min_length=1, max_length=64)
    destination_id: str = Field(min_length=1, max_length=64)
    origin_uid: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    destination_uid: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    departure_date: date

    @model_validator(mode="after")
    def different_locations(self):
        if self.origin_id == self.destination_id or self.origin_uid == self.destination_uid:
            raise ValueError("Choose different origin and destination locations")
        return self


class EndpointComparisonRequest(Contract):
    origin_id: str = Field(default="bari", min_length=1, max_length=64)
    endpoint_ids: list[str] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def unique_endpoints(self):
        if len(set(self.endpoint_ids)) != len(self.endpoint_ids):
            raise ValueError("Choose different endpoints")
        return self


class ConnectionCheckRequest(Contract):
    connection_id: str = Field(min_length=1, max_length=128)
    arrival_at_start: datetime | None = None
    ferry_departure: datetime
    ferry_arrival: datetime
    onward_departure: datetime | None = None
    onward_check_in_minutes: int = Field(default=30, ge=0, le=360)
    onward_transfer_minutes: int = Field(default=0, ge=0, le=1440)
    ferry_check_in_minutes: int | None = Field(default=None, ge=0, le=360)
    port_access_minutes: int | None = Field(default=None, ge=0, le=720)
