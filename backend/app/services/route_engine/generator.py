from itertools import permutations
import networkx as nx
from app.services.errors import PlanningError
from app.services.scheduler import schedule
from app.core.config import get_settings

def score_route(result, request, rail):
    stops = result["stops"][1:]
    interests = set(request.preferences.interests)
    match = sum(len(interests & set(rail.destinations[s["destination_id"]].interest_tags)) / max(1, len(interests)) for s in stops) / max(1, len(stops))
    if request.preferred_stops:
        included = {s["destination_id"] for s in stops}
        match = .8 * match + .2 * len(included & set(request.preferred_stops)) / len(set(request.preferred_stops))
    minutes = sum(leg["estimated_minutes"] for leg in result["legs"])
    efficiency = max(0, 1 - minutes / (request.total_days * 480))
    pace = sum(min(1, s["nights"] / max(1, rail.destinations[s["destination_id"]].suggested_nights)) for s in stops) / len(stops)
    diversity = min(1, len({s["country_code"] for s in stops}) / 6)
    endpoint = rail.destinations[result["endpoint_id"]]
    quality = min(1, len(interests & set(endpoint.interest_tags)) / max(1, len(interests)) + (0.2 if endpoint.airport else 0))
    components = dict(interest_match=match, travel_efficiency=efficiency, pace=pace, diversity=diversity, endpoint_quality=quality)
    weights = get_settings().route_score_weights.model_dump()
    return round(sum(components[k] * weights[k] for k in components), 4), components

def build_path(waypoints, rail):
    path = [waypoints[0]]
    mainland = rail.rail_reachable() if hasattr(rail, "rail_reachable") else set(rail.graph)
    try:
        for index, city in enumerate(waypoints[1:], 1):
            if city == path[-1]: continue
            # A fastest segment can run through an earlier stay (or a later
            # waypoint), even when a slightly longer, forward corridor exists.
            blocked = (set(path[:-1]) | set(waypoints[index + 1:])) - {path[-1], city}
            # Non-rail research corridors may complete an endpoint, not act as
            # shortcuts through the rail itinerary or optional intermediate stops.
            # Saved gateway stays (e.g. Athens before Naxos) are part of the
            # non-rail endpoint tail and must remain editable/reopenable.
            final_segment = index == len(waypoints) - 1 or all(point not in mainland for point in waypoints[index:])
            graph = nx.subgraph_view(rail.segment_graph(final_segment), filter_node=lambda node: node not in blocked)
            try:
                segment = nx.shortest_path(graph, path[-1], city, weight="minutes")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                # Branch lines need a return through a hub. Repeated transit
                # cities are valid; the scheduler accounts for each visit.
                segment = rail.path(path[-1], city, allow_endpoint_transfer=final_segment)
            path.extend(segment[1:])
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        raise rail.connection_error(path[-1], city)
    return path

def waypoint_orders(mandatory, endpoint, rail):
    if len(mandatory) <= 5:
        return permutations(mandatory)
    # Bounded insertion search covers every requested stop, without a
    # factorial search or the old first-120-permutations bias.
    def distance(a, b):
        try:
            path = rail.path(a, b)
            return sum(rail.edge(x, y)["minutes"] for x, y in zip(path, path[1:]))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return float("inf")
    beam = [()]
    for city in sorted(mandatory, key=lambda city: (distance("oslo", city), city)):
        proposals = {order[:i] + (city,) + order[i:] for order in beam for i in range(len(order) + 1)}
        def cost(order):
            points = ("oslo", *order, endpoint)
            return sum(distance(a, b) for a, b in zip(points, points[1:]))
        beam = sorted(proposals, key=lambda order: (cost(order), order))[:8]
    return list(dict.fromkeys([*beam, tuple(mandatory), tuple(reversed(mandatory))]))

