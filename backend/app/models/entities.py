import uuid
from datetime import datetime, timezone, date
from decimal import Decimal
from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

Json = JSON().with_variant(JSONB, "postgresql")
def now(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())

class Destination(Base):
    __tablename__ = "destinations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str]
    country_code: Mapped[str] = mapped_column(String(2))
    latitude: Mapped[float]
    longitude: Mapped[float]
    category: Mapped[str]
    interest_tags: Mapped[list] = mapped_column(Json)
    suggested_nights: Mapped[int]
    is_endpoint: Mapped[bool] = mapped_column(default=False)
    airport: Mapped[str | None]
    __table_args__ = (CheckConstraint("suggested_nights >= 0"),)

class RailConnection(Base):
    __tablename__ = "rail_connections"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    origin_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), index=True)
    estimated_minutes: Mapped[int]
    transfers: Mapped[int] = mapped_column(default=0)
    service_type: Mapped[str]
    night_train: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str]
    estimate_quality: Mapped[str]
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_warning: Mapped[str | None]
    __table_args__ = (CheckConstraint("estimated_minutes > 0"), CheckConstraint("transfers >= 0"))

class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    edit_token_hash: Mapped[str] = mapped_column(String(64))
    start_city_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), default="oslo")
    total_days: Mapped[int]
    start_date: Mapped[date | None]
    date_mode: Mapped[str]
    request: Mapped[dict] = mapped_column(Json)
    total_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    final_stay_budget: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    itineraries: Mapped[list["Itinerary"]] = relationship(cascade="all, delete-orphan", back_populates="trip")
    pass_record: Mapped["TripPass"] = relationship(cascade="all, delete-orphan", uselist=False)
    __table_args__ = (CheckConstraint("total_days >= 2"), CheckConstraint("total_budget IS NULL OR total_budget >= 0"), CheckConstraint("final_stay_budget IS NULL OR final_stay_budget >= 0"))

class TripPass(Base):
    __tablename__ = "trip_passes"
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), primary_key=True)
    details: Mapped[dict] = mapped_column(Json)

class Itinerary(Base):
    __tablename__ = "itineraries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    name: Mapped[str]
    score: Mapped[float]
    revision: Mapped[int] = mapped_column(default=1)
    is_selected: Mapped[bool] = mapped_column(default=False)
    result: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    trip: Mapped[Trip] = relationship(back_populates="itineraries")
    stops: Mapped[list["TripStop"]] = relationship(cascade="all, delete-orphan")
    legs: Mapped[list["TripLeg"]] = relationship(cascade="all, delete-orphan")

class TripStop(Base):
    __tablename__ = "trip_stops"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    itinerary_id: Mapped[str] = mapped_column(ForeignKey("itineraries.id", ondelete="CASCADE"), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), index=True)
    position: Mapped[int]
    arrival_day: Mapped[int]
    departure_day: Mapped[int]
    arrival_date: Mapped[date | None]
    departure_date: Mapped[date | None]
    nights: Mapped[int]
    is_required: Mapped[bool]
    is_locked: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("itinerary_id", "position"), CheckConstraint("nights >= 0"), CheckConstraint("departure_day >= arrival_day"))

class TripLeg(Base):
    __tablename__ = "trip_legs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    itinerary_id: Mapped[str] = mapped_column(ForeignKey("itineraries.id", ondelete="CASCADE"), index=True)
    from_stop_id: Mapped[str] = mapped_column(ForeignKey("trip_stops.id", ondelete="CASCADE"))
    to_stop_id: Mapped[str] = mapped_column(ForeignKey("trip_stops.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(default="rail")
    estimated_minutes: Mapped[int]
    departure_day: Mapped[int]
    travel_days_estimate: Mapped[int] = mapped_column(default=1)
    verification_status: Mapped[str] = mapped_column(default="needs_verification")
    __table_args__ = (CheckConstraint("estimated_minutes > 0"),)
