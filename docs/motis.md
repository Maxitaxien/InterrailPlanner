# Self-hosted MOTIS

The app now has a read-only timetable adapter for MOTIS **v2.11.3**, using
`GET /api/v6/plan`. Docker builds download the pinned official release and verify
its SHA-256 for amd64/arm64. No hosted Transitous requests or account are involved.

## First start

From the repository root, with the existing `.env` and initialized database:

```sh
python3 motis/prepare.py
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml build motis backend
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml run --rm motis-import
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml up -d --build
```

Omit `-f compose.dev.yaml` for the production-style frontend. Keep the same compose
file set on subsequent commands. If your database still has an older city/rail
catalog, explicitly refresh it (this preserves saved trips):

```sh
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml exec backend python -m app.scripts.seed_data
```

Preparation requires Python 3.10+ and the standard library only. `motis/work/`
contains downloaded feeds, provenance, generated config and imported data, and is
gitignored. Imports and feed updates are explicit; ordinary app startup does not
download data. The backend reads prepared source metadata from a read-only mount.
MOTIS is exposed only on `127.0.0.1:8080`; container-to-container requests use
`http://motis:8080`. Core planning still works when MOTIS is stopped/unconfigured.

Open any train leg, select its research date, and press **Search self-hosted
timetables**. The time is local to the origin city, not your browser timezone.
Searches are on demand, not triggered on every map click or form change.
Opening the departures panel reads local coverage metadata only; it does not
query MOTIS or a publisher until you press Search. Prepared calendar and nearby
stop checks are advisory and never disable a search of the running server.

## Plan future overnight travel without downloading timetables

Open **Plan & book this train leg → Departures → Plan now, verify later**.
**Plan overnight travel · unverified** saves an intention on that outgoing leg.
It budgets at least one night in transit (more for already multi-day corridors),
redistributes flexible accommodation nights within the trip duration, and retains
explicit zero-night visits. It neither proves that a sleeper exists nor assumes
the Interrail night-train pass-day saving. Clear the plan to use corridor estimates.
This works with flexible dates, does not search any provider, and does not need
the Swedish archive. Locked stays cannot be silently moved.

When dated timetables are published, explicitly search your self-hosted MOTIS.
The backend validates and stores returned rail/walking journeys as immutable
research snapshots, then returns opaque selection IDs. **Use this departure in
itinerary** applies one of those server-owned snapshots; arbitrary client-supplied
train times are not accepted. Exact trip dates are required. Actual local-date
arrivals and rail-boarding dates update the calendar/pass-day estimates. Selected
departure dates pin allocation of preceding nights, so preference/stay edits
either preserve that departure or explain the conflict. Clearing the selection
returns to illustrative estimates.

