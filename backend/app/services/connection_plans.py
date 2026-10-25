"""Transparent local planning allowances, not operator minima or live schedules."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.providers.motis import TIMEZONES
from app.services.errors import PlanningError

NOTICE = 'Illustrative allowances, not operator minimums or protected connections. Confirm the ticket’s terminal, check-in deadline and local transport. Waiting for actual departures is not included.'
STARTS = {
    'brindisi': 'Brindisi railway station → Costa Morena ferry terminal · separate bus / road transfer',
    'ancona': 'Ancona railway station → assigned ferry check-in office / terminal',
    'salerno': 'Salerno railway station → assigned commercial-port ferry terminal',
    'piombino': 'Piombino rail arrival → Piombino Marittima ferry berth · check final train / bus / road access',
    'corfu': 'Corfu stay / arrival port → confirmed Paxos departure terminal',
    'lefkada': 'Lefkada Town arrival point → onward transfer meeting point',

    'bari': 'Bari Centrale → assigned Bari ferry terminal',
    'naples': 'Napoli Centrale → assigned Naples ferry terminal',
    'genoa': 'Genova Piazza Principe → assigned Genoa ferry terminal',
    'athens': 'Athens city / rail arrival → assigned Piraeus gate',
    'split': 'Split railway station → assigned Split ferry berth',
    'patras': 'Patras arrival point → assigned departure terminal',
}


def connection_plan(edge):
    """Allocate the existing budget exactly once; never append hidden minutes."""
    components = edge.get('components', [])
    ferry_indexes = [i for i, part in enumerate(components) if part['mode'] == 'ferry']
    if not ferry_indexes:
        steps = [{**part, 'kind': 'ground_transfer', 'label': f"{part.get('origin', '')} → {part.get('destination', '')}"} for part in components]
        return {'steps': steps, 'before_departure_minutes': 0,
                'after_arrival_minutes': edge['estimated_minutes'], 'ferry_count': 0,
                'overnight_nights': edge.get('overnight_nights', 0),
                'arrival_time_status': 'unknown', 'notice': NOTICE,
                'arrival_notes': ['Arrange onward road transport before arriving. No scheduled bus or ferry is asserted on this segment.']}
    first_ferry, last_ferry = min(ferry_indexes), max(ferry_indexes)
    buffer = sum(part['estimated_minutes'] for part in components if part['mode'] == 'buffer')
    # These are app assumptions, deliberately not claims about operator deadlines.
    access = min(45, buffer // 4)
    check_in = min(90, buffer // 2)
    disembark = min(30, buffer // 8)
    destination = min(30, buffer // 8)
    contingency = buffer - access - check_in - disembark - destination
    steps = []
    def add(kind, label, minutes):
        if minutes:
            steps.append({'kind': kind, 'label': label, 'estimated_minutes': minutes})
    add('port_access', STARTS.get(edge['origin_id'], 'Arrival point → assigned ferry terminal'), access)
    for part in components[:first_ferry]:
        if part['mode'] != 'buffer':
            add('ground_before_ferry', f"{part.get('origin', '')} → {part.get('destination', '')}", part['estimated_minutes'])
    add('check_in', 'Ferry check-in and boarding allowance · verify ticket deadline', check_in)
    add('contingency', 'Extra connection margin before boarding', contingency)
    for index, part in enumerate(components[first_ferry:]):
        if part['mode'] == 'buffer':
            continue
        kind = 'ferry' if part['mode'] == 'ferry' else 'ground_after_ferry'
        add(kind, f"{part.get('origin', '')} → {part.get('destination', '')}", part['estimated_minutes'])
        if index + first_ferry == last_ferry:
            add('disembarkation', 'Disembark and leave the arrival terminal', disembark)
    add('destination_access', 'Arrival transport / access to the named stay or onward station', destination)
    before = sum(step['estimated_minutes'] for step in steps[:next(i for i, step in enumerate(steps) if step['kind'] == 'ferry')])
    last_index = max(i for i, step in enumerate(steps) if step['kind'] == 'ferry')
    after = sum(step['estimated_minutes'] for step in steps[last_index + 1:])
    assert sum(step['estimated_minutes'] for step in steps) == edge['estimated_minutes']
    return {'steps': steps, 'before_departure_minutes': before, 'after_arrival_minutes': after,
            'ferry_count': len(ferry_indexes), 'overnight_nights': edge.get('overnight_nights', 0),
            'arrival_time_status': 'unknown', 'notice': NOTICE,
            'arrival_notes': ['Arrival hour is unknown until you enter a researched sailing.',
                              'For early or late arrivals, arrange transport, luggage storage and accommodation check-in separately.',
                              'An overnight allowance is not a cabin booking. A missed onward departure may require an extra night.']}


def local_time(value, zone_name):
    if value.tzinfo is not None:
        raise PlanningError('INVALID_LOCAL_TIME', 'Enter the local clock time without an offset; the location supplies its timezone.')
    zone = ZoneInfo(zone_name)
    local = value.replace(tzinfo=zone)
    if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != value or local.utcoffset() != local.replace(fold=1).utcoffset():
        raise PlanningError('INVALID_LOCAL_TIME', 'This time is skipped or ambiguous at a daylight-saving change. Use a different, unambiguous time.')
    return local.astimezone(timezone.utc)


def check_connection(request, edge, origin, destination):
    plan = connection_plan(edge)
    if plan['ferry_count'] != 1:
        raise PlanningError('UNSUPPORTED_CONNECTION', 'Choose a corridor with one ferry crossing. Check ground-only travel separately.')
    origin_zone, destination_zone = TIMEZONES.get(origin.country_code), TIMEZONES.get(destination.country_code)
    if not origin_zone or not destination_zone:
        raise PlanningError('UNSUPPORTED_TIMEZONE', 'Timezone information for this connection is unavailable.')
    departure = local_time(request.ferry_departure, origin_zone)
    arrival = local_time(request.ferry_arrival, destination_zone)
    if arrival <= departure or arrival - departure > timedelta(days=7):
        raise PlanningError('INVALID_TIMES', 'Arrival must follow departure, within seven days. Check local dates and timezones.')
    before_minutes = plan['before_departure_minutes']
    for kind, override in [('check_in', request.ferry_check_in_minutes), ('port_access', request.port_access_minutes)]:
        if override is not None:
            before_minutes += override - sum(step['estimated_minutes'] for step in plan['steps'] if step['kind'] == kind)
    latest_start = departure - timedelta(minutes=before_minutes)
    ready = arrival + timedelta(minutes=plan['after_arrival_minutes'])
    def stamp(value, zone):
        return value.astimezone(ZoneInfo(zone)).isoformat()
    before_margin, after_margin = None, None
    if request.arrival_at_start is not None:
        before_margin = int((latest_start - local_time(request.arrival_at_start, origin_zone)).total_seconds() // 60)
    if request.onward_departure is not None:
        after_margin = int((local_time(request.onward_departure, destination_zone) - ready).total_seconds() // 60) - request.onward_check_in_minutes - request.onward_transfer_minutes
    margins = [value for value in (before_margin, after_margin) if value is not None]
    arrival_local = arrival.astimezone(ZoneInfo(destination_zone))
    departure_local = departure.astimezone(ZoneInfo(origin_zone))
    ready_local = ready.astimezone(ZoneInfo(destination_zone))
    early_late = any(value.hour < 7 or value.hour >= 22 for value in (arrival_local, ready_local))
    warnings = []
    if early_late:
        warnings.append('Early/late arrival: confirm transport operating hours, luggage storage and accommodation access. None is verified here.')
    if after_margin is not None and after_margin < 0:
        warnings.append('The onward departure does not fit these allowances. Choose a later service or budget an extra overnight stay.')
    if before_margin is not None and before_margin < 0:
        warnings.append('Arrival at the starting point is too late for the port-access, check-in and connection allowances.')
    return {'before_departure_minutes': before_minutes, 'after_arrival_minutes': plan['after_arrival_minutes'],
            'status': 'insufficient_margin' if any(value < 0 for value in margins) else 'fits_allowances' if margins else 'times_only',
            'latest_arrival_at_start': stamp(latest_start, origin_zone),
            'ready_at_destination': stamp(ready, destination_zone),
            'origin_timezone': origin_zone, 'destination_timezone': destination_zone,
            'before_margin_minutes': before_margin, 'onward_margin_minutes': after_margin,
            'arrival_day_change': (arrival_local.date() - departure_local.date()).days,
            'early_or_late_arrival': early_late,
            'ready_day_change': (ready_local.date() - arrival_local.date()).days,
            'crossing_minutes': int((arrival - departure).total_seconds() // 60),
            'warnings': warnings, 'notice': NOTICE + ' User-entered times are not verified or saved, and do not alter your itinerary.'}
