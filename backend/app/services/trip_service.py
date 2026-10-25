from datetime import date
from sqlalchemy import delete, select
from sqlalchemy.orm import object_session
from app.models.entities import Itinerary, TripStop, TripLeg, Destination
from app.schemas.trips import TripRequest
from app.services.errors import PlanningError
from app.services.route_engine.generator import build_path, score_route
from app.services.scheduler import schedule
from app.services.journey_plans import annotate_plans, leg_keys

def serialize(itinerary):
    from app.services.connection_plans import connection_plan
    from app.services.airport_access import airport_access
    result = annotate_plans(itinerary.result)
    # Add derived detail to older saved routes without writing/revising their data.
    for leg in result.get('legs', []):
        leg['connections'] = [{**edge, 'connection_plan': connection_plan(edge)}
                              if edge.get('mode') == 'ferry_transfer' and edge.get('components') else dict(edge)
                              for edge in leg.get('connections', [])]
    db = object_session(itinerary)
    city = db.get(Destination, result.get('endpoint_id')) if db and result.get('endpoint_id') else None
    if city:
        result['airport_access'] = airport_access(city)
    return {**result, "id": itinerary.id, "trip_id": itinerary.trip_id, "revision": itinerary.revision, "is_selected": itinerary.is_selected}

def persist_result(db, itinerary, result):
    # Delete legs before stops and flush to avoid unique-position collisions during replacement.
    db.execute(delete(TripLeg).where(TripLeg.itinerary_id == itinerary.id))
    db.execute(delete(TripStop).where(TripStop.itinerary_id == itinerary.id))
    stops = []
    for stop in result["stops"]:
        values = {k: v for k, v in stop.items() if k in {"destination_id", "position", "arrival_day", "departure_day", "arrival_date", "departure_date", "nights", "is_required", "is_locked"}}
        for key in ["arrival_date", "departure_date"]:
            if values[key]: values[key] = date.fromisoformat(values[key])
        record = TripStop(itinerary_id=itinerary.id, **values)
        db.add(record)
        stops.append(record)
    db.flush()
    for i, leg in enumerate(result["legs"]):
        db.add(TripLeg(itinerary_id=itinerary.id, from_stop_id=stops[i].id, to_stop_id=stops[i+1].id,
            estimated_minutes=leg["estimated_minutes"], departure_day=leg["departure_day"],
            mode=leg.get("mode", "rail"), travel_days_estimate=leg.get("travel_days_estimate", 1)))
    itinerary.result = result
    itinerary.score = result["score"]
    itinerary.name = result["name"]

