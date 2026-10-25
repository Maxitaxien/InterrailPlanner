import json
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.entities import Destination, RailConnection
from app.models.integrations import Attraction

DATA = Path(__file__).resolve().parents[2] / "data"
def seed(db: Session):
    for filename, model in [("destinations.json", Destination), ("rail_connections.json", RailConnection), ("attractions.json", Attraction)]:
        for values in json.loads((DATA / filename).read_text()):
            db.merge(model(**values))
    expansion = json.loads((DATA / "map_expansion.json").read_text())
    for city_id, name, country, latitude, longitude, tags in expansion["cities"]:
        db.merge(Destination(id=city_id, name=name, country_code=country,
            latitude=latitude, longitude=longitude, category="major",
            interest_tags=tags, suggested_nights=2, is_endpoint=False, airport=None))
    db.flush()
    for city in json.loads((DATA / "island_endpoints.json").read_text()):
        db.merge(Destination(**city, category="island", suggested_nights=4, is_endpoint=True))
    db.flush()
    for origin, destination, minutes in expansion["corridors"]:
        for a, b in [(origin, destination), (destination, origin)]:
            db.merge(RailConnection(id=f"{a}-{b}-map", origin_id=a, destination_id=b,
                estimated_minutes=minutes, transfers=1, service_type="rail corridor",
                night_train=False, source=expansion["source"], estimate_quality="illustrative",
                reviewed_at=None, reservation_warning=expansion["notice"]))
    coastal = json.loads((DATA / "coastal_expansion.json").read_text())
    for city in coastal["destinations"]:
        db.merge(Destination(**city))
    db.flush()
    for attraction in coastal["attractions"]:
        db.merge(Attraction(**attraction))
    for corridor in coastal["rail_corridors"]:
        for origin, destination in [(corridor["origin_id"], corridor["destination_id"]), (corridor["destination_id"], corridor["origin_id"])]:
            db.merge(RailConnection(id=f"{origin}-{destination}-coastal", origin_id=origin, destination_id=destination,
                estimated_minutes=corridor["estimated_minutes"], transfers=1, service_type="rail corridor",
                night_train=False, source=corridor["source"], estimate_quality="illustrative", reviewed_at=None,
                reservation_warning=corridor["reservation_warning"]))
    db.commit()

if __name__ == "__main__":
    with SessionLocal() as db:
        seed(db)
    print("Seed import complete (idempotent).")
