# Interrail Helper — Technical Implementation Specification

**Version:** 1.0  
**Date:** 2026-10-16  
**Status:** Architecture finalized; implementation pending

## 1. Executive summary

Interrail Helper is a local-first web application for planning multi-city European railway trips starting in Oslo, usually ending in southern Europe before flying back to Bergen (BGO). It generates multiple routes, supports mandatory and optional stops, allocates days, offers an editable itinerary and interactive map, and recommends attractions and final relaxation destinations.

The route engine and scheduler are deterministic. A configurable local LLM provides personalization and explanations, not invented transport facts. External rail rules, flights, and accommodation data are requested on demand and cached with provenance and expiry.

### Confirmed decisions

1. User selects their existing Interrail pass.
2. Flexible dates for planning; exact dates required for live flight/hotel searches.
3. Optional overall budget and separate final-stay budget.
4. Curated railway graph with approximate times for MVP.
5. Automatic itinerary recalculation after committed edits.
6. Ollama default; optional cloud LLM fallback disabled by default.
7. All primary services in Docker Compose, including GPU-backed Ollama.
8. No user accounts initially; trips use UUIDs and separate edit tokens.
9. Live flight/hotel APIs where available; external booking search fallback.
10. Fully local first, prepared for eventual deployment.

## 2. Technology stack

| Layer | Technology | Responsibility |
|---|---|---|
| Frontend | Next.js, TypeScript | Trip UI and editor |
| UI | Tailwind CSS, shadcn/ui | Components and styling |
| State | TanStack Query, Zustand | Server state and editor state |
| Maps | MapLibre GL JS | Route visualization |
| Backend | Python 3.12+, FastAPI | API and business logic |
| Validation | Pydantic v2 | Typed request/response contracts |
| Persistence | PostgreSQL 17 | Trips, graph, caches |
| ORM/migrations | SQLAlchemy 2.x, Alembic | Database schema and access |
| Routing | NetworkX MultiDiGraph | Candidate path search |
| Local AI | Ollama, Qwen3 8B quantized | Recommendations and explanations |
| Deployment | Docker Compose | Local orchestration |
| Testing | pytest, Hypothesis, Vitest, Playwright | Unit through end-to-end |

Pin tested dependency versions in lockfiles and container images. Use a modular monolith, not microservices.

## 3. Architecture and service responsibilities

```text
Browser
  -> Next.js frontend (:3000)
      -> FastAPI backend (:8000)
          -> Trip service / itinerary editing
          -> Route engine / constraints / scoring
          -> Calendar scheduler / pass-day estimates
          -> AI orchestration / validated recommendations
          -> Rail restrictions provider
          -> Flight and accommodation provider adapters
          -> PostgreSQL (internal)
          -> Ollama (internal, NVIDIA GPU)
          -> External APIs (only on demand)
```

The frontend must not hold provider credentials. Backend modules communicate through interfaces and typed data contracts. The route engine works without internet or LLM access.

## 4. Functional requirements

### 4.1 Trip creation

Inputs: fixed Oslo start; total calendar days (default 21); optional exact start date; required and preferred stops; desired endpoint/region; interests; pace; max daily travel hours; final-stay nights (default 4); optional overall and final-stay budgets; currency (default NOK); existing Interrail pass details.

Pass fields: Global vs One Country; continuous vs flexi; number of travel days; days already used; validity dates when known; class if relevant. Pass checking must distinguish `valid_estimate`, `needs_verification`, `incompatible`, and `unknown`. Estimated graph compatibility is not definitive pass validity.

### 4.2 Itinerary alternatives

Generate up to three meaningfully different routes containing all required stops, ordered rail legs, estimated durations, allocated nights, travel-day estimates, confidence warnings, endpoint information, and route scores.

### 4.3 Interactive editing

Add/remove/reorder/lock stops, edit nights, and switch endpoint. On committed edit, recalculate automatically, preserving required/locked constraints. Debounce rapid UI interactions and avoid rerunning AI on every edit. Reject infeasible changes atomically with actionable errors.

### 4.4 Southern endpoint

Score southern Italy, coastal Croatia, southern France, southern Spain, Greece and other feasible regions by rail access, airport transfer, return journey to Bergen, relaxation suitability, user interests and accommodation budget. Ferry-dependent endpoints require explicit non-rail transport modeling or a warning.

