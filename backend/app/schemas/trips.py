from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Preferences(Contract):
    interests: list[str] = Field(default_factory=lambda: ["culture", "food"], max_length=20)
    pace: Literal["relaxed", "balanced", "fast"] = "balanced"
    final_stay_nights: int = Field(default=4, ge=0, le=30)
    # Accepted for saved-trip/API compatibility only; no routing effect.
    max_daily_travel_hours: float | None = Field(default=None, ge=1, le=16, deprecated=True)
    endpoint_id: str | None = None
    endpoint_region: Literal["southern_italy", "southern_france", "spain", "croatia", "greece", "islands", "any"] = "southern_italy"

class Budget(Contract):
    total: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    final_stay: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="NOK", pattern=r"^[A-Z]{3}$")

class PassDetails(Contract):
    type: Literal["global", "one_country"] = "global"
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    validity_type: Literal["flexi", "continuous"] = "flexi"
    travel_days_total: int | None = Field(default=7, ge=1, le=90)
    travel_days_used: int = Field(default=0, ge=0, le=90)
    valid_from: date | None = None
    valid_until: date | None = None
    travel_class: Literal[1, 2] = 2

    @model_validator(mode="after")
    def valid_pass(self):
        if self.type == "one_country" and not self.country_code:
            raise ValueError("A One Country pass needs country_code")
        if self.travel_days_total is not None and self.travel_days_used > self.travel_days_total:
            raise ValueError("Used travel days exceed the pass total")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError("Pass validity dates are reversed")
        return self

class TripRequest(Contract):
    total_days: int = Field(default=21, ge=2, le=90)
    start_date: date | None = None
    date_mode: Literal["flexible", "exact"] = "flexible"
    required_stops: list[str] = Field(default_factory=list, max_length=90)
    preferred_stops: list[str] = Field(default_factory=list, max_length=90)
    preferences: Preferences = Field(default_factory=Preferences)
    budget: Budget = Field(default_factory=Budget)
    pass_details: PassDetails = Field(default_factory=PassDetails, alias="pass")

    @model_validator(mode="after")
    def valid_trip(self):
        if self.date_mode == "exact" and not self.start_date:
            raise ValueError("An exact-date trip requires start_date")
        if self.date_mode == "flexible" and self.start_date:
            raise ValueError("Use exact date_mode when providing start_date")
        if len(set(self.required_stops)) != len(self.required_stops):
            raise ValueError("Required stops must be unique")
        if "oslo" in self.required_stops:
            raise ValueError("Oslo is already the fixed starting city")
        if self.preferences.final_stay_nights >= self.total_days:
            raise ValueError("Final stay must leave time for the journey")
        return self

class EditRequest(Contract):
    expected_revision: int = Field(ge=1)
    operation: Literal["set_nights", "add_stop", "remove_stop", "reorder_stop", "lock_stop", "change_endpoint", "set_leg_plan", "set_journey", "clear_leg_plan"]
    destination_id: str
    nights: int | None = Field(default=None, ge=0, le=89)
    position: int | None = Field(default=None, ge=1)
    locked: bool | None = None
    remove_required: bool = False
    expected_trip_revision: int | None = Field(default=None, ge=1)
    leg_index: int | None = Field(default=None, ge=0)
    journey_id: UUID | None = None

    @model_validator(mode="after")
    def explicit_required_removal(self):
        if self.remove_required and (self.operation != "remove_stop" or self.expected_trip_revision is None):
            raise ValueError("Removing a must-see requires remove_stop and the current trip revision")
        if self.operation in {"set_leg_plan", "set_journey", "clear_leg_plan"} and self.leg_index is None:
            raise ValueError("Choose the outgoing leg index")
        if self.operation == "set_journey" and not self.journey_id:
            raise ValueError("Choose a journey returned by a timetable search")
        if self.journey_id is not None and self.operation != "set_journey":
            raise ValueError("journey_id is only valid for set_journey")
        return self

class TripPatch(Contract):
    expected_revision: int = Field(ge=1)
    total_days: int | None = Field(default=None, ge=2, le=90)
    start_date: date | None = None
    date_mode: Literal["flexible", "exact"] | None = None
    required_stops: list[str] | None = Field(default=None, max_length=90)
    preferred_stops: list[str] | None = Field(default=None, max_length=90)
    preferences: Preferences | None = None
    budget: Budget | None = None
    pass_details: PassDetails | None = Field(default=None, alias="pass")
