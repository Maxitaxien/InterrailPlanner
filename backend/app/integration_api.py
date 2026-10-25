from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from uuid import UUID
import httpx
from fastapi import APIRouter, Depends, Header, Response
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import get_settings
from app.ai.ollama import OllamaProvider
from app.schemas.integrations import ModelRequest, CityIdeasRequest, FlightSearch, HotelSearch, RailRulesRequest, RailBookingRequest, RailTimetableRequest, RailCoverageRequest, RailLocationSearch, ExternalRailSearch, EndpointComparisonRequest, ConnectionCheckRequest
from app.providers.allaboard import AllAboardTimetables
from app.providers.motis import MotisTimetables, coverage_report
from app.models.entities import Destination, Itinerary, Trip
from app.models.integrations import RailJourneySnapshot, CityIdeaSet
from app.services.errors import PlanningError
from app.services.recommendations import recommend
from app.providers.fallback import FlightSearchLinks, AccommodationSearchLinks
from app.providers.rail import rail_rules
from app.services.rail_booking import booking_guide
from app.services.journey_plans import timing
from app.services.city_ideas import history as city_ideas_history, generate_city_ideas
from sqlalchemy import select

router = APIRouter(prefix="/api/v1")

def city_scope(db, trip_id, destination_id, token):
    from app.main import authorize
    trip = db.get(Trip, str(trip_id))
    if not trip: raise PlanningError('NOT_FOUND', 'Trip not found.', status=404)
    authorize(trip, token)
    city = db.get(Destination, destination_id)
    if not city: raise PlanningError('UNKNOWN_DESTINATION', 'Unknown city.')
    return trip, city

