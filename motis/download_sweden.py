"""Explicit, quota-protected GTFS Sverige 2 download. No startup/background calls.

Reads TRAFIKLAB_GTFS_API_KEY from the process environment or an optional .env
file only when a network refresh is actually needed. Never prints credentials,
provider URLs, response bodies or raw network exceptions.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from prepare import MAX_DOWNLOAD, audit, checksum

KEY_NAME = "TRAFIKLAB_GTFS_API_KEY"
ROOT = Path(__file__).resolve().parents[1]
DAY = 24 * 60 * 60


class DownloadError(ValueError):
    """Safe to display: never contains upstream URLs, responses or secrets."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise DownloadError("Provider redirect blocked to avoid forwarding the key.")


def read_key(env_file, environ):
    key = environ.get(KEY_NAME, "").strip()
    if not key and env_file is not None:
        try:
            # Parse only this literal variable; never execute or interpolate .env.
            for line in Path(env_file).read_text().splitlines():
                match = re.fullmatch(r"\s*(?:export\s+)?TRAFIKLAB_GTFS_API_KEY\s*=\s*(.*?)\s*", line)
                if match:
                    value = match.group(1)
                    if value.startswith(('"', "'")):
                        quote = value[0]
                        end = value.find(quote, 1)
                        if end < 0 or value[end+1:].strip() and not value[end+1:].strip().startswith('#'):
                            raise DownloadError("Invalid quoting for TRAFIKLAB_GTFS_API_KEY.")
                        key = value[1:end]
                    else:
                        key = value.split('#', 1)[0].strip()
        except OSError:
            raise DownloadError("Cannot read the selected key file. Set TRAFIKLAB_GTFS_API_KEY in your environment or .env.") from None
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,200}", key):
        raise DownloadError("Set a valid TRAFIKLAB_GTFS_API_KEY in your environment or .env; the key is not shown.")
    return key


def cached_archive(directory):
    archive, status = directory / "sweden.zip", directory / "sweden-status.json"
    if not archive.is_file():
        return None
    try:
        record = json.loads(status.read_text())
        if record.get('sha256') == checksum(archive):
            return record
        return None  # A previously checked archive was changed; do not silently trust it.
    except FileNotFoundError:
        try:
            dates = audit(archive)
            return {"sha256": checksum(archive), "downloaded_at": None,
                    "service_start": dates['service_start'], "service_end": dates['service_end']}
        except Exception:
            return None
    except (OSError, ValueError, AttributeError):
        return None


def download(directory, refresh=False, env_file=None, environ=None, open_url=None, now=None):
    directory = Path(directory).resolve()
    cached = cached_archive(directory)
    if not refresh:
        if cached:
            return {**cached, "status": "cached", "requests_made": 0}
        raise DownloadError("No validated cached Swedish feed. Run this command with --refresh to explicitly allow a download.")
    now = now or datetime.now(timezone.utc)
    timestamp = now.timestamp()
    if cached and cached.get('downloaded_at'):
        try:
            age = timestamp - datetime.fromisoformat(cached['downloaded_at']).timestamp()
            if age < DAY:
                return {**cached, "status": "cached", "requests_made": 0}
        except (TypeError, ValueError):
            pass
    key = read_key(env_file, os.environ if environ is None else environ)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(directory / "trafiklab-requests.sqlite3", timeout=1, isolation_level=None)
        with connection:
            connection.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, attempted_at REAL NOT NULL, succeeded INTEGER NOT NULL DEFAULT 0)")
            connection.execute("BEGIN IMMEDIATE")
            # Recheck after acquiring the cross-process lock.
            latest = connection.execute("SELECT MAX(attempted_at), MAX(CASE WHEN succeeded=1 THEN attempted_at END) FROM attempts").fetchone()
            count = connection.execute("SELECT COUNT(*) FROM attempts WHERE attempted_at >= ?", (timestamp - 30 * DAY,)).fetchone()[0]
            if count >= 50:
                raise DownloadError("Local safety limit reached: 50 download attempts in the last 30 days. No request made.")
            if latest[0] is not None and timestamp - latest[0] < 60:
                raise DownloadError("Wait at least 60 seconds between attempts. No request made.")
            if latest[1] is not None and timestamp - latest[1] < DAY:
                cached = cached_archive(directory)
                if cached:
                    return {**cached, "status": "cached", "requests_made": 0}
                raise DownloadError("The last successful download was less than 24 hours ago, but its cache is damaged. Restore it or wait; no request made.")
            attempt = connection.execute("INSERT INTO attempts (attempted_at) VALUES (?)", (timestamp,)).lastrowid
            # Persist the attempt before I/O, including timeouts/crashes/failures.
            connection.execute("COMMIT")
            connection.execute("BEGIN IMMEDIATE")
            try:
                opener = open_url or build_opener(NoRedirect()).open
                request = Request("https://api.resrobot.se/gtfs/sweden.zip?" + urlencode({"key": key}),
                                  headers={"User-Agent": "InterrailHelper-explicit-feed-download/0.1"})
                with tempfile.TemporaryDirectory(prefix="sweden-", dir=directory) as scratch:
                    staged = Path(scratch) / "sweden.zip"
                    with opener(request, timeout=60) as response, staged.open('wb') as output:
                        size = 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > MAX_DOWNLOAD:
                                raise DownloadError("Feed archive exceeds the download size limit.")
                            output.write(chunk)
                    dates = audit(staged)
                    record = {"sha256": checksum(staged), "downloaded_at": now.isoformat(),
                              "service_start": dates['service_start'], "service_end": dates['service_end']}
                    status = Path(scratch) / "sweden-status.json"
                    status.write_text(json.dumps(record, indent=2) + '\n')
                    staged.replace(directory / "sweden.zip")
                    status.replace(directory / "sweden-status.json")
                connection.execute("UPDATE attempts SET succeeded=1 WHERE id=?", (attempt,))
                return {**record, "status": "downloaded", "requests_made": 1, "local_attempts_last_30_days": count + 1}
            except Exception:
                # Never expose upstream exception text; HTTP errors contain the keyed URL.
                raise DownloadError("Download or validation failed; no automatic retry. Any prior archive was retained unless publication had already completed. This attempt counts toward the local quota. Check the key and provider status.") from None
    except sqlite3.Error:
        raise DownloadError("The local quota ledger is busy or unavailable. No automatic retry; keep the ledger and try again later.") from None
    finally:
        if 'connection' in locals():
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Explicitly permit a download, subject to the persistent cache and quota guards.')
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env', help='Key file used only if a refresh needs credentials. Process environment takes priority.')
    parser.add_argument('--cache-dir', type=Path, default=Path(__file__).with_name('downloads'))
    args = parser.parse_args()
    try:
        result = download(args.cache_dir, args.refresh, args.env_file)
    except DownloadError as error:
        parser.exit(1, str(error) + '\n')
    print(f"Swedish feed: {result['status']}; provider requests this run: {result['requests_made']}.")
    print(f"Service envelope {result['service_start']} to {result['service_end']}; calendars may contain gaps.")
    print("Cached archive ready for explicit MOTIS preparation/import. No background refresh is scheduled.")


if __name__ == '__main__':
    main()