### 4.5 Live travel discovery

Exact dates and party/guest counts are required before live hotel/flight searches. Show provider, currency, timestamps, terms, and verified prices only when returned by an authorized API. Otherwise show a prefilled external booking-search link without pretending to know prices.

## 5. Railway graph and data

Seed 40–60 curated destinations and connecting corridors in version-controlled JSON/CSV; import idempotently to PostgreSQL. Use `networkx.MultiDiGraph` to represent directed connections, including alternative services.

Example (illustrative, not verified timetable):

```json
{
  "origin": "berlin",
  "destination": "prague",
  "estimated_minutes": 270,
  "typical_transfers": 0,
  "service_type": "intercity",
  "estimate_quality": "curated",
  "source": "manual",
  "last_reviewed_at": null
}
```

Store provenance, typical transfers, service type, night-train flag, country transitions, and possible reservation warnings. Schematic map lines must not be represented as verified railway geometry.

## 6. Route generation algorithm

1. Validate duration, pass, required stops, and user preferences.
2. Select candidate southern endpoints.
3. Build candidate paths through required stops using shortest-path search, bounded permutations and beam search.
4. Insert optional stops subject to detour and travel-time limits.
5. Allocate calendar days and final-stay nights.
6. Evaluate known pass constraints; mark unknown restrictions for verification.
7. Reject hard-constraint violations.
8. Score candidates and select three diverse alternatives.

```python
def generate_routes(request, graph, destinations):
    validate_request(request)
    endpoints = select_candidate_endpoints(destinations, request)
    candidates = []
    for endpoint in endpoints:
        paths = generate_paths_with_required_stops(
            graph, request.start_city_id, request.required_stop_ids,
            endpoint.id, max_candidates=30,
        )
        for path in paths:
            for variant in insert_optional_stops(path, graph, request, max_variants=5):
                schedule = allocate_calendar_days(variant, request)
                if not schedule.feasible:
                    continue
                pass_result = evaluate_pass_constraints(schedule, request.pass_details)
                if pass_result.known_incompatible:
                    continue
                candidates.append(score_itinerary(schedule, request, pass_result))
    return select_diverse_top_k(candidates, k=3)
```

Suggested normalized score:

`S = 0.30*interest_match + 0.25*travel_efficiency + 0.20*pace + 0.15*diversity + 0.10*endpoint_quality`

All components in [0,1]; weights configurable. Required stops and total days are hard constraints, not score penalties. Penalize nearly identical alternatives in final selection.

## 7. Scheduling algorithm

Model the trip as calendar dates (or day offsets for flexible dates). Stops use half-open `[arrival_date, departure_date)` intervals; nights equal departure minus arrival. Rail legs occupy time *within* calendar days rather than consuming an additional day automatically.

Track arrival/departure, nights, estimated train minutes, usable sightseeing time, pass travel-day estimates, final-stay allocation, and return-flight date. Preferred intermediate stays: small city 1 night; standard city 2; major city 2–3; final relaxation 3–6. User-locked stays override preferences.

On overrun, remove optional stops or shorten unlocked stays; if still impossible, return structured constraint errors. Midnight crossings, night trains, uncertain pass rules, missing graph edges and overly long travel days require explicit warnings. Do not assert precise schedules without timetable data.

## 8. PostgreSQL schema

All user-generated resources use UUID primary keys. Money uses `NUMERIC` and ISO 4217 currency codes; event timestamps are timezone-aware. Add foreign keys, deletion rules, nonnegative constraints, and indexes.

| Table | Main columns |
|---|---|
| `trips` | id, start_city_id, total_days, start_date, date_mode, preferences JSONB, total_budget, final_stay_budget, currency, revision, created_at, updated_at |
| `trip_passes` | trip_id, pass_type, validity_type, travel_days_total, travel_days_used, valid_from, valid_until, travel_class |
| `itineraries` | id, trip_id, name, score, status, is_selected, revision, created_at |
| `trip_stops` | id, itinerary_id, destination_id, position, arrival_day, departure_day, arrival_date, departure_date, nights, is_required, is_locked |
| `trip_legs` | id, itinerary_id, from_stop_id, to_stop_id, mode, estimated_minutes, departure_day, travel_days_estimate, verification_status |
| `destinations` | id, name, country_code, latitude, longitude, category, interest_tags, suggested_nights |
| `rail_connections` | id, origin_id, destination_id, estimated_minutes, transfers, source, reviewed_at |
| `attractions` | id, destination_id, name, category, visit_minutes, description, source |
| `travel_rules_cache` | id, source_url, lookup_key, content_json, retrieved_at, expires_at, source_version |
| `flight_offer_cache` | id, search_hash, provider, offers_json, currency, retrieved_at, expires_at |
| `accommodation_offer_cache` | id, search_hash, provider, offers_json, currency, retrieved_at, expires_at |
| `ai_cache` | id, input_hash, model_name, prompt_version, output_json, created_at |
| `external_requests` | id, provider, request_type, status, requested_at, error_code |

