from uuid import UUID
from types import SimpleNamespace
from fastapi import FastAPI, Depends, Header, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import get_db
from app.core.security import issue_token, token_matches
from app.models.entities import Destination, RailConnection, Trip, TripPass, Itinerary, TripStop
from app.models.integrations import Attraction
from app.models.integrations import RailJourneySnapshot
from datetime import datetime, timezone
from app.schemas.trips import TripRequest, EditRequest, TripPatch
from app.services.errors import PlanningError
from app.services.route_engine.graph import RailGraph
from app.services.route_engine.generator import generate, build_path, score_route
from app.services.scheduler import schedule
from app.services.trip_service import serialize, persist_result, edit_itinerary
from app.services.endpoint_transfers import endpoint_transfers
from app.services.stop_suggestions import suggest_stops

app = FastAPI(title="Interrail Helper", version="0.1.0")
PREFIX = "/api/v1"

@app.exception_handler(PlanningError)
async def planning_error(_, error):
    return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": error.message, "details": error.details}})

@app.exception_handler(RequestValidationError)
async def validation_error(_, error):
    details = [{"location": list(e["loc"]), "message": e["msg"]} for e in error.errors()]
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "Check the supplied fields.", "details": {"fields": details}}})

@app.exception_handler(SQLAlchemyError)
async def database_error(_, error):
    return JSONResponse(status_code=503, content={"error": {"code": "DATABASE_UNAVAILABLE", "message": "The database is not ready. Check the database service and run migrations.", "details": {}}})

def trip_or_404(db, trip_id):
    trip = db.get(Trip, str(trip_id))
    if not trip: raise PlanningError("NOT_FOUND", "Trip not found.", status=404)
    return trip

def authorize(trip, token):
    if not token or not token_matches(token, trip.edit_token_hash):
        raise PlanningError("UNAUTHORIZED", "A valid trip edit token is required.", status=401)

def trip_view(trip):
    return {"id": trip.id, "revision": trip.revision, "request": trip.request,
        "created_at": trip.created_at.isoformat(), "itineraries": [serialize(i) for i in trip.itineraries]}

@app.get(PREFIX + "/health")
def health(db: Session = Depends(get_db)):
    try: db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "database": "unavailable"})
    return {"status": "ok", "database": "ok", "ai_required_for_routing": False}

@app.get(PREFIX + "/destinations")
def destinations(q: str = Query(default="", max_length=100), db: Session = Depends(get_db)):
    rows = db.scalars(select(Destination).where(Destination.name.ilike(f"%{q}%")).order_by(Destination.name)).all()
    if not rows and not q:
        raise PlanningError("DATA_NOT_SEEDED", "No destinations are available. Run the seed import after migrations.", status=503)
    return [destination_view(d) for d in rows]

@app.get(PREFIX + "/itineraries/{itinerary_id}/legs/{leg_index}/stop-suggestions")
def intermediate_stops(itinerary_id: UUID, leg_index: int, db: Session = Depends(get_db)):
    itinerary = db.get(Itinerary, str(itinerary_id))
    if not itinerary:
        raise PlanningError("NOT_FOUND", "Itinerary not found.", status=404)
    return suggest_stops(itinerary, leg_index, RailGraph(db))

def destination_view(d):
    return {k: getattr(d, k) for k in ["id", "name", "country_code", "latitude", "longitude", "category", "interest_tags", "suggested_nights", "is_endpoint", "airport"]}

@app.get(PREFIX + "/destinations/{destination_id}")
def destination_detail(destination_id: str, db: Session = Depends(get_db)):
    d = db.get(Destination, destination_id)
    if not d: raise PlanningError("NOT_FOUND", "Destination not found.", status=404)
    attractions = db.scalars(select(Attraction).where(Attraction.destination_id == destination_id).order_by(Attraction.name)).all()
    return {**destination_view(d), "attractions": [{key: getattr(attraction, key)
        for key in ("id", "name", "description", "interest_tags", "source")} for attraction in attractions]}

@app.get(PREFIX + "/rail-network")
def rail_network(db: Session = Depends(get_db)):
    edges = db.scalars(select(RailConnection).order_by(RailConnection.id)).all()
    rail_edges = [{**{key: getattr(edge, key) for key in (
        "id", "origin_id", "destination_id", "estimated_minutes", "transfers",
        "service_type", "night_train", "estimate_quality", "source", "reservation_warning"
    )}, "mode": "rail"} for edge in edges]
    ids = set(db.scalars(select(Destination.id)).all())
    return rail_edges + endpoint_transfers(ids)

