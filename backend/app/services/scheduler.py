from datetime import datetime, timedelta
from app.services.errors import PlanningError
from app.services.airport_access import airport_access
from app.services.journey_plans import leg_keys, timing, NIGHT_RULE_URL

ESTIMATE_WARNING = "Illustrative rail durations and schematic connections; verify timetables, pass acceptance and reservations."

def schedule(path, request, rail, fixed_nights=None, locked=None, journey_plans=None):
    fixed_nights, locked = fixed_nights or {}, set(locked or [])
    required = set(request.required_stops)
    # Every requested/edited waypoint is a visit, including explicit zero-night visits.
    waypoints = required | set(request.preferred_stops) | set(fixed_nights) | locked | {path[-1]}
    # With no requested intermediate stay, offer one default exploration stop.
    # This is not a daily cap; a single corridor can be as long as necessary.
    if not (waypoints - {path[-1]}) and len(path) > 2:
        waypoints.add(path[len(path) // 2])
    stop_ids, legs = [path[0]], []
    via, minutes = [path[0]], 0
    visited_waypoints = {path[0]}
    for index in range(1, len(path)):
        a, b = path[index-1:index+1]
        edge = rail.edge(a, b)
        if edge.get("night_train"):
            raise PlanningError("NIGHT_TRAIN_UNSUPPORTED", "This route needs explicit overnight-train scheduling.")
        mode = edge.get("mode", "rail")
        # Keep an endpoint ferry/ground transfer separate from rail, including
        # its booking requirements and pass-day accounting.
        if mode != "rail" and minutes:
            stop_ids.append(a)
            legs.append({"origin_id": via[0], "destination_id": a, "via": via[:], "estimated_minutes": minutes})
            via, minutes = [a], 0
        minutes += edge["minutes"]
        via.append(b)
        if index == len(path) - 1 or mode != "rail" or b in waypoints and b not in visited_waypoints:
            stop_ids.append(b)
            legs.append({"origin_id": via[0], "destination_id": b, "via": via[:], "estimated_minutes": minutes})
            via, minutes = [b], 0
            visited_waypoints.add(b)
    for leg in legs:
        leg["connections"] = [{"origin_id": a, "destination_id": b, **rail.edge(a,b),
            "country_transition": rail.destinations[a].country_code != rail.destinations[b].country_code}
            for a,b in zip(leg["via"],leg["via"][1:])]
        modes = {edge.get("mode", "rail") for edge in leg["connections"]}
        leg["mode"] = "rail" if modes == {"rail"} else "ferry_transfer"
        # A lower-bound calendar allowance, not a dated connection schedule.
        leg["travel_nights_estimate"] = max(leg["estimated_minutes"] // 1440, sum(edge.get("overnight_nights", 0) for edge in leg["connections"]))
        leg["rail_minutes"] = sum(edge["minutes"] for edge in leg["connections"] if edge.get("mode", "rail") == "rail")
        leg["travel_days_estimate"] = 1 + leg["travel_nights_estimate"] if leg["mode"] == "rail" else 0
        leg["is_long_journey"] = leg["estimated_minutes"] > 480
        leg["estimate_quality"] = "illustrative"
        candidates, elapsed = [], 0
        for edge in leg["connections"][:-1]:
            elapsed += edge["minutes"]
            city = edge["destination_id"]
            if city not in stop_ids and leg["mode"] == "rail":
                candidates.append((abs(elapsed - leg["estimated_minutes"] / 2), city))
        leg["suggested_stop_ids"] = [city for _, city in sorted(candidates)[:3]] if leg["is_long_journey"] else []
        ground_only = leg["mode"] != "rail" and all(
            edge.get("components") and all(part["mode"] != "ferry" for part in edge["components"])
            for edge in leg["connections"])
        leg["travel_advice"] = ("Separate onward ground transfer: arrange local transport, confirm the connection after your ferry and budget separately. Pass coverage is unknown." if ground_only else "Separate ferry and onward ground transfer: allow an overnight crossing, confirm check-in and connections, and budget separately. Pass coverage is unknown." if leg["mode"] != "rail" else
            "A very long rail journey. Consider adding an overnight stop; departure times, waiting time and extra pass days need verification." if leg["estimated_minutes"] > 720 else
            "A long rail journey. Add an intermediate stay if you would prefer a gentler pace." if leg["is_long_journey"] else "Illustrative rail time; check actual departures and connections.")
    plans, anchors = {}, []
    for index, (leg, key) in enumerate(zip(legs, leg_keys(stop_ids))):
        leg['leg_key'] = key
        plan = (journey_plans or {}).get(key)
        if not plan or leg['mode'] != 'rail':
            continue
        plan = dict(plan)
        plans[key] = plan
        leg['travel_plan'] = plan
        if plan['kind'] == 'overnight_intent':
            leg['travel_nights_estimate'] = max(1, leg['travel_nights_estimate'])
            leg['travel_days_estimate'] = 1 + leg['travel_nights_estimate']
            leg['travel_advice'] = 'Overnight travel is an intention only, not evidence of a night train. Allow transit nights; verify departures, cabins and reservations when published. Pass-day savings are not assumed.'
        else:
            if not request.start_date:
                raise PlanningError('DATES_REQUIRED', 'Set an exact trip start date before choosing a dated train journey. Clear saved journeys before switching to flexible dates.')
            info = timing(plan['journey'], rail.destinations[leg['origin_id']].country_code, rail.destinations[leg['destination_id']].country_code)
            plan.update(departure_date=info['departure_date'].isoformat(), arrival_date=info['arrival_date'].isoformat())
            departure_day = (info['departure_date'] - request.start_date).days
            if not 0 <= departure_day < request.total_days:
                raise PlanningError('JOURNEY_DATE_CONFLICT', 'A saved departure is outside this trip. Clear it or choose a journey on the new dates.')
            anchors.append((index, departure_day))
            leg.update({field: info[field] for field in ('estimated_minutes', 'rail_minutes', 'travel_nights_estimate')})
            leg['pass_day_offsets'] = [(day - request.start_date).days for day in info['boarding_dates']]
            leg['rail_valid_until_offset'] = (info['last_rail_date'] - request.start_date).days
            leg['travel_days_estimate'] = len(leg['pass_day_offsets'])
            leg['estimate_quality'] = 'timetable_snapshot'
            leg['is_long_journey'] = leg['estimated_minutes'] > 480
            leg['suggested_stop_ids'] = []
            leg['travel_advice'] = 'Saved dated timetable, not a booking. Calendar and pass-day estimates use its times; pass acceptance, actual operating days, seats and reservations still need checking. Map geometry remains schematic.'
        leg['is_overnight'] = leg['travel_nights_estimate'] > 0
    # Visits, rather than destination IDs, own their nights. A return through
    # Oslo or another hub must not overwrite an earlier stay's calendar.
    nights = [0] + [fixed_nights.get(city, 1) for city in stop_ids[1:]]
    nights[-1] = fixed_nights.get(path[-1], request.preferences.final_stay_nights)
    # total_days includes the return day: N days contain N-1 nights.
    available = request.total_days - 1
    transit_nights = sum(leg["travel_nights_estimate"] for leg in legs)
    if sum(nights) + transit_nights > available:
        raise PlanningError("TRIP_DURATION_EXCEEDED", "The stays and estimated nights in transit exceed the trip duration.", {"required_days": sum(nights) + transit_nights + 1, "available_days": request.total_days})
    priorities = sorted(range(1, len(stop_ids) - 1), key=lambda i: (stop_ids[i] not in required, -len(set(rail.destinations[stop_ids[i]].interest_tags) & set(request.preferences.interests))))
    # Dated departures pin cumulative stay nights before their outgoing leg.
    # Allocate each interval independently rather than shifting saved departures.
    boundaries = [(i, day - sum(leg['travel_nights_estimate'] for leg in legs[:i])) for i, day in anchors]
    boundaries.append((len(stop_ids)-1, available - transit_nights))
    previous_index, previous_total, extended_final_stay = -1, 0, False
    for end_index, cumulative in boundaries:
        indexes = list(range(previous_index+1, end_index+1))
        spare = cumulative - previous_total - sum(nights[i] for i in indexes)
        if spare < 0:
            raise PlanningError('JOURNEY_DATE_CONFLICT', 'The stays cannot fit before a saved departure. Reduce an earlier stay, clear that journey, or choose another departure.')
        local_priorities = [i for i in priorities if i in indexes]
        eligible = [i for i in local_priorities if stop_ids[i] not in fixed_nights and stop_ids[i] not in locked]
        for i in eligible:
            desired = rail.destinations[stop_ids[i]].suggested_nights
            if request.preferences.pace == 'relaxed': desired += 1
            if request.preferences.pace == 'fast': desired = max(1, desired - 1)
            added = min(spare, max(0, desired - nights[i]))
            nights[i] += added
            spare -= added
        if spare and not eligible and end_index == len(stop_ids)-1 and stop_ids[-1] not in fixed_nights and stop_ids[-1] not in locked:
            nights[-1] += spare
            spare = 0
            extended_final_stay = True
        if spare and not eligible:
            raise PlanningError('LOCKED_DURATION_CONFLICT', 'No flexible stay can absorb the remaining nights before the next departure. Unlock a stay or adjust the trip duration.')
        for i in range(spare): nights[eligible[i % len(eligible)]] += 1
        previous_index, previous_total = end_index, cumulative
    stops, day, visits = [], 0, {}
    for i, city in enumerate(stop_ids):
        if i:
            day += legs[i-1]["travel_nights_estimate"]
        destination = rail.destinations[city]
        departure = day + nights[i]
        visits[city] = visits.get(city, 0) + 1
        stops.append({"destination_id": city, "name": destination.name, "country_code": destination.country_code,
            "latitude": destination.latitude, "longitude": destination.longitude,
            "position": i, "arrival_day": day, "departure_day": departure,
            "arrival_date": (request.start_date + timedelta(days=day)).isoformat() if request.start_date else None,
            "departure_date": (request.start_date + timedelta(days=departure)).isoformat() if request.start_date else None,
            "nights": nights[i], "is_day_visit": i > 0 and nights[i] == 0, "visit_number": visits[city], "is_revisit": visits[city] > 1, "is_required": city in required and visits[city] == 1, "is_locked": city in locked,
            "is_transfer_gateway": i < len(legs) and legs[i]["mode"] != "rail"})
        day = departure
    for i, leg in enumerate(legs):
        leg.update(departure_day=stops[i]["departure_day"], arrival_day=stops[i+1]["arrival_day"], verification_status="needs_verification")
        if i and stops[i]['nights'] == 0:
            before, after = legs[i-1].get('travel_plan', {}), leg.get('travel_plan', {})
            if before.get('kind') == after.get('kind') == 'timetable' and datetime.fromisoformat(before['journey']['arrival']) > datetime.fromisoformat(after['journey']['departure']):
                raise PlanningError('JOURNEY_CONNECTION_CONFLICT', 'The outgoing saved train leaves before the incoming journey arrives. Choose another departure.')
    for i, stop in enumerate(stops):
        incoming = legs[i-1]["estimated_minutes"] if i else 0
        stop["usable_sightseeing_minutes_estimate"] = max(0, stop["nights"] * 480 - incoming)
    rail_days = {day for leg in legs if leg["mode"] == "rail" for day in leg.get('pass_day_offsets', range(leg["departure_day"], leg["departure_day"] + leg["travel_days_estimate"]))}
    travel_days = len(rail_days)
    details = request.pass_details
    if details.type == "one_country":
        countries = {rail.destinations[city].country_code for leg in legs if leg["mode"] == "rail" for city in leg["via"]}
        if countries - {details.country_code}:
            raise PlanningError("PASS_INCOMPATIBLE", "A One Country pass does not cover this international journey.", {"route_countries": sorted(countries), "pass_country": details.country_code})
    if details.validity_type == "flexi" and details.travel_days_total is not None and travel_days > details.travel_days_total - details.travel_days_used:
        raise PlanningError("PASS_LIMIT_EXCEEDED", "The estimated rail travel days exceed the remaining pass days.", {"travel_days_estimate": travel_days, "remaining": details.travel_days_total-details.travel_days_used})
    if request.start_date and rail_days:
        first_rail_date = request.start_date + timedelta(days=min(rail_days))
        last_rail_date = request.start_date + timedelta(days=max(max(rail_days), max(leg.get('rail_valid_until_offset', leg['arrival_day']) for leg in legs if leg['mode'] == 'rail')))
        if (details.valid_from and first_rail_date < details.valid_from) or (details.valid_until and last_rail_date > details.valid_until):
            raise PlanningError("PASS_INCOMPATIBLE", "The estimated rail journey falls outside the pass validity dates.")
    return {"stops": stops, "legs": legs, "journey_plans": plans, "total_days": request.total_days, "total_nights": sum(nights) + transit_nights,
        "stay_nights": sum(nights), "transit_nights_estimate": transit_nights,
        "total_rail_minutes": sum(leg["rail_minutes"] for leg in legs),
        "total_transfer_minutes": sum(leg["estimated_minutes"] for leg in legs if leg["mode"] != "rail"),
        "has_non_rail_transfer": any(leg["mode"] != "rail" for leg in legs),
        "travel_days_estimate": travel_days, "pass_status": "unknown" if details.validity_type == "flexi" and details.travel_days_total is None else "needs_verification",
        "return_day": request.total_days-1,
        "return_date": (request.start_date + timedelta(days=request.total_days-1)).isoformat() if request.start_date else None,
        "endpoint_id": path[-1], "airport": rail.destinations[path[-1]].airport,
        "airport_access": airport_access(rail.destinations[path[-1]]),
        "warnings": [ESTIMATE_WARNING, "Airport transfers and return flights are not included in rail estimates.", "There is no daily rail limit. Long journeys are advisory; waiting time, midnight crossings and actual pass-day use need timetable verification."] + (["Overnight intentions are unverified; transit nights are budgeted without assuming a direct sleeper or a one-day pass saving."] if any(p['kind'] == 'overnight_intent' for p in plans.values()) else []) + ([f"Saved timetable journeys are not bookings. Pass-day estimates count local rail-boarding dates; actual pass acceptance and through-service rules need verification: {NIGHT_RULE_URL}"] if any(p['kind'] == 'timetable' for p in plans.values()) else []) + (["A travel plan was cleared because its original city pair/visit no longer exists in this route."] if set(journey_plans or {}) - set(plans) else []) + (["Remaining nights were added to the final stay to preserve your trip duration; explicitly fixed and locked stays were preserved."] if extended_final_stay else []) + (["Zero-night visits have no accommodation night. Check arrival/departure times and luggage storage; selecting zero nights does not select or confirm a night train."] if any(stop["is_day_visit"] for stop in stops) else []) + (["This itinerary returns through a rail hub to reach a branch-line stop; return journeys are included in the estimates."] if len(path) != len(set(path)) else []) + (["Long rail journeys: consider intermediate overnight stays using the suggestions on each leg."] if any(leg["is_long_journey"] and leg["mode"] == "rail" for leg in legs) else []) + (["The endpoint includes a ferry and onward ground transfer, not a continuous train journey. Timings, availability, fares and Interrail benefits are unverified; ferry travel is not included in the rail-pass day estimate."] if any(leg["mode"] != "rail" for leg in legs) else [])}
