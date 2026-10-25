"""Explicit, admin-run timetable preparation. Standard library only; no secrets in manifests.

Downloads/stages approved GTFS inputs, audits calendars and provenance, and
generates a timetable-only MOTIS configuration. Does NOT start or import MOTIS.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

MAX_DOWNLOAD = 512 * 1024 * 1024


def catalog_cities():
    """Use the same coordinates as the app; no separately maintained station claims."""
    data = Path(__file__).resolve().parents[1] / "backend" / "data"
    cities = json.loads((data / "destinations.json").read_text())
    cities += json.loads((data / "island_endpoints.json").read_text())
    cities += json.loads((data / "coastal_expansion.json").read_text())["destinations"]
    for city, name, country, lat, lon, _ in json.loads((data / "map_expansion.json").read_text())["cities"]:
        cities.append({"id": city, "name": name, "country_code": country, "latitude": lat, "longitude": lon})
    return cities


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(stream.read()).hexdigest()


def audit(path, cities=None):
    with ZipFile(path) as archive:
        names = set(archive.namelist())
        required = {"agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt"}
        if not required <= names or not {"calendar.txt", "calendar_dates.txt"} & names:
            raise ValueError("Expected root-level GTFS tables and a service calendar")
        if sum(item.file_size for item in archive.infolist()) > 2 * 1024**3:
            raise ValueError("Uncompressed feed exceeds 2 GiB; split/review this input separately")
        def rows(name):
            with archive.open(name) as stream:
                yield from csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig"))
        rail_routes = {row["route_id"] for row in rows("routes.txt") if int(row["route_type"]) == 2 or 100 <= int(row["route_type"]) < 200}
        rail_trips, rail_services, trip_count = set(), set(), 0
        for row in rows("trips.txt"):
            trip_count += 1
            if row["route_id"] in rail_routes:
                rail_trips.add(row["trip_id"])
                rail_services.add(row["service_id"])
        starts, ends, rail_starts, rail_ends = [], [], [], []
        def iso(value):
            return datetime.strptime(value, "%Y%m%d").date().isoformat()
        def bounds(row, start, end):
            start, end = iso(start), iso(end)
            if start > end:
                raise ValueError("Reversed service calendar")
            starts.append(start); ends.append(end)
            if row["service_id"] in rail_services:
                rail_starts.append(start); rail_ends.append(end)
        if "calendar.txt" in names:
            for row in rows("calendar.txt"):
                if any(row.get(day) == "1" for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")):
                    bounds(row, row["start_date"], row["end_date"])
        if "calendar_dates.txt" in names:
            for row in rows("calendar_dates.txt"):
                if row["exception_type"] == "1":
                    bounds(row, row["date"], row["date"])
        if not starts:
            raise ValueError("Feed has no scheduled service dates")
        rail_stops = {row["stop_id"] for row in rows("stop_times.txt") if row["trip_id"] in rail_trips}
        cities = catalog_cities() if cities is None else cities
        city_counts = {city["id"]: 0 for city in cities}
        stop_count = 0
        for row in rows("stops.txt"):
            stop_count += 1
            if row["stop_id"] not in rail_stops:
                continue
            lat, lon = float(row["stop_lat"]), float(row["stop_lon"])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Invalid rail-stop coordinates")
            for city in cities:
                if abs(lat - city["latitude"]) > .03 or abs(lon - city["longitude"]) > .15:
                    continue
                a, b = math.radians(lat), math.radians(city["latitude"])
                hav = math.sin((a-b)/2)**2 + math.cos(a)*math.cos(b)*math.sin(math.radians(lon-city["longitude"])/2)**2
                if 2 * 6371000 * math.asin(min(1, math.sqrt(hav))) <= 3000:
                    city_counts[city["id"]] += 1
        return {"service_start": min(starts), "service_end": max(ends),
                "rail_service_start": min(rail_starts) if rail_starts else None,
                "rail_service_end": max(rail_ends) if rail_ends else None,
                "stop_count": stop_count, "trip_count": trip_count,
                "rail_route_count": len(rail_routes), "rail_trip_count": len(rail_trips),
                "rail_stop_count": len(rail_stops), "city_stop_counts": city_counts,
                "city_radius_meters": 3000}


def prepare(manifest_path, work_dir, selected=None, extra_manifests=None):
    manifest_path, work_dir = Path(manifest_path).resolve(), Path(work_dir).resolve()
    feeds = []
    for path in [manifest_path, *(Path(value).resolve() for value in extra_manifests or [])]:
        for feed in json.loads(path.read_text())["feeds"]:
            if feed.get("path"):
                feed["path"] = str((path.parent / feed["path"]).resolve())
            feeds.append(feed)
    ids = [feed["id"] for feed in feeds]
    if len(ids) != len(set(ids)) or any(not re.fullmatch(r"[a-z][a-z0-9]{0,31}", tag) for tag in ids):
        raise ValueError("Feed IDs must be unique lowercase alphanumeric tags, without underscores")
    if selected and set(selected) - set(ids):
        raise ValueError("Unknown feed ID")
    feeds = [feed for feed in feeds if not selected or feed["id"] in selected]
    if not feeds:
        raise ValueError("Select at least one reviewed feed")
    for feed in feeds:
        for key in ("name", "source_url", "license_url", "attribution", "coverage"):
            if not feed.get(key):
                raise ValueError(f"Missing {key} for {feed['id']}")
        for key in ("source_url", "license_url"):
            if not feed[key].startswith("https://"):
                raise ValueError(f"{key} must be a public HTTPS reference")
        if bool(feed.get("url")) == bool(feed.get("path")):
            raise ValueError("Each feed needs either a download URL or a local archive path")
        if feed.get("url") and not feed["url"].startswith("https://"):
            raise ValueError("Feed downloads must use HTTPS")
        if not isinstance(feed.get("min_download_interval_hours", 0), (int, float)) or not 0 <= feed.get("min_download_interval_hours", 0) <= 720:
            raise ValueError("Download interval must be between 0 and 720 hours")
        headers = feed.get("headers", {})
        if not isinstance(headers, dict) or any(key != "ET-Client-Name" or not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]{3,120}", value) for key, value in headers.items()):
            raise ValueError("Only a public ET-Client-Name identification header is allowed; never put credentials in manifests")
    work_dir.mkdir(parents=True, exist_ok=True)
    try:
        previous = {record["id"]: record for record in json.loads((work_dir / "feeds-status.json").read_text())["feeds"]}
    except (OSError, ValueError, KeyError, TypeError):
        previous = {}
    # Complete every download and validation before replacing any prepared input.
    with tempfile.TemporaryDirectory(prefix="prepare-", dir=work_dir) as scratch:
        staged = Path(scratch)
        records, datasets = [], {}
        for feed in feeds:
            archive = staged / (feed["id"] + ".zip")
            downloaded_at = datetime.now(timezone.utc).isoformat()
            fingerprint = hashlib.sha256(str(feed.get("url") or feed.get("path")).encode()).hexdigest()
            old = previous.get(feed["id"], {})
            cached = work_dir / "feeds" / (feed["id"] + ".zip")
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(old["downloaded_at"])).total_seconds() / 3600
                reuse = feed.get("url") and old.get("source_fingerprint") == fingerprint and 0 <= age < feed.get("min_download_interval_hours", 0)
            except (KeyError, ValueError, TypeError):
                reuse = False
            if feed.get("path"):
                source = (manifest_path.parent / feed["path"]).resolve()
                if source.stat().st_size > MAX_DOWNLOAD:
                    raise ValueError("Feed archive exceeds 512 MiB")
                shutil.copyfile(source, archive)
            elif reuse:
                if not cached.is_file() or checksum(cached) != old.get("sha256"):
                    raise ValueError(f"Cached {feed['id']} archive is missing or changed. Restore it or wait for the publisher download interval.")
                shutil.copyfile(cached, archive)
                downloaded_at = old["downloaded_at"]
            else:
                request = Request(feed["url"], headers={"User-Agent": "InterrailHelper-feed-preparation/0.1", **feed.get("headers", {})})
                with urlopen(request, timeout=60) as response, archive.open("wb") as output:
                    if not response.url.startswith("https://"):
                        raise ValueError("Feed redirected away from HTTPS")
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_DOWNLOAD:
                            raise ValueError("Feed archive exceeds 512 MiB")
                        output.write(chunk)
            dates = audit(archive)
            records.append({k: feed[k] for k in ("id", "name", "source_url", "license_url", "attribution", "coverage")})
            records[-1].update(**dates, sha256=checksum(archive), downloaded_at=downloaded_at, source_fingerprint=fingerprint)
            datasets[feed["id"]] = {"path": f"feeds/{feed['id']}.zip", "extend_calendar": False}
        config = {"server": {"host": "0.0.0.0", "port": 8080},
                  "timetable": {"first_day": "TODAY", "num_days": 365, "datasets": datasets},
                  "street_routing": False, "geocoding": False, "osr_footpath": False,
                  "limits": {"routing_max_timeout_seconds": 25, "plan_max_results": 8}}
        (work_dir / "feeds").mkdir(exist_ok=True)
        for feed in feeds:
            (staged / (feed["id"] + ".zip")).replace(work_dir / "feeds" / (feed["id"] + ".zip"))
        # JSON is valid YAML, avoiding a dependency for this standalone tool.
        for filename, content in (("config.yml", config), ("feeds-status.json", {"state": "prepared_not_import_verified", "feeds": records})):
            path = staged / filename
            path.write_text(json.dumps(content, indent=2) + "\n")
            path.replace(work_dir / filename)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(Path(__file__).with_name("feeds.json")))
    parser.add_argument("--work-dir", default=str(Path(__file__).with_name("work")))
    parser.add_argument("--feed", action="append", help="Select feed IDs; repeat to combine. Default: all manifest entries.")
    parser.add_argument("--extra-manifest", action="append", default=[], help="Merge additional reviewed manifests; repeat to combine. Local paths are relative to their own manifest.")
    args = parser.parse_args()
    records = prepare(args.manifest, args.work_dir, args.feed, args.extra_manifest)
    for record in records:
        print(f"{record['id']}: {record['trip_count']} trips; service envelope {record['service_start']} to {record['service_end']}")
        print(f"  Rail: {record['rail_trip_count']} trips, {record['rail_stop_count']} stops; rail envelope {record['rail_service_start']} to {record['rail_service_end']}")
        print("  Rail stops within 3 km of catalog cities: " + (", ".join(city for city, count in record["city_stop_counts"].items() if count) or "none"))
    print("Prepared only. Stop MOTIS before re-importing; import and start it using the documented Docker commands.")