@app.post(PREFIX + "/trips", status_code=201)
def create_trip(request: TripRequest, db: Session = Depends(get_db)):
    rail = RailGraph(db)
    unknown = set(request.required_stops + request.preferred_stops) - rail.destinations.keys()
    if unknown: raise PlanningError("UNKNOWN_DESTINATION", "Unknown stops.", {"destination_ids": sorted(unknown)})
    if "oslo" not in rail.destinations: raise PlanningError("DATA_NOT_SEEDED", "Run the seed command before creating trips.", status=503)
    token, digest = issue_token()
    trip = Trip(edit_token_hash=digest, total_days=request.total_days, start_date=request.start_date,
        date_mode=request.date_mode, request=request.model_dump(mode="json", by_alias=True),
        total_budget=request.budget.total, final_stay_budget=request.budget.final_stay, currency=request.budget.currency)
    db.add(trip)
    db.flush()
    db.add(TripPass(trip_id=trip.id, details=request.pass_details.model_dump(mode="json")))
    db.commit()
    return {**trip_view(trip), "edit_token": token}

@app.get(PREFIX + "/trips/{trip_id}")
def get_trip(trip_id: UUID, db: Session = Depends(get_db)):
    return trip_view(trip_or_404(db, trip_id))

@app.delete(PREFIX + "/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: UUID, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    trip = trip_or_404(db, trip_id)
    authorize(trip, x_edit_token)
    db.delete(trip)
    db.commit()

@app.post(PREFIX + "/trips/{trip_id}/generate")
def generate_trip(trip_id: UUID, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    trip = db.scalar(select(Trip).where(Trip.id == str(trip_id)).with_for_update())
    if not trip: raise PlanningError("NOT_FOUND", "Trip not found.", status=404)
    authorize(trip, x_edit_token)
    if trip.itineraries:
        # Reopening/generating cannot silently destroy manually edited alternatives.
        return [serialize(i) for i in trip.itineraries]
    results = generate(TripRequest.model_validate(trip.request), RailGraph(db))
    for index, result in enumerate(results):
        itinerary = Itinerary(trip_id=trip.id, name=result["name"], score=result["score"], result=result, is_selected=index == 0)
        db.add(itinerary)
        db.flush()
        persist_result(db, itinerary, result)
    db.commit()
    db.expire(trip, ["itineraries"])
    return [serialize(i) for i in trip.itineraries]

@app.get(PREFIX + "/trips/{trip_id}/itineraries")
def list_itineraries(trip_id: UUID, db: Session = Depends(get_db)):
    return [serialize(i) for i in trip_or_404(db, trip_id).itineraries]

@app.patch(PREFIX + "/itineraries/{itinerary_id}")
def edit_route(itinerary_id: UUID, edit: EditRequest, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    itinerary = db.get(Itinerary, str(itinerary_id))
    if not itinerary: raise PlanningError("NOT_FOUND", "Itinerary not found.", status=404)
    trip = db.scalar(select(Trip).where(Trip.id == itinerary.trip_id).with_for_update())
    authorize(trip, x_edit_token)
    if itinerary.revision != edit.expected_revision:
        raise PlanningError("STALE_ITINERARY_REVISION", "Reload the itinerary before editing again.", status=409)
    updated_request = None
    if edit.remove_required:
        if trip.revision != edit.expected_trip_revision:
            raise PlanningError("STALE_TRIP_REVISION", "Trip preferences changed. Reload before removing a must-see.", status=409)
        if edit.destination_id not in trip.request["required_stops"]:
            raise PlanningError("INVALID_EDIT", "This city is no longer a must-see. Reload the route.")
        updated_request = {**trip.request,
            "required_stops": [city for city in trip.request["required_stops"] if city != edit.destination_id],
            "preferred_stops": [city for city in trip.request["preferred_stops"] if city != edit.destination_id]}
    planning_itinerary = SimpleNamespace(result=itinerary.result, trip=SimpleNamespace(request=updated_request)) if updated_request else itinerary
    snapshot_plan = None
    if edit.operation == 'set_journey':
        snapshot = db.get(RailJourneySnapshot, str(edit.journey_id))
        if not snapshot:
            raise PlanningError('JOURNEY_NOT_FOUND', 'Search timetables again; this journey snapshot is unavailable.')
        expires = snapshot.expires_at.replace(tzinfo=timezone.utc) if snapshot.expires_at.tzinfo is None else snapshot.expires_at
        if datetime.now(timezone.utc) >= expires:
            raise PlanningError('JOURNEY_EXPIRED', 'This search is over 24 hours old. Search again before choosing it.')
        if edit.leg_index >= len(itinerary.result['legs']):
            raise PlanningError('INVALID_EDIT', 'This journey leg no longer exists.')
        leg = itinerary.result['legs'][edit.leg_index]
        if (snapshot.origin_id, snapshot.destination_id) != (leg['origin_id'], leg['destination_id']):
            raise PlanningError('JOURNEY_MISMATCH', 'That timetable journey belongs to a different city pair.')
        snapshot_plan = {'kind': 'timetable', 'snapshot_id': snapshot.id,
            'journey': snapshot.journey_json, 'sources': snapshot.sources_json,
            'queried_at': (snapshot.queried_at.replace(tzinfo=timezone.utc) if snapshot.queried_at.tzinfo is None else snapshot.queried_at).isoformat(), 'recheck_after': expires.isoformat(),
            'needs_recheck': False, 'status_label': 'Saved timetable · not booked',
            'reservation_status': 'unknown', 'price': None}
    result = edit_itinerary(planning_itinerary, edit, RailGraph(db), snapshot_plan)
    # Conditional UPDATE is the concurrency gate, including on SQLite test databases.
    changed = db.execute(update(Itinerary).where(Itinerary.id == itinerary.id, Itinerary.revision == edit.expected_revision).values(revision=edit.expected_revision+1))
    if changed.rowcount != 1:
        db.rollback()
        raise PlanningError("STALE_ITINERARY_REVISION", "Another edit was saved first. Reload and retry.", status=409)
    persist_result(db, itinerary, result)
    if updated_request:
        changed_trip = db.execute(update(Trip).where(Trip.id == trip.id, Trip.revision == edit.expected_trip_revision).values(revision=edit.expected_trip_revision+1))
        if changed_trip.rowcount != 1:
            db.rollback()
            raise PlanningError("STALE_TRIP_REVISION", "Trip preferences changed. Reload before removing a must-see.", status=409)
        trip.request = updated_request
        for other in trip.itineraries:
            if other.id == itinerary.id: continue
            other.result = {**other.result, "stops": [{**stop, "is_required": False} if stop["destination_id"] == edit.destination_id else stop for stop in other.result["stops"]]}
            other.revision += 1
        db.execute(update(TripStop).where(TripStop.itinerary_id.in_([other.id for other in trip.itineraries]), TripStop.destination_id == edit.destination_id).values(is_required=False))
    db.commit()
    db.refresh(itinerary)
    return {**serialize(itinerary), **({"trip_revision": trip.revision} if updated_request else {})}

@app.post(PREFIX + "/itineraries/{itinerary_id}/select")
def select_route(itinerary_id: UUID, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    itinerary = db.get(Itinerary, str(itinerary_id))
    if not itinerary: raise PlanningError("NOT_FOUND", "Itinerary not found.", status=404)
    trip = db.scalar(select(Trip).where(Trip.id == itinerary.trip_id).with_for_update())
    authorize(trip, x_edit_token)
    db.execute(update(Itinerary).where(Itinerary.trip_id == trip.id).values(is_selected=False))
    itinerary.is_selected = True
    db.commit()
    db.refresh(itinerary)
    return serialize(itinerary)

from app.integration_api import router as integration_router
app.include_router(integration_router)

@app.patch(PREFIX + "/trips/{trip_id}")
def patch_trip(trip_id: UUID, patch: TripPatch, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    from pydantic import ValidationError
    trip = db.scalar(select(Trip).where(Trip.id == str(trip_id)).with_for_update())
    if not trip: raise PlanningError("NOT_FOUND", "Trip not found.", status=404)
    authorize(trip, x_edit_token)
    if trip.revision != patch.expected_revision:
        raise PlanningError("STALE_TRIP_REVISION", "Reload the trip before updating preferences.", status=409)
    changes = patch.model_dump(mode="json", by_alias=True, exclude_unset=True)
    changes.pop("expected_revision")
    merged = dict(trip.request)
    for key, value in changes.items():
        if isinstance(value, dict): merged[key] = {**merged[key], **value}
        else: merged[key] = value
    try: request = TripRequest.model_validate(merged)
    except ValidationError:
        raise PlanningError("VALIDATION_ERROR", "The updated preferences are invalid. Check duration, dates, pass and final stay.")
    rail = RailGraph(db)
    unknown = set(request.required_stops + request.preferred_stops) - rail.destinations.keys()
    if request.preferences.endpoint_id and request.preferences.endpoint_id not in rail.destinations: unknown.add(request.preferences.endpoint_id)
    if unknown: raise PlanningError("UNKNOWN_DESTINATION", "Unknown destination.", {"destination_ids": sorted(unknown)})
    rail = rail.daytime()
    # Recalculation preserves saved stop order, edited stays and all locked calendar intervals.
    recalculated = []
    region_country = {"southern_italy": "IT", "southern_france": "FR", "spain": "ES", "croatia": "HR", "greece": "GR"}
    target_country = region_country.get(request.preferences.endpoint_region)
    islands = request.preferences.endpoint_region == "islands"
    region_endpoints = sorted(d.id for d in rail.destinations.values() if d.is_endpoint and (d.category == "island" if islands else d.country_code == target_country))
    for route_index, itinerary in enumerate(trip.itineraries):
        old = itinerary.result
        ids = [s["destination_id"] for s in old["stops"]]
        old_endpoint = ids[-1]
        next_endpoint = request.preferences.endpoint_id
        if not next_endpoint and "endpoint_region" in changes.get("preferences", {}) and (islands and rail.destinations[old_endpoint].category != "island" or target_country and rail.destinations[old_endpoint].country_code != target_country):
            if not region_endpoints: raise PlanningError("ROUTE_NOT_FOUND", "This region has no curated endpoints.")
            next_endpoint = region_endpoints[route_index % len(region_endpoints)]
        if next_endpoint and next_endpoint != old_endpoint:
            if old["stops"][-1]["is_locked"] or old_endpoint in request.required_stops:
                raise PlanningError("STOP_LOCKED", "The current endpoint is required or locked.")
            if not rail.destinations[next_endpoint].is_endpoint:
                raise PlanningError("INVALID_ENDPOINT", "Choose a curated southern endpoint.")
            gateways = {s["destination_id"] for s in old["stops"][:-1] if s.get("is_transfer_gateway") and not s["is_locked"] and s["destination_id"] not in set(request.required_stops + request.preferred_stops) | set(old.get("night_overrides", {}))}
            ids = [point for point in ids if point not in gateways]
            ids[-1] = next_endpoint
        for city in request.required_stops:
            if city not in ids: ids.insert(len(ids)-1, city)
        locked = {s["destination_id"] for s in old["stops"] if s["is_locked"]}
        fixed = {**old.get("night_overrides", {}), **{s["destination_id"]: s["nights"] for s in old["stops"] if s["is_locked"]}}
        fixed = {c:n for c,n in fixed.items() if c in ids}
        if "final_stay_nights" in changes.get("preferences", {}) and ids[-1] not in locked:
            fixed.pop(ids[-1], None)
        local_request = request.model_copy(deep=True)
        local_request.preferred_stops = list(dict.fromkeys(ids[1:-1] + request.preferred_stops))
        if ids[-1] in fixed: local_request.preferences.final_stay_nights = fixed[ids[-1]]
        result = schedule(build_path(ids, rail), local_request, rail, fixed, locked, old.get('journey_plans', {}))
        for original in old["stops"]:
            if original["destination_id"] not in locked: continue
            updated = next(s for s in result["stops"] if s["destination_id"] == original["destination_id"])
            if (updated["arrival_day"], updated["departure_day"], updated["arrival_date"], updated["departure_date"]) != (original["arrival_day"], original["departure_day"], original["arrival_date"], original["departure_date"]):
                raise PlanningError("LOCKED_SCHEDULE_CONFLICT", "The updated preferences would move a locked stay.")
        result["score"], result["score_components"] = score_route(result, local_request, rail)
        result["name"] = f"South to {rail.destinations[ids[-1]].name}"
        result["night_overrides"] = {c:n for c,n in old.get("night_overrides", {}).items() if c in fixed}
        recalculated.append((itinerary, result))
    changed = db.execute(update(Trip).where(Trip.id == trip.id, Trip.revision == patch.expected_revision).values(revision=patch.expected_revision+1))
    if changed.rowcount != 1:
        db.rollback()
        raise PlanningError("STALE_TRIP_REVISION", "Another update was saved first. Reload and retry.", status=409)
    trip.request = request.model_dump(mode="json", by_alias=True)
    trip.total_days, trip.start_date, trip.date_mode = request.total_days, request.start_date, request.date_mode
    trip.total_budget, trip.final_stay_budget, trip.currency = request.budget.total, request.budget.final_stay, request.budget.currency
    trip.pass_record.details = request.pass_details.model_dump(mode="json")
    for itinerary, result in recalculated:
        itinerary.revision += 1
        persist_result(db, itinerary, result)
    db.commit()
    return trip_view(trip)