The [official Interrail night-train guidance](https://www.interrail.com/en/support/interested-in-interrailing/what-is-a-travel-day)
distinguishes a through overnight train from boarding another train after midnight.
We estimate pass days from local rail-boarding dates and separately check overall
validity through the last rail arrival. Through-service continuations are counted
conservatively until their identity is established. No reservation, pass
entitlement or sleeper accommodation is confirmed. Zero-night connections between
two saved journeys cannot have an outgoing departure before the incoming arrival;
minimum connection margins and estimated connecting legs still need checking.

New snapshots are selectable for 24 hours. Saved selections stay in your itinerary
after that and show **recheck needed**; opening/reopening does not refresh them.
Removing/splitting their city pair clears the plan with a warning rather than
applying it to a different leg. Snapshot station journeys can differ from the
schematic map corridor, which remains illustrative. There is no background
download, reservation request, live repricing or automatic timetable refresh.

### Upgrade an existing database

The new snapshot table requires an explicit migration after rebuilding the backend:

```sh
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml build backend
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml run --rm backend alembic upgrade head
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml up -d
```

Back up your PostgreSQL data before applying migrations. No feed download or
MOTIS re-import is required for the unverified planning feature. Real dated
searches need imported data covering those dates, as before.

## Included data: deliberately limited

The reviewed starter manifest is [motis/feeds.json](../motis/feeds.json):
[GTFS.de German long-distance rail](https://www.gtfs.de/en/feeds/de_fv/), based on
DELFI data, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Downloaded archives are not modified. Credits, source/license links, SHA-256,
download timestamp, stop/trip counts and the calendar envelope are recorded.
The UI displays credits and prepared source details with search responses.

The free feed covers approximately **30 days**, not the full honeymoon planning
horizon. Our first downloaded snapshot had 5,538 trips and service dates
2026-10-10 through 2026-11-09. These numbers are not a future guarantee. Hamburg
to Munich on 2026-10-20 returned real scheduled train options in a local binary
smoke test. Docker itself could not be run in the development workspace.

The default manifest now also includes three official [Entur timetable
exports](https://developer.entur.no/open-data/timetable): Vy Rail (`novy`),
SJ Nord (`nosj`) and Go-Ahead Nordic (`nogo`). They require no account. Data
originates from Entur under [NLOD 2.0](https://data.norge.no/nlod/en/2.0);
archives remain unchanged, while this app calculates city summaries. See
[Entur's identification, attribution and fair-use terms](https://developer.entur.no/terms-of-service).
Preparation sends a stable application-identification header and reuses an
unchanged, SHA-256-checked archive within 24 hours, retaining its original download
timestamp. If that cache is damaged during the interval, restore it or wait;
the tool does not bypass the interval by fetching again.

The 16 October 2026 snapshots contained 6,353 Vy Rail trips (rail calendar
2026-10-15–2027-02-16), 359 SJ Nord trips (2026-10-14–2027-02-24) and 718
Go-Ahead trips (2026-10-16–2027-02-12). These are snapshot envelopes, not a promise
of daily service. Total compressed inputs for all four feeds were about 92 MiB;
the local timetable import occupied about 186 MiB. Resource use may change.

The pinned MOTIS binary successfully imported all four feeds in an isolated
temporary directory. Through the real backend adapter, searches for
**20 October 2026** returned three scheduled options each for Oslo–Gothenburg,
Oslo–Bergen, Oslo–Trondheim and Hamburg–Munich. This checks those dated searches,
not every route/date, seat inventory or Docker execution. Existing app data was
not re-imported in place for the smoke test.

These are **operator subsets**, not complete Norwegian, Swedish, Danish or
Italian national coverage. SJ Nord is not the same as all SJ Sweden services.
Some cross-border services can appear in the Norwegian or German exports; do not
infer full coverage. A calendar envelope is only earliest/latest service, not a
guarantee of daily operation or complete geography. Feed preparation is not proof
that the currently running server loaded that version; import and restart it.

For the German-only starter import, use `python3 motis/prepare.py --feed defv`.
That intentionally replaces the configured dataset list with just that feed.

## Add and maintain feeds

Use the [expansion setup guide](timetable-integrations.md) for the current source
shortlist, `coverage.py` readiness/preparation manager and dated corridor checker.
The manager retains previously prepared known expansions and refuses to discard
custom feeds; the lower-level manifest commands below remain available.


For optional French, Swiss, Austrian and Danish manifests, access requirements,
and the API shortlist for remaining gaps, see [timetable coverage](timetable-coverage.md).
These opt-in manifests do not change the running import or download Sweden.

Make an admin-owned JSON manifest using the same structure. Each entry needs a
unique lowercase alphanumeric `id` (no underscores), `name`, `source_url`,
`license_url`, `attribution`, `coverage`, and either an HTTPS `url` or a local
`path` relative to that manifest. For example, after acquiring an authorized GTFS
archive:

```json
{
  "feeds": [{
    "id": "myrail",
    "name": "Publisher and dataset name",
    "path": "downloads/authorized-feed.zip",
    "source_url": "https://publisher.example/dataset",
    "license_url": "https://publisher.example/licence",
    "attribution": "Required attribution from the publisher; describe modifications if any",
    "coverage": "Operators, geography and limitations verified by the administrator"
  }]
}
```

Keep **all** intended feeds in the manifest and select all of them (or repeat
`--feed`). Each preparation generates a complete replacement config, not an
append operation. Unselected old archives may remain on disk but are not loaded.
Do not commit credentials or signed download URLs; download authenticated feeds
separately and use a local path. The app offers no user-supplied URL fetching.

### Sweden: key setup and explicit cached downloads

Create a [Trafiklab account](https://developer.trafiklab.se/) and request access
to **GTFS Sverige 2**. The [official dataset page](https://www.trafiklab.se/api/gtfs-datasets/gtfs-sverige-2/)
documents key access, the current download endpoint and CC0 licence. Add this
variable to your root `.env` yourself (do not use a `NEXT_PUBLIC_` prefix):

```dotenv
TRAFIKLAB_GTFS_API_KEY=your-private-key
```

This is a **host-side downloader key**. It is not passed into the frontend,
backend, MOTIS config, prepared metadata or browser storage. The standalone
command reads this literal variable only when an explicitly permitted download
needs it; it does not execute shell expressions in `.env`. An already exported
process variable takes priority. For another key-file location use `--env-file
/absolute/path/to/private-config`. Never commit a key or key-bearing URL.

```sh
# No provider calls: reuse a validated archive, or explain how to download it.
python3 motis/download_sweden.py

# Explicitly permit one Swedish bulk-feed download if the cache needs refreshing.
python3 motis/download_sweden.py --refresh
```

The archive is saved at `motis/downloads/sweden.zip`, with a checksum/status file
and `trafiklab-requests.sqlite3` quota ledger in the same gitignored directory.
Keep that directory across restarts/rebuilds. Do not delete the ledger to retry:
it records local attempts, including errors and timeouts, before network I/O.
Downloads are never triggered by app startup, map clicks, route generation,
timetable searches, `prepare.py`, or cache age. A stale cache is still used until
you explicitly request refresh; service-calendar diagnostics remain important.

Quota safeguards: at most one successful refresh per 24 hours, at least 60 seconds
between attempts, and a local ceiling of 50 attempts in a rolling 30 days. The
ledger serializes concurrent downloader processes. No automatic retries, redirect
following or preliminary API probes are made. Successful fresh caches are reused
even with `--refresh`; missing credentials do not cause a request. Failed downloads
or GTFS validation keep the prior archive. Upstream errors and keyed URLs are not
printed. The ledger cannot see calls made outside this downloader or in another
checkout; account for those separately. This tool does not override provider limits.

One request downloads the bulk timetable feed. Once imported, any number of
journey searches query **your own MOTIS server**, not Trafiklab. Their results
are timetable research, not live seat or reservation availability. Do not
substitute historical public snapshots for the current feed.

The supplied local-file manifest can be merged without editing the default:

```sh
python3 motis/prepare.py --extra-manifest motis/feeds.sweden.example.json
```

This prepares **all five** feeds. Relative archive paths resolve against their
own manifest, not the shell's working directory. Duplicate feed IDs and missing
archives fail before replacing the prepared config. Swedish data has **not**
been downloaded/imported or verified here: an authorized current archive is
still needed. The local-file template and preparation step do not collect a key
or contact Trafiklab; only the explicit downloader refresh can do so. After
preparation, run the MOTIS import and restart commands below to load the archive.

```sh
python3 motis/prepare.py --manifest /absolute/path/to/your-feeds.json
```

The tool currently accepts **GTFS ZIPs** with root-level tables, up to 512 MiB
compressed / 2 GiB uncompressed. MOTIS supports NeTEx too, but this workflow does
not yet validate/stage it. Failed downloads or validation preserve the prior
prepared configuration. It checks table presence/calendar bounds, not every GTFS
relationship; MOTIS import is the next validation step. No ZIP is extracted.
Auditing additionally separates rail from bus/ferry route types, counts rail
trips and stops referenced by rail stop-times, and checks rail stops within
3 km of every catalog city. Stops merely listed in `stops.txt` do not establish
rail coverage. Rail calendar envelopes exclude bus-only services, but can still
contain service gaps and are not exact per-city/per-trip calendars. Older status
files without these fields are shown as unaudited until preparation is rerun.

For updates, stop the server before preparation/import and restart after success:

```sh
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml stop motis
python3 motis/prepare.py
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml run --rm motis-import
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml up -d motis
```

Back up the last working `motis/work/` before changes: imports update the same
data directory and are **not** a blue/green deployment. If import fails, fix the
inputs and re-import before starting; don't assume partially updated data is safe.
No background refresh is scheduled yet. Refresh according to each source's terms,
service validity, and publication schedule.

Next coverage priorities: Trafiklab's current Swedish export (authorized archive
needed), Danish national rail coverage, then Italian operators and the
Alpine transit countries. Review current publisher access/licences and audit each
cross-border leg; a country filename alone is not evidence of coverage.

## Deliberate boundaries

- Timetable-only config: no OSM, geocoding, tiles or real-time feeds are loaded.
- City-coordinate searches use a 3 km radius. Walking access/egress is a straight-
  line estimate, not a street-validated walk; outlying stations may be missed.
- Search allows rail plus walking transfers, not buses/ferries. Walking-only,
  cancelled and extrapolated-calendar journeys are not offered. Calendars are
  never extended beyond published dates by our config.
- Dates/times retain offsets and station timezones. DST gaps and overlaps require
  a different, unambiguous research time.
- Missing/expired data, unavailable MOTIS and an empty result are not presented
  as proof that the real journey is impossible.
- MOTIS reservation flags/defaults are not treated as Interrail rules. No pass
  entitlement, reservation fee, inventory or ticket purchase is implied.
- The curated graph still generates/edits the multi-day holiday. Searching does
  not change the itinerary. Explicitly applying a returned snapshot updates that
  leg's timing and calendar; other legs remain estimates. Full timetable-aware
  multi-day route generation and proven station-to-station interchange feasibility
  remain future work.

Official references: [setup configuration](https://github.com/motis-project/motis/blob/v2.11.3/docs/setup.md)
and [pinned API contract](https://github.com/motis-project/motis/blob/v2.11.3/openapi.yaml).
