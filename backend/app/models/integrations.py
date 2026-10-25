from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.entities import Json, now, uid

class Attraction(Base):
    __tablename__ = "attractions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"), index=True)
    name: Mapped[str]
    category: Mapped[str]
    interest_tags: Mapped[list] = mapped_column(Json)
    description: Mapped[str]
    source: Mapped[str]

class AICache(Base):
    __tablename__ = "ai_cache"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    input_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model_name: Mapped[str]
    prompt_version: Mapped[str]
    output_json: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class TravelRulesCache(Base):
    __tablename__ = "travel_rules_cache"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lookup_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_url: Mapped[str]
    content_json: Mapped[dict] = mapped_column(Json)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source_version: Mapped[str]

class ExternalRequest(Base):
    __tablename__ = "external_requests"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    provider: Mapped[str]
    request_type: Mapped[str]
    status: Mapped[str]
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    error_code: Mapped[str | None]

class RailJourneySnapshot(Base):
    __tablename__ = "rail_journey_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    origin_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"))
    destination_id: Mapped[str] = mapped_column(ForeignKey("destinations.id"))
    journey_json: Mapped[dict] = mapped_column(Json)
    sources_json: Mapped[list] = mapped_column(Json)
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

class CityIdeaSet(Base):
    __tablename__ = 'city_idea_sets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    trip_id: Mapped[str] = mapped_column(ForeignKey('trips.id', ondelete='CASCADE'), index=True)
    destination_id: Mapped[str] = mapped_column(ForeignKey('destinations.id'))
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    request_json: Mapped[dict] = mapped_column(Json)
    result_json: Mapped[dict] = mapped_column(Json)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class CityWebCache(Base):
    __tablename__ = 'city_web_cache'
    query_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_json: Mapped[dict] = mapped_column(Json)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
