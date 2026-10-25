"""Explicit dated searches against the configured local MOTIS; no feed downloads.

Run after import/restart: python -m app.scripts.check_timetable_corridors --date YYYY-MM-DD
This does not mutate itineraries or persist snapshots. Missing journeys indicate
coverage/search limitations, not proof that a real-world journey is impossible.
"""
import argparse
import asyncio
from datetime import date
import json
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import Destination
from app.providers.motis import MotisTimetables
from app.schemas.integrations import RailTimetableRequest

CORRIDORS = [
    ('oslo', 'gothenburg'), ('gothenburg', 'copenhagen'),
    ('copenhagen', 'hamburg'), ('hamburg', 'munich'),
    ('munich', 'milan'), ('milan', 'bari'),
    ('paris', 'milan'), ('zurich', 'milan'),
]


async def check_corridors(day, cities, provider):
    reports = []
    for origin, destination in CORRIDORS:
        if origin not in cities or destination not in cities:
            reports.append({'origin_id': origin, 'destination_id': destination, 'status': 'catalog_missing'})
            continue
        result = await provider.search(RailTimetableRequest(origin_id=origin, destination_id=destination,
                                                          departure_date=day), cities[origin], cities[destination])
        reports.append({'origin_id': origin, 'destination_id': destination,
                        'status': result['status'], 'journeys': len(result['journeys']),
                        'coverage_status': result.get('coverage', {}).get('status'),
                        'message': result['message']})
        if result['status'] == 'not_configured':
            break
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date', required=True, type=date.fromisoformat)
    args = parser.parse_args()
    with SessionLocal() as db:
        cities = {city.id: city for city in db.scalars(select(Destination)).all()}
        reports = asyncio.run(check_corridors(args.date, cities, MotisTimetables()))
    print(json.dumps({'date': args.date.isoformat(), 'corridors': reports}, indent=2))
    raise SystemExit(0 if len(reports) == len(CORRIDORS) and all(row['status'] == 'scheduled' for row in reports) else 1)


if __name__ == '__main__':
    main()