@router.get('/trips/{trip_id}/cities/{destination_id}/ideas')
def saved_city_ideas(trip_id: UUID, destination_id: str, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    trip, city = city_scope(db, trip_id, destination_id, x_edit_token)
    return city_ideas_history(db, trip, city)

@router.post('/trips/{trip_id}/cities/{destination_id}/ideas')
async def request_city_ideas(trip_id: UUID, destination_id: str, request: CityIdeasRequest, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    trip, city = city_scope(db, trip_id, destination_id, x_edit_token)
    return await generate_city_ideas(db, trip, city, request)

@router.delete('/trips/{trip_id}/cities/{destination_id}/ideas/{idea_id}', status_code=204)
def delete_city_ideas(trip_id: UUID, destination_id: str, idea_id: UUID, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    trip, city = city_scope(db, trip_id, destination_id, x_edit_token)
    record = db.scalar(select(CityIdeaSet).where(CityIdeaSet.id == str(idea_id),
        CityIdeaSet.trip_id == trip.id, CityIdeaSet.destination_id == city.id))
    if not record:
        raise PlanningError('NOT_FOUND', 'Saved recommendations not found.', status=404)
    db.delete(record)
    db.commit()

@router.get("/ai/models")
async def models():
    settings = get_settings()
    tuning = {'context_window': settings.llm_num_ctx, 'max_output_tokens': settings.llm_num_predict,
              'thinking': settings.llm_thinking, 'web_search_enabled': bool(settings.searxng_base_url)}
    try:
        names = await OllamaProvider().models()
        return {"provider": "ollama", "models": names, "default_model": settings.llm_model, "available": True, "cloud_enabled": False, **tuning}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {"provider": "ollama", "models": [], "default_model": settings.llm_model, "available": False, "cloud_enabled": False, **tuning}

class Ready(BaseModel):
    ready: bool
@router.post("/ai/test")
async def test_ai(request: ModelRequest):
    try:
        result = await OllamaProvider(request.model).generate_structured("Return JSON indicating readiness.", "Return ready: true.", Ready)
        return {"available": result.ready, "provider": "ollama", "cloud_used": False}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {"available": False, "provider": "ollama", "cloud_used": False, "notice": "Ollama unavailable or response invalid; core routing still works."}

@router.post("/itineraries/{itinerary_id}/recommendations")
async def recommendations(itinerary_id: UUID, request: ModelRequest, x_edit_token: str | None = Header(default=None), db: Session = Depends(get_db)):
    from app.main import authorize
    itinerary = db.get(Itinerary, str(itinerary_id))
    if not itinerary: raise PlanningError("NOT_FOUND", "Itinerary not found.", status=404)
    authorize(itinerary.trip, x_edit_token)
    return await recommend(db, itinerary, request.model)

@router.post("/travel/flights/search")
async def flights(request: FlightSearch):
    if not request.departure_date: raise PlanningError("DATES_REQUIRED", "Choose a departure date or the first date of a departure range before searching for flights.")
    return await FlightSearchLinks().search(request)

@router.post("/travel/hotels/search")
async def hotels(request: HotelSearch, db: Session = Depends(get_db)):
    if not request.check_in or not request.check_out: raise PlanningError("DATES_REQUIRED", "Exact check-in and check-out dates are required.")
    if request.check_out <= request.check_in: raise PlanningError("INVALID_DATES", "Check-out must be after check-in.")
    destination = db.get(Destination, request.destination_id)
    if not destination: raise PlanningError("UNKNOWN_DESTINATION", "Unknown destination.")
    values = SimpleNamespace(**request.model_dump(), destination_name=destination.name)
    return await AccommodationSearchLinks().search(values)

@router.post("/travel/rail-rules")
async def rules(request: RailRulesRequest, db: Session = Depends(get_db)):
    return await rail_rules(db, request.topic)

@router.post("/travel/rail/booking-guide")
def rail_booking(request: RailBookingRequest, db: Session = Depends(get_db)):
    ids = set(request.via or [request.origin_id, request.destination_id])
    destinations = {city.id: city for city in db.scalars(select(Destination).where(Destination.id.in_(ids))).all()}
    if ids - destinations.keys():
        raise PlanningError("UNKNOWN_DESTINATION", "A city in this journey is not in the planning catalog.")
    return booking_guide(request, destinations)

@router.post("/travel/rail/timetables")
async def rail_timetables(request: RailTimetableRequest, db: Session = Depends(get_db)):
    origin, destination = db.get(Destination, request.origin_id), db.get(Destination, request.destination_id)
    if not origin or not destination:
        raise PlanningError("UNKNOWN_DESTINATION", "A city in this journey is not in the planning catalog.")
    result = await MotisTimetables().search(request, origin, destination)
    if result['status'] == 'scheduled':
        now = datetime.now(timezone.utc)
        accepted = []
        for journey in result['journeys']:
            try:
                timing(journey, origin.country_code, destination.country_code)
            except PlanningError:
                continue
            snapshot = RailJourneySnapshot(origin_id=origin.id, destination_id=destination.id,
                journey_json=journey, sources_json=result.get('prepared_sources', []),
                queried_at=now, expires_at=now + timedelta(hours=24))
            db.add(snapshot)
            db.flush()
            accepted.append({**journey, 'selection_id': snapshot.id})
        db.commit()
        result = {**result, 'journeys': accepted}
        if not accepted:
            result.update(status='unavailable', message='The returned timetable times could not be validated. Your itinerary is unchanged.')
    return result

@router.post("/travel/rail/coverage")
def rail_coverage(request: RailCoverageRequest, db: Session = Depends(get_db)):
    if not db.get(Destination, request.origin_id) or not db.get(Destination, request.destination_id):
        raise PlanningError("UNKNOWN_DESTINATION", "A city in this journey is not in the planning catalog.")
    return coverage_report(get_settings(), request.origin_id, request.destination_id, request.departure_date)


@router.get("/travel/timetable-sources")
def timetable_sources(response: Response):
    response.headers['Cache-Control'] = 'no-store'
    settings = get_settings()
    return {"sources": [
        {"provider": "self-hosted-motis", "status": "configured" if settings.motis_base_url else "not_configured",
         "message": "Routing coverage depends on explicitly prepared and imported feeds."},
        {**AllAboardTimetables(settings).readiness(),
         "message": "On-demand rail research. Approved access required; no offers, purchases or persisted results."},
        {"provider": "ferryhapi", "status": "awaiting_partner_contract",
         "message": "Awaiting partner endpoint, authentication, schema, port catalogue and permitted storage terms. A key alone cannot enable this integration."},
    ]}


@router.post("/travel/rail/allaboard/locations")
async def allaboard_locations(request: RailLocationSearch, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    city = db.get(Destination, request.city_id)
    if not city:
        raise PlanningError("UNKNOWN_DESTINATION", "City is not in the planning catalog.")
    return await AllAboardTimetables().locations(city)


@router.post("/travel/rail/allaboard/timetables")
async def allaboard_timetables(request: ExternalRailSearch, response: Response, db: Session = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    if not db.get(Destination, request.origin_id) or not db.get(Destination, request.destination_id):
        raise PlanningError("UNKNOWN_DESTINATION", "A city in this journey is not in the planning catalog.")
    return await AllAboardTimetables().search(request)


@router.post("/travel/endpoints/compare")
def endpoint_comparison(request: EndpointComparisonRequest, db: Session = Depends(get_db)):
    from app.services.route_engine.graph import RailGraph
    from app.services.endpoint_comparison import compare_endpoints
    return compare_endpoints(request, RailGraph(db))


@router.post("/travel/connections/check")
def connection_check(request: ConnectionCheckRequest, db: Session = Depends(get_db)):
    from app.services.endpoint_transfers import endpoint_transfers
    from app.services.connection_plans import check_connection
    cities = {city.id: city for city in db.scalars(select(Destination)).all()}
    edge = next((edge for edge in endpoint_transfers(cities) if edge['id'] == request.connection_id), None)
    if not edge:
        raise PlanningError('UNKNOWN_CONNECTION', 'Choose one of the modeled ferry connections.')
    return check_connection(request, edge, cities[edge['origin_id']], cities[edge['destination_id']])
