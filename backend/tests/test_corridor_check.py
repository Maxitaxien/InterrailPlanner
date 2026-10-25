import asyncio
from datetime import date
from types import SimpleNamespace

from app.scripts.check_timetable_corridors import CORRIDORS, check_corridors


def test_corridor_check_uses_exact_date_and_each_city_pair_without_persisting():
    calls = []
    class Provider:
        async def search(self, request, origin, destination):
            calls.append(request)
            return {'status': 'scheduled', 'journeys': [{}], 'coverage': {'status': 'prepared_candidates'}, 'message': 'Synthetic'}
    cities = {city: SimpleNamespace(id=city) for pair in CORRIDORS for city in pair}
    day = date(2027, 6, 10)
    results = asyncio.run(check_corridors(day, cities, Provider()))
    assert [(row.origin_id, row.destination_id) for row in calls] == CORRIDORS
    assert all(row.departure_date == day for row in calls)
    assert len(results) == 8 and all(row['journeys'] == 1 for row in results)


def test_corridor_check_stops_when_disabled_and_distinguishes_missing_catalog():
    class Provider:
        async def search(self, *args):
            return {'status': 'not_configured', 'journeys': [], 'message': 'Disabled'}
    cities = {city: SimpleNamespace(id=city) for pair in CORRIDORS for city in pair}
    assert len(asyncio.run(check_corridors(date(2027, 6, 10), cities, Provider()))) == 1
    results = asyncio.run(check_corridors(date(2027, 6, 10), {}, Provider()))
    assert all(row['status'] == 'catalog_missing' for row in results)
