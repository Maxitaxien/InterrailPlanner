# Your setup, verification and credentials checklist

No `.env` file, API keys, host permissions, Docker installation or GPU settings were created or changed. This file collects everything that needs your environment or decisions.

## Prerequisites and local secrets

- [ ] Install Docker Engine/Desktop and Compose with `gpus: all` support.
- [ ] Verify NVIDIA driver and Container Toolkit, or Windows WSL2 GPU passthrough.
- [ ] Copy `.env.example` to `.env` yourself and set a strong PostgreSQL password. Use URL-safe characters because Compose inserts it into DATABASE_URL.
- [ ] Keep services on loopback. PostgreSQL and Ollama have no published ports. Public use needs authentication and HTTPS first.

## Start the application

After creating your `.env`, run from the repository root:

```sh
docker compose up -d db ollama
docker compose build backend frontend
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python -m app.scripts.seed_data
docker compose up -d backend frontend
docker compose exec ollama ollama pull qwen3:14b
docker compose exec ollama ollama list
docker compose ps
```

- [ ] Health: http://localhost:8000/api/v1/health reports database `ok`.
- [ ] OpenAPI: http://localhost:8000/docs loads.
- [ ] Frontend: http://localhost:3000 loads destinations.
- [ ] Default 21-day trip, Prague/Venice required and seven-day flexi pass: up to three saved southern Italy alternatives, 20 nights, final four nights and return on day 21.
- [ ] Reload: trip, form preferences, route edits and selected alternative reopen.
- [ ] Edit nights, add/remove/reorder a stop, lock/unlock and switch endpoint. Infeasible edits leave the saved result unchanged.
- [ ] Save changed preferences with the existing-trip button; stale edits show a conflict requiring reload.
- [ ] Restart containers and confirm persistence. `down -v` removes stored volumes.
- [ ] Validate desktop/mobile layout, keyboard controls and MapLibre pan/zoom. The schematic has no external tiles; it is not verified railway geometry.

## Local AI and GPU

- [ ] Open AI settings and test structured local inference with the pulled model.
- [ ] Confirm inference uses the GPU using `nvidia-smi` on your host. Model listing alone does not establish GPU use.
- [ ] Check latency and VRAM consumption with Qwen3 8B and the 8192-token context.
- [ ] Find ideas on a route; check local ranking, cache reuse and relevant curated results.
- [ ] Stop Ollama and confirm route planning still works and recommendations fall back to curated ranking.
- [ ] Cloud inference is unimplemented and disabled. Leave external AI keys empty.

## Provider choices and API keys — later

Current planning, schematic map, local AI and booking links need no external API keys.

- [ ] Choose an authorized flight API and review access, terms, caching and repricing support before supplying a backend key.
- [ ] Choose an authorized accommodation API and review availability, taxes, fees and cancellation fields. Airbnb access is not assumed.
- [ ] Decide whether official rail reference pages suffice or an authorized structured rail-rules source is needed.
- [ ] Keep all future keys in your own backend secret configuration. Never add secrets to Git or frontend code.
- [ ] Exact flight dates/adult counts and hotel dates/guest/room counts must be confirmed on external search sites. Search links do not imply prices or availability.
- [ ] Try rail-reference retrieval; sources may block automated access. Failure returns `unknown` and an official source link.

## Data review

- [ ] Review coordinates, airports and all 128 directed illustrative corridors before relying on them. These are engineering fixtures, not current timetables or guaranteed direct services.
- [ ] Verify services, transfer times, reservations, pass acceptance, works and midnight crossings for actual travel dates.
- [ ] Verify airport transfers and Bergen flight availability separately.
- [ ] For Greece, verify the modeled Bari–Patras ferry and onward travel to Athens: dates, connections, cabin, fares and pass benefits. Displayed allowances are not a timetable.
- [ ] Budget fields are saved preferences; no cost feasibility is claimed.

## Test and release verification

- [ ] Run PostgreSQL tests against a disposable database. Set TEST_DATABASE_URL yourself to a `postgresql+psycopg://...` URL and run `pytest -q tests/test_postgres.py` from backend. Tests create/drop only their randomly named schema, and require schema creation rights in that test database.
- [ ] Run browser scenarios from frontend after `npm ci` and `npm run build`: `npm run test:e2e`. They use isolated temporary SQLite data; TEST_PYTHON can point to your Python environment. Default is the root `.venv/bin/python`.
- [ ] Install Playwright's Chromium/runtime dependencies in your environment if needed. In this workspace Chromium download succeeded but launch failed because `libglib-2.0.so.0` is missing. System libraries and permissions are left to you.
- [ ] Exercise backup/restore in [deployment.md](deployment.md).
- [ ] Actual Docker image startup, PostgreSQL runtime, browser rendering and GPU inference have not been verified here. Registry manifests were checked and pinned; that is not a runtime test.

See [implementation-status.md](implementation-status.md) for completed work and remaining implementation limits.


## Additional timetable coverage

- [ ] Follow [source setup and credentials](timetable-integrations.md). Danish and ferry enquiries are already sent; request All Aboard rail journey access if useful for Italian/cross-border gaps.
- [ ] Run `python3 motis/coverage.py status`; obtain authorized missing national archives. This local check does not contact providers.
- [ ] Explicitly prepare selected sources, import and restart MOTIS, then run the dated corridor checker for published travel dates. Existing known expansions are retained by `coverage.py prepare`.
- [ ] If All Aboard access is approved, configure its private backend key and test environment, verify operator coverage, then enable live research when approved. External results do not update the calendar.
- [ ] Obtain FerryhAPI's technical contract alongside credentials; the live ferry adapter remains pending those details.


## Compare final stays and check connections

- [ ] Rebuild frontend and backend using your normal Compose overrides; no migration is needed for comparison/connection planning.
- [ ] Open **Compare final destinations**, select a common Italian origin and compare island/coastal access before choosing.
- [ ] Expand the route to check station-to-port access, ticket check-in requirements, ferry/ground legs and return-airport access.
- [ ] Enter researched local dates/times in the connection checker. Add onward airport/station transfers and the next operator's boarding requirements; plan an extra night when margins do not fit.
- [ ] Treat all comparison and access times as estimates until real services are verified. See [connection planning](endpoint-comparison.md).