Unique `(itinerary_id, position)` for stops. Index trip foreign keys, destination IDs, search hashes and cache expiries. Use optimistic revision checks for edits. Avoid logging credentials or sensitive payloads.

Without accounts, create a separate cryptographically random edit token for each trip; store its hash. A UUID is not authentication. Require edit token for mutations and implement proper auth before broad public deployment.

## 9. REST API contracts

Prefix all endpoints with `/api/v1`; FastAPI generates OpenAPI docs.

| Method | Endpoint | Function |
|---|---|---|
| POST | `/trips` | Create trip and return UUID/edit token |
| GET | `/trips/{id}` | Retrieve trip |
| PATCH | `/trips/{id}` | Edit preferences |
| DELETE | `/trips/{id}` | Delete trip |
| POST | `/trips/{id}/generate` | Generate alternatives |
| GET | `/trips/{id}/itineraries` | List alternatives |
| PATCH | `/itineraries/{id}` | Apply edit and recalculate |
| POST | `/itineraries/{id}/select` | Select alternative |
| GET | `/destinations` | Search destinations |
| GET | `/destinations/{id}` | Destination detail |
| POST | `/travel/rail-rules` | Fetch/cache restrictions |
| POST | `/travel/flights/search` | Search flights |
| POST | `/travel/hotels/search` | Search accommodation |
| GET | `/ai/models` | Available models |
| POST | `/ai/test` | Test AI connection |
| GET | `/health` | Service health |

Illustrative trip request:

```json
{
  "total_days": 21,
  "start_date": null,
  "date_mode": "flexible",
  "required_stops": ["prague", "venice"],
  "preferences": {
    "interests": ["culture", "food", "beaches"],
    "pace": "balanced",
    "final_stay_nights": 4
  },
  "budget": {"total": 30000, "final_stay": 10000, "currency": "NOK"},
  "pass": {"type": "global", "validity_type": "flexi", "travel_days_total": 7, "travel_days_used": 0}
}
```

Edits include `expected_revision` and operation (`set_nights`, `add_stop`, `remove_stop`, `reorder_stop`, `lock_stop`, `change_endpoint`). Return recalculated itinerary plus warnings. `409 Conflict` for stale revision; `422 Unprocessable Entity` for impossible constraints. Standard error shape:

```json
{
  "error": {
    "code": "TRIP_DURATION_EXCEEDED",
    "message": "The requested stays exceed the trip duration.",
    "details": {"required_days": 24, "available_days": 21}
  }
}
```

Other codes: `PASS_LIMIT_EXCEEDED`, `ROUTE_NOT_FOUND`, `DATES_REQUIRED`, `PROVIDER_UNAVAILABLE`, `STALE_ITINERARY_REVISION`.

## 10. Local AI specification

Default: Ollama with quantized `qwen3:8b` on RTX 4070 Ti SUPER (16 GB VRAM); temperature 0.3; context window initially 8192; timeout 90s; JSON Schema output validated by Pydantic. Allow model and provider changes in settings. Optional cloud provider must be explicitly enabled and have cost controls.

```python
from typing import Protocol, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

class LLMProvider(Protocol):
    async def generate_structured(
        self, system_prompt: str, user_prompt: str, response_model: type[T]
    ) -> T: ...
```

AI responsibilities: rank curated destinations by interests, choose/explain attractions, compare route alternatives, summarize schedules. AI cannot invent rail connections, ticket rules, prices, availability, or override constraints.

Fallback: Ollama -> validate JSON -> one local retry -> optional cloud provider if enabled -> deterministic database recommendations. Cache by model, prompt version, relevant preferences, destination context and schema version. Never require AI for core route generation.