def generate(request, rail):
    rail = rail.daytime()
    requested = request.required_stops + request.preferred_stops
    unknown = set(requested) - rail.destinations.keys()
    if request.preferences.endpoint_id and request.preferences.endpoint_id not in rail.destinations:
        unknown.add(request.preferences.endpoint_id)
    if unknown:
        raise PlanningError("UNKNOWN_DESTINATION", "Some destinations are not in the curated rail graph.", {"destination_ids": sorted(unknown)})
    region_country = {"southern_italy": "IT", "southern_france": "FR", "spain": "ES", "croatia": "HR", "greece": "GR"}
    country = region_country.get(request.preferences.endpoint_region)
    endpoints = [request.preferences.endpoint_id] if request.preferences.endpoint_id else [d.id for d in rail.destinations.values() if d.is_endpoint and (d.category == "island" if request.preferences.endpoint_region == "islands" else not country or d.country_code == country)]
    unreachable = [city for city in request.required_stops if not nx.has_path(rail.graph, "oslo", city)]
    if unreachable:
        raise rail.connection_error("oslo", unreachable[0])
    for endpoint in endpoints:
        if not rail.destinations[endpoint].is_endpoint:
            raise PlanningError("INVALID_ENDPOINT", "Choose one of the curated southern endpoints.")
    reachable_endpoints = [city for city in endpoints if nx.has_path(rail.graph, "oslo", city)]
    if endpoints and not reachable_endpoints:
        errors = [rail.connection_error("oslo", city) for city in endpoints]
        raise min(errors, key=lambda error: error.details.get("minimum_daily_hours", float("inf")))
    endpoints = reachable_endpoints
    # Preferred means optional. A disconnected preferred city must not veto an
    # otherwise feasible honeymoon (mandatory cities are checked above).
    skipped_preferred = {city for city in request.preferred_stops if not nx.has_path(rail.graph, "oslo", city)}
    minimum_days = min((len(set(request.required_stops) - {endpoint}) + request.preferences.final_stay_nights + 1 for endpoint in endpoints), default=0)
    if minimum_days > request.total_days:
        raise PlanningError("TRIP_DURATION_EXCEEDED", "There are more required overnight stays than fit in this trip.", {"required_days": minimum_days, "available_days": request.total_days})
    candidates, failures, seen = [], [], set()
    for endpoint in endpoints:
        if not rail.destinations[endpoint].is_endpoint:
            raise PlanningError("INVALID_ENDPOINT", "Choose one of the curated southern endpoints.")
        mandatory = [c for c in request.required_stops if c != endpoint]
        for order in waypoint_orders(mandatory, endpoint, rail):
            # A bounded insertion beam can retain several preferred stops together.
            baseline = tuple(order)
            variants, beam = {baseline}, [baseline]
            preferred = set(request.preferred_stops) - set(mandatory) - {endpoint, "oslo"} - skipped_preferred
            for optional in sorted(preferred):
                proposals = set(beam)
                for base in beam:
                    for i in range(len(base)+1):
                        proposals.add(base[:i] + (optional,) + base[i:])
                ranked = []
                for variant in proposals:
                    try:
                        candidate_path = build_path(["oslo", *variant, endpoint], rail)
                        minutes = sum(rail.edge(a,b)["minutes"] for a,b in zip(candidate_path,candidate_path[1:]))
                        ranked.append((-len(preferred & set(variant)), minutes, variant))
                    except PlanningError:
                        continue
                beam = [v for _,_,v in sorted(ranked)[:5]]
                variants.update(beam)
            # Keep the mandatory-only fallback even if preferred detours prove infeasible.
            variants = [baseline] + sorted(variants - {baseline}, key=lambda v: (-len(preferred & set(v)), v))[:29]
            for variant in variants[:30]:
                try:
                    path = build_path(["oslo", *variant, endpoint], rail)
                    result = schedule(path, request, rail)
                    omitted_preferred = set(request.preferred_stops) - {stop["destination_id"] for stop in result["stops"]}
                    if omitted_preferred:
                        result["warnings"].append("Optional cities omitted because they could not fit this supported route: " + ", ".join(rail.destinations[city].name for city in sorted(omitted_preferred)))
                    signature = tuple(s["destination_id"] for s in result["stops"])
                    if signature in seen: continue
                    seen.add(signature)
                    result["score"], result["score_components"] = score_route(result, request, rail)
                    result["name"] = f"South to {rail.destinations[endpoint].name}"
                    candidates.append(result)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    failures.append(PlanningError("ROUTE_NOT_FOUND", "No curated rail connection exists for the requested stops."))
                except PlanningError as error:
                    failures.append(error)
    if not candidates:
        if failures:
            # Prefer an actionable scheduling constraint over a failed
            # permutation or an unreachable alternative endpoint.
            rank = {"PASS_INCOMPATIBLE": 0, "PASS_LIMIT_EXCEEDED": 1, "TRIP_DURATION_EXCEEDED": 2}
            raise min(failures, key=lambda error: (rank.get(error.code, 3), error.details.get("travel_days_estimate", float("inf"))))
        raise PlanningError("ROUTE_NOT_FOUND", "No feasible route found.")
    selected = []
    while candidates and len(selected) < 3:
        def adjusted(candidate):
            cities = {s["destination_id"] for s in candidate["stops"]}
            transit = [candidate["legs"][0]["via"][0]] + [city for leg in candidate["legs"] for city in leg["via"][1:]]
            revisits = len(transit) - len(set(transit))
            minutes = sum(leg["estimated_minutes"] for leg in candidate["legs"])
            overlap = max((len(cities & {s["destination_id"] for s in other["stops"]}) / len(cities | {s["destination_id"] for s in other["stops"]}) for other in selected), default=0)
            return .1 * candidate["score"] - .02 * overlap - .15 * revisits - minutes / 1000
        best = max(candidates, key=adjusted)
        candidates.remove(best)
        selected.append(best)
    return selected
