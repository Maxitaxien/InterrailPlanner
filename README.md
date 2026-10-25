# Interrail Helper

Local-first rail trip planning from Oslo to southern Europe, based on [the implementation spec](interrail-helper-spec.md).

The interface is tailored to a honeymoon, with two-adult defaults and booking guidance on map connections and itinerary legs. See [rail API coverage and signup recommendations](docs/rail-api-assessment.md) before purchasing provider access. Operator links work now; live fares, seat availability and ticket issuing are not connected.

Optional additional rail research now has a prepared All Aboard adapter. See
[timetable source setup and exact credentials](docs/timetable-integrations.md)
for the source shortlist, Danish/ferry access status, repeatable feed preparation
and dated corridor checks. External research is separate from calendar-applied
MOTIS snapshots; no commercial provider is enabled by default.

Self-hosted MOTIS timetable searches are available as an optional Docker service. See [MOTIS setup and feed management](docs/motis.md) to import German long-distance schedules plus Norwegian exports from Vy Rail, SJ Nord and Go-Ahead Nordic. Train dialogs show prepared feed dates and city-coverage diagnostics. This does not yet replace the curated multi-day route generator or cover all route countries.

For a future honeymoon, plan unverified overnight travel without downloading any
feeds. Later, explicitly apply a researched departure to update the itinerary's
calendar. Saved timetable choices are not bookings and show when they need
rechecking. Existing installations need the new snapshot migration; see
[upgrade and future-journey planning](docs/motis.md#plan-future-overnight-travel-without-downloading-timetables).

City panels and stop cards now offer saved, on-demand activity ideas. Reopening
loads saved versions without running AI/search again. See [local AI setup](docs/local-ai.md)
for the new migration, Qwen3 14B guidance for a 16 GB GPU, and required private
SearXNG research for new city ideas. The same selected model plans a query, then
reads fresh search excerpts and answers. Every generation saves a new version;
opening saved results never searches. No model or timetable download is automatic.

The planner creates a trip, generates up to three deterministic routes (Italy by default) through mandatory stops, checks estimated pass-day limits, saves alternatives, and recalculates after edits. A large interactive map shows 146 cities/island stays, schematic connections, destination information and your route through transit cities. Click a city to add a stay, or an island to choose a final destination. Stops run left to right below the map. Branch-line trips may return through a hub. Retry uses current settings. Optional Ollama ranks curated recommendations; flights/hotels use search-link fallbacks. No AI or provider keys are required for core planning.

Compare up to six final stays using **Compare final destinations**. Route details
now separate station/port access, check-in, crossings and onward transfers, with
a local-time connection checker and return-airport access guidance. See
[endpoint comparison and connection planning](docs/endpoint-comparison.md).
No new keys or database migration are needed for these features.

The latest additions include Brindisi, Ancona, Salerno and Piombino as Italian
rail/ferry gateways, plus Elba, Paxos, Ithaca and Meganisi as final stays. Rebuild
the backend and rerun the seed import to load them; see [gateway and island sources](docs/data-sources.md#italian-ferry-gateways-and-western-greek-islands).

## Run locally

The coastal expansion adds 14 final stays in Italy and Greece, with Italian
rail/ferry access and Greek Ionian routes through Igoumenitsa or Patras. See
[coastal endpoints and access notes](docs/data-sources.md#coastal-expansion-17-october-2026).
Rebuild the backend and rerun the seed import below; no migration is needed.


The latest UI keeps stop cards compact and opens train/ferry research in a
keyboard-accessible modal. Each rail leg offers intermediate-stop ideas with
travel splits, suggested/allocated nights and a preview of pass/lock constraints.
Cards can remove stays, including a confirmed removal from the must-see list.
The catalog now has 146 places, including 25 island endpoints in Greece, Italy,
Croatia and Corsica. Rebuild the backend and rerun the seed import below to load
the new destinations. No schema migration or additional API key is needed.

There is no daily rail cap: long legs show estimated times, warnings and one-click
intermediate-stay suggestions. Athens can end via a labelled Bari–Patras ferry
plus onward ground transfer, with separate booking links and unknown pass coverage.
Estimated transit nights are included in the calendar, not destination stays.
Other unmodeled gaps still need data; arbitrary ferry/flight routes are not invented.

Follow [your setup checklist](docs/user-checklist.md) for `.env`, Docker, database initialization, GPU verification and first-trip acceptance. The application never runs migrations implicitly on startup.

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

For frontend hot reload in Docker, use the development override:

```sh
docker compose -f compose.yaml -f compose.dev.yaml up
```

It bind-mounts `frontend/` and runs Next in development mode. Keep using `docker compose up -d --build` for the production-style frontend image.

After pulling backend or city-network changes, rebuild the backend and refresh the seed data:

If you enabled self-hosted MOTIS, keep `-f compose.motis.yaml` in these Compose
commands as well, so the backend retains its MOTIS connection and source mount.
The complete MOTIS file set is shown in [MOTIS setup](docs/motis.md).

```sh
docker compose -f compose.yaml -f compose.dev.yaml up -d --build frontend backend
docker compose exec backend python -m app.scripts.seed_data
```

The seed import updates the city/connection catalog without deleting saved trips. Existing trips retain their saved route until edited or recalculated. Frontend edits continue to hot-reload after this setup; backend changes need a rebuild.

## Development checks

Python 3.12 is used in the container; application tests also run on Python 3.11.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
cd backend
../.venv/bin/pytest -q
```

```sh
cd frontend
npm ci
npm run build
npm run typecheck
npm test
```

For backend development set `DATABASE_URL` yourself, run `alembic upgrade head`, seed, then `uvicorn app.main:app --reload`. For the frontend run `npm run dev`; the server-side proxy defaults to `http://127.0.0.1:8000`. Provider secrets never enter browser requests.

## State of implementation

See [progress and next steps](docs/implementation-status.md), [architecture](docs/architecture.md), [API usage](docs/api.md), and [data sources](docs/data-sources.md). This is an early local planning build. Rail durations and connections are explicitly illustrative, flights and airport transfers are separate, and pass acceptance always requires verification.