def edit_itinerary(itinerary, edit, rail, journey_snapshot=None):
    if edit.operation == "add_stop" and edit.position is None:
        # Map clicks have no position. Try each insertion slot and retain the
        # shortest feasible schedule, honoring all existing stays and locks.
        candidates, failures = [], []
        for position in range(1, len(itinerary.result["stops"])):
            try:
                candidates.append(edit_itinerary(itinerary, edit.model_copy(update={"position": position}), rail))
            except PlanningError as error:
                failures.append(error)
        if not candidates:
            raise failures[0] if failures else PlanningError("INVALID_EDIT", "No insertion position is available.")
        return min(candidates, key=lambda result: sum(leg["estimated_minutes"] for leg in result["legs"]))
    request = TripRequest.model_validate(itinerary.trip.request)
    rail = rail.daytime()
    old = itinerary.result
    ids = [s["destination_id"] for s in old["stops"]]
    locked = {s["destination_id"] for s in old["stops"] if s["is_locked"]}
    fixed = {**old.get("night_overrides", {}), **{s["destination_id"]: s["nights"] for s in old["stops"] if s["is_locked"]}}
    plans = dict(old.get('journey_plans', {}))
    city = edit.destination_id
    if ids.count(city) > 1 and edit.operation in {"set_nights", "lock_stop", "remove_stop", "reorder_stop"}:
        raise PlanningError("MULTIPLE_VISITS", "This rail hub is visited more than once. Its separate travel breaks are scheduled automatically; edit a different city or adjust the trip preferences.")
    if city not in rail.destinations:
        raise PlanningError("UNKNOWN_DESTINATION", "Unknown destination.")
    if edit.operation in {"set_nights", "remove_stop", "reorder_stop"} and city in locked:
        raise PlanningError("STOP_LOCKED", "Unlock this stop before changing it.")
    if edit.operation in {'set_leg_plan', 'set_journey', 'clear_leg_plan'}:
        if edit.leg_index >= len(old['legs']):
            raise PlanningError('INVALID_EDIT', 'This journey leg no longer exists. Reload the route.')
        leg = old['legs'][edit.leg_index]
        if leg['origin_id'] != city or leg.get('mode', 'rail') != 'rail':
            raise PlanningError('INVALID_EDIT', 'Choose an outgoing train leg, not an endpoint transfer.')
        key = leg_keys(ids)[edit.leg_index]
        if edit.operation == 'clear_leg_plan':
            plans.pop(key, None)
        elif edit.operation == 'set_leg_plan':
            plans[key] = {'kind': 'overnight_intent', 'status_label': 'Overnight intention · unverified', 'needs_recheck': True}
        elif journey_snapshot:
            plans[key] = journey_snapshot
        else:
            raise PlanningError('INVALID_JOURNEY', 'Choose a saved timetable search result.')
    elif edit.operation == "add_stop":
        if city in ids or edit.position is None or edit.position >= len(ids):
            raise PlanningError("INVALID_EDIT", "Choose a new city and a position before the endpoint.")
        ids.insert(edit.position, city)
    elif edit.operation == "change_endpoint":
        if ids[-1] in locked or ids[-1] in request.required_stops:
            raise PlanningError("STOP_LOCKED", "The current endpoint is required or locked.")
        if not rail.destinations[city].is_endpoint or city in ids:
            raise PlanningError("INVALID_ENDPOINT", "Choose a different curated endpoint.")
        fixed.pop(ids[-1], None)
        # Drop automatically inserted ferry gateways when changing the final
        # island; never discard an explicitly requested, locked or edited stay.
        gateways = {s["destination_id"] for s in old["stops"][:-1] if s.get("is_transfer_gateway") and s["destination_id"] not in set(request.required_stops + request.preferred_stops) | locked | set(fixed)}
        ids = [point for point in ids if point not in gateways]
        ids[-1] = city
    else:
        if city not in ids: raise PlanningError("INVALID_EDIT", "The city is not a stay in this itinerary.")
        if city == "oslo": raise PlanningError("START_FIXED", "Oslo is the fixed starting point.")
        if edit.operation == "set_nights":
            if edit.nights is None: raise PlanningError("INVALID_EDIT", "Provide nights.")
            fixed[city] = edit.nights
            if city == ids[-1]: request.preferences.final_stay_nights = edit.nights
        elif edit.operation == "lock_stop":
            if edit.locked is None: raise PlanningError("INVALID_EDIT", "Provide locked true or false.")
            if edit.locked:
                locked.add(city)
                fixed[city] = next(s["nights"] for s in old["stops"] if s["destination_id"] == city)
            else:
                locked.discard(city)
                if city not in old.get("night_overrides", {}): fixed.pop(city, None)
        elif edit.operation == "remove_stop":
            if city in request.required_stops or city == ids[-1]:
                raise PlanningError("REQUIRED_STOP", "Required stops and the endpoint cannot be removed.")
            ids.remove(city)
            fixed.pop(city, None)
        elif edit.operation == "reorder_stop":
            if city == ids[-1] or edit.position is None or edit.position >= len(ids)-1:
                raise PlanningError("INVALID_EDIT", "Reorder only intermediate stays.")
            old_locked_positions = {c: ids.index(c) for c in locked}
            ids.remove(city)
            ids.insert(edit.position, city)
            if any(ids.index(c) != p for c,p in old_locked_positions.items()):
                raise PlanningError("STOP_LOCKED", "The edit would move a locked stop.")
    if ids[-1] in fixed: request.preferences.final_stay_nights = fixed[ids[-1]]
    request.preferred_stops = ids[1:-1]
    path = build_path(ids, rail)
    result = schedule(path, request, rail, fixed, locked, plans)
    new_ids = [s["destination_id"] for s in result["stops"]]
    if edit.operation == "remove_stop" and city in new_ids:
        raise PlanningError("STOP_REQUIRED_FOR_CONNECTION", "This stop separates the endpoint transfer or provides the default exploration stay. Add another intermediate stay before removing it.")
    # Locked stops preserve stay length and calendar interval, not only their label.
    for original in old["stops"]:
        if original["destination_id"] not in locked: continue
        updated = next(s for s in result["stops"] if s["destination_id"] == original["destination_id"])
        if (updated["arrival_day"], updated["departure_day"]) != (original["arrival_day"], original["departure_day"]):
            raise PlanningError("LOCKED_SCHEDULE_CONFLICT", "The edit would change the calendar interval of a locked stay.")
    overrides = dict(old.get("night_overrides", {}))
    if edit.operation == "set_nights": overrides[city] = edit.nights
    if edit.operation == "remove_stop": overrides.pop(city, None)
    if edit.operation == "change_endpoint": overrides.pop(old["stops"][-1]["destination_id"], None)
    result["night_overrides"] = overrides
    result["score"], result["score_components"] = score_route(result, request, rail)
    result["name"] = f"South to {rail.destinations[ids[-1]].name}"
    return result
