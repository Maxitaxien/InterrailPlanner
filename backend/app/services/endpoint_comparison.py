"""Read-only comparisons from one chosen Italian city, using the app's graph."""
import networkx as nx
from app.services.airport_access import airport_access
from app.services.errors import PlanningError


def compare_endpoints(request, rail):
    origin = rail.destinations.get(request.origin_id)
    if not origin or origin.country_code != 'IT' or origin.id not in rail.rail_reachable():
        raise PlanningError('INVALID_COMPARISON_ORIGIN', 'Choose a connected Italian city as the common starting point.')
    for city in request.endpoint_ids:
        if city not in rail.destinations or not rail.destinations[city].is_endpoint:
            raise PlanningError('INVALID_ENDPOINT', 'Choose catalogued final-stay destinations.', {'destination_id': city})
    results = []
    for endpoint_id in request.endpoint_ids:
        city = rail.destinations[endpoint_id]
        base = {'endpoint_id': city.id, 'name': city.name, 'country_code': city.country_code,
                'category': city.category, 'interest_tags': city.interest_tags,
                'airport_access': airport_access(city)}
        try:
            path = rail.path(origin.id, city.id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            results.append({**base, 'status': 'no_modeled_route', 'selectable': False,
                            'notice': 'No modeled access route from this origin. This does not prove that real transport is unavailable.'})
            continue
        connections = []
        totals = dict(rail=0, ferry=0, ground=0, port_access=0, check_in=0, disembarkation=0, destination_access=0, contingency=0)
        ferries, ground_legs, overnights, seasonal = 0, 0, 0, False
        for a, b in zip(path, path[1:]):
            edge = rail.edge(a, b)
            connections.append({'origin_id': a, 'destination_id': b, 'origin': rail.destinations[a].name,
                                'destination': rail.destinations[b].name, 'estimated_minutes': edge['minutes'],
                                'mode': edge.get('mode', 'rail'), 'service_type': edge.get('service_type'),
                                'connection_id': edge['connection_id'], 'source_url': edge.get('source_url') or edge.get('source'),
                                'reservation_warning': edge.get('reservation_warning'),
                                'connection_plan': edge.get('connection_plan'),
                                'components': edge.get('components', []), 'seasonal': edge.get('seasonal', False)})
            overnights += edge.get('overnight_nights', 0)
            seasonal |= edge.get('seasonal', False)
            if edge.get('mode', 'rail') == 'rail':
                totals['rail'] += edge['minutes']
                continue
            plan = edge['connection_plan']
            ferries += plan['ferry_count']
            for step in plan['steps']:
                kind = step['kind']
                group = 'ground' if kind.startswith('ground') else kind
                totals[group] += step['estimated_minutes']
                ground_legs += int(group == 'ground')
        minutes = sum(edge['estimated_minutes'] for edge in connections)
        assert sum(totals.values()) == minutes
        nights = max(overnights, minutes // 1440)
        burden = 'Longer journey' if minutes > 1080 or ferries >= 2 else 'Some onward travel' if minutes > 480 or ground_legs else 'Shorter journey'
        caveats = ['Waiting for actual departures, disruption and timetable compatibility are unknown. Earlier holiday legs and the return airport journey are excluded.']
        if ferries > 1:
            caveats.append('Separate ferry connections may require a night between sailings. Their timetables have not been matched.')
        if seasonal:
            caveats.append('A potentially seasonal sailing is included; check your travel dates.')
        if ferries:
            caveats.append('Arrival hours and cabin availability are unknown. Check overnight arrival access before booking onward travel.')
        results.append({**base, 'status': 'modeled', 'selectable': True, 'path': path,
                        'route_names': [rail.destinations[point].name for point in path],
                        'connections': connections, 'estimated_minutes': minutes, 'breakdown_minutes': totals,
                        'ferry_crossings': ferries, 'onward_ground_legs': ground_legs,
                        'transit_nights_lower_bound': nights, 'seasonal': seasonal,
                        'burden': burden, 'caveats': caveats, 'arrival_time_status': 'unknown'})
    return {'origin_id': origin.id, 'origin_name': origin.name, 'comparisons': results,
            'notice': 'Local planning estimates from a common Italian starting point, not live journeys or a full holiday feasibility check. No provider request, booking or itinerary change was made.'}
