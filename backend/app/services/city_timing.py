"""Server-owned visit timing; only coarse month/season context may reach search."""
from calendar import month_name
from datetime import date, timedelta

from sqlalchemy import select
from app.models.entities import Itinerary, TripStop
from app.services.errors import PlanningError


def travel_context(db, trip, city, itinerary_id=None):
    query = select(Itinerary).where(Itinerary.trip_id == trip.id)
    if itinerary_id:
        itinerary = db.scalar(query.where(Itinerary.id == str(itinerary_id)))
        if not itinerary:
            raise PlanningError('NOT_FOUND', 'Itinerary not found for this trip.', status=404)
    else:
        itinerary = db.scalar(query.where(Itinerary.is_selected.is_(True)).limit(1))
    if trip.start_date is None:
        return None  # Do not infer a season from today's date for flexible trips.
    visits = []
    if itinerary:
        stops = db.scalars(select(TripStop).where(TripStop.itinerary_id == itinerary.id,
            TripStop.destination_id == city.id).order_by(TripStop.position)).all()
        visits = [{'arrival_date': stop.arrival_date.isoformat(), 'departure_date': stop.departure_date.isoformat(),
                   'nights': stop.nights} for stop in stops if stop.arrival_date and stop.departure_date]
    intervals = [(date.fromisoformat(visit['arrival_date']), date.fromisoformat(visit['departure_date'])) for visit in visits]
    if not intervals:
        intervals = [(trip.start_date, trip.start_date + timedelta(days=trip.total_days - 1))]
    months = set()
    for start, end in intervals:
        current = start.replace(day=1)
        while current <= end:
            months.add((current.year, current.month))
            if (current.year, current.month) == (end.year, end.month):
                break
            current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    periods = [{'month': month_name[month], 'year': year,
                'season': ('winter', 'spring', 'summer', 'autumn')[(month % 12) // 3]} for year, month in sorted(months)]
    return {'scope': 'city_visit' if visits else 'trip_window', 'status': 'planned_not_confirmed',
            'start_date': min(start for start, _ in intervals).isoformat(),
            'end_date': max(end for _, end in intervals).isoformat(), 'visits': visits, 'periods': periods}


def seasonal_context(timing):
    if timing is None:
        return None
    return {'scope': timing['scope'], 'status': timing['status'], 'periods': timing['periods'],
            'season_basis': 'Northern Hemisphere meteorological seasons, not a weather forecast'}
