"""Calendar-only travel plans and immutable timetable research. No bookings/API calls."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from app.providers.motis import TIMEZONES, RAIL_MODES
from app.services.errors import PlanningError

NIGHT_RULE_URL = "https://www.interrail.com/en/support/interested-in-interrailing/what-is-a-travel-day"


def leg_keys(stop_ids):
    visits, labels = {}, []
    for city in stop_ids:
        visits[city] = visits.get(city, 0) + 1
        labels.append(f"{city}:{visits[city]}")
    return [f"{a}->{b}" for a, b in zip(labels, labels[1:])]


def timing(journey, origin_country, destination_country):
    """Never infer a sleeper/cabin from crossing midnight or a service label."""
    try:
        start, end = (datetime.fromisoformat(journey[key]) for key in ('departure', 'arrival'))
        if start.tzinfo is None or end.tzinfo is None or not start < end or (end-start).total_seconds() > 7*86400:
            raise ValueError('Invalid journey interval')
        departure = start.astimezone(ZoneInfo(TIMEZONES[origin_country]))
        arrival = end.astimezone(ZoneInfo(TIMEZONES[destination_country]))
        boardings, rail_arrival_dates, rail_minutes, previous = set(), set(), 0, start
        for leg in journey['legs']:
            a, b = (datetime.fromisoformat(leg[key]) for key in ('departure', 'arrival'))
            if a.tzinfo is None or b.tzinfo is None or a < previous or b < a or b > end:
                raise ValueError('Invalid connection chronology')
            previous = b
            if leg['mode'] in RAIL_MODES:
                # Count every rail boarding conservatively, including through-service
                # continuations until their service identity can be established.
                zone = leg.get('origin_timezone') or TIMEZONES[origin_country]
                boardings.add(a.astimezone(ZoneInfo(zone)).date())
                arrival_zone = leg.get('destination_timezone') or TIMEZONES[destination_country]
                rail_arrival_dates.add(b.astimezone(ZoneInfo(arrival_zone)).date())
                rail_minutes += max(1, round((b-a).total_seconds()/60))
            elif leg['mode'] != 'WALK':
                raise ValueError('Nonrail journey')
        if not boardings or previous != end:
            raise ValueError('Incomplete journey')
        nights = (arrival.date() - departure.date()).days
        if nights < 0:
            raise ValueError('Invalid local dates')
        return {'departure_date': departure.date(), 'arrival_date': arrival.date(),
                'travel_nights_estimate': nights, 'estimated_minutes': max(1, round((end-start).total_seconds()/60)),
                'rail_minutes': rail_minutes, 'boarding_dates': sorted(boardings),
                'last_rail_date': max(rail_arrival_dates)}
    except (KeyError, TypeError, ValueError):
        raise PlanningError('INVALID_JOURNEY', 'This timetable journey has invalid or incomplete times. Search again.') from None


def annotate_plans(result):
    """Dynamic freshness labels do not mutate saved snapshots or query providers."""
    now = datetime.now(timezone.utc)
    legs = []
    for original in result.get('legs', []):
        leg = dict(original)
        plan = leg.get('travel_plan')
        if plan and plan.get('kind') == 'timetable':
            plan = dict(plan)
            expires = datetime.fromisoformat(plan['recheck_after'])
            plan['needs_recheck'] = now >= expires
            plan['status_label'] = 'Saved timetable · recheck needed' if plan['needs_recheck'] else 'Saved timetable · not booked'
            leg['travel_plan'] = plan
        legs.append(leg)
    return {**result, 'legs': legs}