## 11. External providers and caching

Implement `FlightProvider`, `AccommodationProvider`, and `RailRulesProvider` interfaces, normalizing third-party responses to internal Pydantic models.

Flights: search endpoint-region airports to BGO, display price/currency, stops, duration, baggage if available, booking URL, source and retrieval timestamp. Reprice when provider supports it. Hotels: check-in/out, guests, budget, property type, taxes/fees, cancellation conditions, booking URL, timestamp. Airbnb API access must not be assumed.

Rail restrictions: fetch only when requested; check cache first; store source URL, lookup parameters, content, retrieval time and expiry. Mark unresolved rules `unknown` or `needs_verification` rather than asserting facts.

Initial cache guidance: destination information ~30 days; AI until inputs/prompt change; rail rules ~24 hours; flight/hotel offers ~10–15 minutes. Provider terms and source-specific freshness rules override defaults. Booking-site fallback shows links, not fabricated prices.

## 12. Docker Compose

Prerequisites: Docker Compose, NVIDIA driver, NVIDIA Container Toolkit or compatible Windows WSL2 GPU setup. Ollama must remain internal; do not expose PostgreSQL or inference ports publicly.

```yaml
name: interrail-helper

services:
  frontend:
    build:
      context: ./frontend
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      API_INTERNAL_URL: http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped

  backend:
    build:
      context: ./backend
    ports:
      - "127.0.0.1:8000:8000"
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+asyncpg://interrail:${POSTGRES_PASSWORD}@db:5432/interrail
      OLLAMA_BASE_URL: http://ollama:11434
      LLM_PROVIDER: ollama
      LLM_MODEL: qwen3:8b
    depends_on:
      db:
        condition: service_healthy
      ollama:
        condition: service_started
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"]
      interval: 15s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  db:
    image: postgres:17
    environment:
      POSTGRES_DB: interrail
      POSTGRES_USER: interrail
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U interrail -d interrail"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    gpus: all
    restart: unless-stopped

volumes:
  postgres_data:
  ollama_data:
```

This is a baseline, not a complete runnable repository. The backend Dockerfile must include the health-check dependencies. Pin image versions in production; run migrations as an explicit initialization step.

`.env.example`:

```dotenv
POSTGRES_PASSWORD=replace-with-strong-local-password
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:8b
LLM_FALLBACK_ENABLED=false
LLM_TIMEOUT_SECONDS=90
DEFAULT_CURRENCY=NOK
DEFAULT_START_CITY=oslo
DEFAULT_RETURN_AIRPORT=BGO
FLIGHT_PROVIDER=none
HOTEL_PROVIDER=none
RAIL_RULES_PROVIDER=none
OPENAI_API_KEY=
FLIGHT_API_KEY=
HOTEL_API_KEY=
```

Startup after creating Dockerfiles and application code:

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama list
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed_data
```

Frontend: `http://localhost:3000`; FastAPI docs: `http://localhost:8000/docs`. Use a frontend proxy for browser API requests.

## 13. Repository structure

```text
interrail-helper/
├── frontend/
│   ├── app/{page.tsx,trips/,settings/}
│   ├── components/{trip/,map/,itinerary/,destinations/,travel/}
│   ├── hooks/
│   ├── lib/
│   ├── types/
│   ├── tests/
│   ├── Dockerfile
│   └── package.json
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/{config.py,database.py,security.py}
│   │   ├── api/v1/{trips.py,itineraries.py,destinations.py,travel.py,ai.py}
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/route_engine/{graph.py,generator.py,scoring.py,constraints.py}
│   │   ├── services/{scheduler.py,trip_service.py,recommendations.py}
│   │   ├── ai/{base.py,ollama.py,cloud.py,prompts/}
│   │   ├── providers/{rail/,flights/,hotels/}
│   │   └── scripts/seed_data.py
│   ├── data/{destinations.json,rail_connections.json}
│   ├── migrations/
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── docs/{architecture.md,api.md,data-sources.md,deployment.md}
├── compose.yaml
├── compose.prod.yaml
├── .env.example
├── .gitignore
└── README.md
```

## 14. Testing strategy

