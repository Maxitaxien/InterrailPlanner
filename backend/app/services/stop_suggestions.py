"""On-demand, read-only previews of intermediate stays, without LLM claims."""
from math import cos, radians, hypot
import networkx as nx
from app.schemas.trips import EditRequest, TripRequest
from app.services.errors import PlanningError
from app.services.trip_service import edit_itinerary


def suggest_stops(itinerary, leg_index, rail):
    legs = itinerary.result["legs"]
    if leg_index < 0 or leg_index >= len(legs):
        raise PlanningError("NOT_FOUND", "Journey leg not found.", status=404)
    leg = legs[leg_index]
    if leg.get("mode", "rail") != "rail":
        return {"suggestions": [], "notice": "This is a ferry/ground connection. Research gateway stays and actual sailings separately."}
    request = TripRequest.model_validate(itinerary.trip.request)
    rail = rail.daytime()
    existing = {stop["destination_id"] for stop in itinerary.result["stops"]}
    origin, destination = rail.destinations[leg["origin_id"]], rail.destinations[leg["destination_id"]]
    midpoint = ((origin.latitude+destination.latitude)/2, (origin.longitude+destination.longitude)/2)
    def nearby(city):
        return hypot((city.latitude-midpoint[0])*111, (city.longitude-midpoint[1])*111*cos(radians(midpoint[0])))
    pool = set(leg["via"][1:-1]) - existing
    pool.update(city.id for city in sorted(rail.destinations.values(), key=nearby)[:12] if nearby(city) < 300 and city.category != "island" and city.id not in existing)
    candidates = []
    for city_id in pool:
        city = rail.destinations[city_id]
        try:
            before = rail.path(origin.id, city_id, False)
            after = rail.path(city_id, destination.id, False)
            first = sum(rail.edge(a,b)["minutes"] for a,b in zip(before,before[1:]))
            second = sum(rail.edge(a,b)["minutes"] for a,b in zip(after,after[1:]))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
        extra = max(0, first + second - leg["estimated_minutes"])
        if extra > 180:
            continue
        matches = sorted(set(city.interest_tags) & set(request.preferences.interests))
        candidates.append((extra/60 + abs(first-second)/max(1, first+second) - len(matches)*.3, city_id, first, second, extra, matches))
    suggestions = []
    for _, city_id, first, second, extra, matches in sorted(candidates)[:6]:
        city = rail.destinations[city_id]
        suggestion = {"destination_id": city_id, "name": city.name, "country_code": city.country_code,
                      "origin": origin.name, "destination": destination.name,
                      "before_minutes": first, "after_minutes": second, "extra_travel_minutes": extra,
                      "suggested_nights": city.suggested_nights, "interest_matches": matches,
                      "reason": "Matches your interest in " + ", ".join(matches) if matches else "A useful place to break up this rail corridor.",
                      "can_add": False, "planned_nights": None, "extra_pass_days": None, "limitation": None}
        try:
            preview = edit_itinerary(itinerary, EditRequest(expected_revision=itinerary.revision, operation="add_stop", destination_id=city_id, position=leg_index+1), rail)
            index = next(i for i,s in enumerate(preview["stops"]) if s["destination_id"] == city_id)
            suggestion.update(can_add=True, planned_nights=preview["stops"][index]["nights"],
                              before_minutes=preview["legs"][index-1]["estimated_minutes"],
                              after_minutes=preview["legs"][index]["estimated_minutes"],
                              extra_pass_days=preview["travel_days_estimate"]-itinerary.result["travel_days_estimate"])
            suggestion["extra_travel_minutes"] = max(0, sum(item["estimated_minutes"] for item in preview["legs"]) - sum(item["estimated_minutes"] for item in legs))
        except PlanningError as error:
            suggestion["limitation"] = error.message
            if error.code == "PASS_LIMIT_EXCEEDED":
                suggestion["limitation"] += f" This preview needs {error.details['travel_days_estimate']} rail-pass days; {error.details['remaining']} remain."
            elif error.code == "TRIP_DURATION_EXCEEDED":
                suggestion["limitation"] += f" Allow {error.details['required_days']} calendar days; the trip currently has {error.details['available_days']}."
        suggestions.append(suggestion)
    return {"suggestions": suggestions, "notice": "Illustrative corridor estimates, not train departures. Adding a stay redistributes existing nights while preserving the final stay; pass and lock constraints are previewed, not bypassed."}