- **pytest unit tests:** graph traversal, scoring, mandatory stops, scheduling, pass constraints.
- **Hypothesis property tests:** calendar-day invariants, stable required-stop ordering, no negative nights.
- **HTTPX API tests:** validation, conflict responses, edit operations, errors.
- **PostgreSQL integration tests:** migrations, constraints, transactions and persistence.
- **Vitest frontend tests:** trip form, editor state and formatting.
- **Playwright E2E tests:** create, generate, edit, save and reopen trip.
- **AI contract tests:** mocked structured responses, invalid JSON retry, no-cloud fallback.
- **Provider tests:** timeout, cache expiry, unavailable APIs and stale-offer labeling.
- **Docker smoke tests:** startup, health checks, GPU access and volume persistence.

Critical invariants: every route includes required stops; calendar duration is respected; edits preserve locked constraints; known pass violations are rejected or flagged; missing rail data never becomes an invented journey; offline AI does not break routing; disabled cloud fallback makes zero cloud calls; expired offers are not marked live; stale edits return conflict.

## 15. Implementation roadmap

| Phase | Estimate | Deliverable |
|---|---|---|
| 1. Infrastructure and database | Week 1 | All Compose services start; migrations work; Ollama uses GPU |
| 2. Railway graph and route generation | Weeks 2–3 | API returns multiple routes with required stops |
| 3. Scheduling and editing | Weeks 4–5 | Constraint-safe automatic recalculation and persistence |
| 4. Interactive frontend | Weeks 6–7 | Trip wizard, map, timeline, edit controls |
| 5. Local AI | Week 8 | Configurable Ollama recommendations, caching and fallback |
| 6. Travel integrations | Weeks 9–10+ | On-demand rail rules and live/fallback booking discovery |
| 7. Testing and release | Week 11 | Stable local MVP and deployment docs |

Estimates assume solo part-time development and depend on data/API access.

## 16. Deployment readiness

Local MVP: frontend, backend, PostgreSQL and Ollama in Compose. Future: frontend/backend on VPS or container hosting; managed or VPS PostgreSQL; GPU inference host; HTTPS reverse proxy; secrets management; proper authentication and sharing permissions; off-machine backups; secure private access to inference. Do not assume a home desktop is always online.

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Inaccurate rail estimates | Source/confidence labels; verification links |
| Pass-rule complexity | Known/unknown distinction; on-demand authoritative retrieval |
| Restricted flight/hotel APIs | Provider interfaces and booking-site fallback |
| LLM hallucinations | Curated context, structured output, deterministic validation |
| Slow inference | Cache results; avoid per-edit regeneration |
| Impossible trips | Hard constraints and actionable errors |
| Data loss | Volumes, backup/restore tests, migrations |
| Unauthorized edits | High-entropy edit tokens; auth before public launch |

## 18. MVP acceptance criteria

- [ ] Create trip from Oslo with duration, stops, preferences, existing pass and optional budgets.
- [ ] Generate up to three distinct, geographically sensible alternatives.
- [ ] Enforce hard constraints or explain infeasibility.
- [ ] Show map, timeline, estimated legs and recommended stays.
- [ ] Edit stops and nights with automatic recalculation.
- [ ] Persist and reopen trips in PostgreSQL.
- [ ] Generate personalized recommendations through configurable Ollama.
- [ ] Continue core planning without AI or internet access.
- [ ] Fetch requested rail-rule information with source and verification status.
- [ ] Show verified live flight/hotel offers where possible, fallback links otherwise.
- [ ] Run all primary services in Docker Compose.
- [ ] Pass routing, scheduling, editing and persistence tests.

## 19. Sprint 1: first vertical slice

1. Create repository, frontend/backend Dockerfiles and Compose configuration.
2. Start PostgreSQL, FastAPI, Next.js and Ollama.
3. Verify NVIDIA GPU inference with Qwen3 8B.
4. Define SQLAlchemy models and first Alembic migration.
5. Seed 10–15 representative European cities and rail connections.
6. Implement a route-generation endpoint with mandatory stops.
7. Display a generated route in a simple frontend page.

**Sprint acceptance:** Create a 21-day trip from Oslo with Prague and Venice required; receive and save an estimated route toward southern Italy.

---

**Core ownership rule:** The route engine owns connectivity and feasibility; the scheduler owns time allocation; Ollama owns personalization; external providers own live travel information.
