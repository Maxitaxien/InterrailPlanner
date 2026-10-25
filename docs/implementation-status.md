# More rail/ferry gateways and Ionian final stays — 17 October 2026

Added Brindisi, Ancona, Salerno and Piombino with illustrative rail approaches,
port access and reviewed ferry-route references. Added Elba, Paxos, Ithaca and
Meganisi final stays, including explicit outlying ports/local transfers,
seasonality and return-airport ferry access. Totals: 146 destinations, 25 island
endpoints, 466 directed rail estimates and 36 ferry/ground research corridors.
All additions use existing comparison, connection checks, map and seed machinery;
no credentials, schema migration or automatic import is required. Existing saved
routes are retained until explicitly edited/recalculated. Validation passed 227
Python tests (two PostgreSQL tests skipped), 12 frontend tests and seven focused
browser scenarios covering comparison, the expanded map and saved island trips.
See [sources and setup](data-sources.md#italian-ferry-gateways-and-western-greek-islands).

# Endpoint comparison and connection planning — 17 October 2026

Implemented an explicit comparison dialog for up to six final stays from a common
Italian origin, with route breakdowns, ferry/ground counts, transit-night lower
bounds, seasonality, return-airport access and guarded endpoint application.
Ferry/ground corridors now expose station/port access, check-in, disembarkation,
road legs and margins without changing or double-counting existing budgets.
A local-time checker handles Italy/Greece offsets, midnight, DST rejection,
early/late arrival, short margins, ticket/access overrides and onward-airport
transfer time. It stores no research or calendar changes. Airport candidates
need an explicit user choice before flight searches. Reopening old routes adds
derived details without database writes or revision changes. No migration,
provider key, feed download or live transport claim is introduced.
Validation: 223 Python tests passed with two PostgreSQL tests skipped; the
28-test focused suite covers the latest connection cases. Twelve frontend unit
tests, all 22 browser scenarios and production build/TypeScript checks passed.
The responsive comparison was also rechecked after its mobile card layout.
See [usage, API contracts and assumptions](endpoint-comparison.md).

# Coastal final stays — 17 October 2026

Added 14 Italian and Greek endpoints with individual highlights and research
access notes: eight in western Greece and six in Italy. The catalog now has
138 destinations, 21 island endpoint options, 454 directed rail estimates and
27 ferry/ground endpoint research corridors. Greek additions use Bari ferries
through Igoumenitsa or Patras, with explicit onward road/island connections.
Cefalù preserves separate Palermo rail-pass accounting; Lefkada's bridge approach
is labelled ground travel. New coastal map actions choose a final destination.
EAV links and pass warnings cover Sorrento. Seeds merge idempotently; no migration.
All 14 new endpoints passed sample route generation; focused seed/operator and
transfer-label checks passed, along with the frontend tests and production build.
The full Python run passed 195 tests with two PostgreSQL skips; the additional
Sorrento operator check passed in its focused suite.
See [sources and access notes](data-sources.md#coastal-expansion-17-october-2026).

# Timetable machinery increment — 17 October 2026

Added an opt-in All Aboard GraphQL adapter for explicit nearby-location lookup
and dated end-to-end journey research, with fixed test/live hosts, secret-valued
server configuration, no redirects/retries, bounded responses and redacted errors.
Train dialogs expose explicit provider location choice and search. Sandbox
results are labelled; provider DateTime values remain station-local research.
No offers, payments, persistent external snapshots or calendar application were
added. Technical contract reviewed against the provider's public documentation;
real account access and exact operator coverage remain unverified.

Added local source readiness and repeatable preparation via `motis/coverage.py`.
Known prior expansions are retained; custom sources and missing authorized
archives fail safely. An explicit backend corridor checker searches eight dated
pairs against the configured MOTIS, without downloads or trip writes. Booking
data now reports local provider readiness and the current access shortlist.
Danish and ferry enquiries are already sent. FerryhAPI authentication and live
schedules remain pending partner documentation, not just a key. No current
import, real credentials, database schema or provider subscriptions were changed.
Validation: full Python suite passed 190 tests with two PostgreSQL tests skipped;
the subsequently added corridor-check tests passed in the 21-test focused suite.
Frontend passed seven tests, TypeScript checking and the production build.
See [setup and remaining work](timetable-integrations.md).

# Implementation status

Saved city AI increment: stop cards and map city panels expose a square Things
to do dialog. Explicit requests generate bounded structured activity ideas using
local Ollama and save model/request/preferences/source provenance to the trip.
Every generation plans/searches afresh and saves a new version, and
reopening only reads saved results. Offline/invalid-output fallbacks are saved
honestly and retried only by explicit regeneration. Trip deletion cascades to
its private city idea sets; reads and writes require the edit token.
Saved recommendations are collapsed behind a button, titled from their prompts,
and individually expandable/deletable with confirmation. Deletion is trip/city
scoped, leaves the draft and other versions intact, and triggers no inference.

Self-hosted SearXNG is required for new city recommendations; there is no web
toggle or refresh setting. Missing configuration disables generation while
keeping saved versions readable. Every explicit generation uses one query with
six bounded search excerpts, not arbitrary page
fetches or model-selected tools. There is no refresh setting or search-cache
replay. The same selected model plans a concise validated query and then reads
the excerpts and answers. Fixed topic mappings and lexical topic filters are
removed; relevance is assessed by the answering model, not guaranteed by code.
Only coarse planned month/season/year context is passed to the planner; city stay
dates on the active/selected route take precedence over a labelled overall trip
window. Exact dates stay local for generation, with timing snapshots saved and
shown alongside results. Undated trips do not assume a season. Basic PII/query guards are
not a complete detector. Planner failure is labelled as a city-only fallback.
Citations must use server-owned source IDs/URLs. Prompt v8 requires specific named
places and supported stops for self-guided walks, preferring fewer or empty ideas
to generic filler. Empty results are saved; fallback walks are no longer injected.
The generation action is now a prominent green button. Citation checks use normalized
verbatim quotes with source-level context,
and a bounded correction on validation failure. Failed AI answers retain matching
search results as explicitly labelled research leads, not confirmed activities.
These checks do not establish semantic truth, venue location or current facts;
all generated ideas remain unverified. The search
Compose image is digest-pinned, but Docker/engine startup needs local validation.

Model tuning now includes context/output limits and thinking; remote-model
aliases are rejected using local Ollama metadata before chat. Qwen3 14B Q4_K_M
is the default and documented as a candidate for the user's 16 GB GPU, without
automatically downloading a model. Migration `938e271ac640` adds city
idea/source-cache tables. See [local AI setup, privacy and limitations](local-ai.md).

Future-journey groundwork: outgoing train legs support a persisted, explicitly
unverified overnight intention before future timetables exist. The calendar
budgets transit nights and conservatively estimates pass days without claiming
a sleeper service or cabin. Users can clear the intention and return to estimates.

On-demand MOTIS research now saves server-owned `rail_journey_snapshots` and
returns opaque selection IDs. With exact trip dates, users can explicitly apply
a returned departure from the train dialog. Saved snapshots update journey
durations, local-date arrivals, transit nights and estimated rail-boarding days;
their departures anchor stay-night allocation rather than shifting silently on
later edits. Known validity checks include the arrival of an overnight train,
even if only its departure day consumes a travel day. Locked stays, trip duration,
pass limits, edit tokens and itinerary revisions remain enforced atomically.

Snapshots are research, never reservations. They expire for new selection after
24 hours; already selected research remains saved and dynamically gains a
recheck-needed label, without a provider request. Route edits discard only plans
whose original city-pair/visit no longer exists, with a warning. Map geometry and
unspecified legs remain schematic. Pass entitlement, cabins, prices, seats,
through-service identity and connection margins are not confirmed. Unverified
intentions do not assume a one-day night-train saving.

Migration `6a901b28c314` adds the snapshot table. SQLite upgrade, metadata check,
downgrade and re-upgrade were verified on a disposable database. Synthetic
journeys test future dates without any feed downloads, live keys or `.env` reads.

Swedish key/quota increment: documented host-only `TRAFIKLAB_GTFS_API_KEY` and
an explicit standalone downloader. Default execution only uses a validated saved
archive; `--refresh` permits a download subject to a 24-hour successful-cache
guard, 60-second retry spacing and a persistent local 50-attempt/30-day ledger.
Failures count, concurrent downloads are serialized, and no automatic retries
or redirects forward the key. The app and MOTIS searches never use this key.
Only synthetic keys and mock responses were tested; no real `.env` was read or
changed and no live Trafiklab requests were made during this increment.

Phase 6 coverage increment: the default MOTIS manifest now includes Entur's
Vy Rail, SJ Nord and Go-Ahead Nordic exports alongside German long-distance
rail. Downloads identify the app, retain provenance and use checksum-checked
24-hour caching for the Entur inputs. Feed audits distinguish rail calendars,
rail-served stops and nearby catalog cities from all-mode tables. Local-only
coverage diagnostics appear before searches without blocking them or claiming
that prepared metadata proves the running server's import version. An optional
Swedish local-file manifest can be merged with the defaults; current Trafiklab
GTFS Sverige 2 access is the next account/archive requirement.

Real MOTIS v2.11.3 import and adapter smoke searches passed for Oslo–Gothenburg,
Oslo–Bergen, Oslo–Trondheim and Hamburg–Munich on 20 October 2026. This was an
isolated binary test, not a Docker test or complete route/date validation.
The German feed still has a roughly 30-day horizon, while these Norwegian
snapshots extend into February 2027. Future honeymoon dates may be unpublished.

Zero-night visits are supported in stop cards, map details, final-stay preferences
and the edit API. They remain visits (including required stops), persist through
reopening and later edits, and share a calendar/pass day when the estimated
journeys occur on the same day. Freed nights go to flexible intermediate stays;
if none remain, an unfixed/unlocked final stay absorbs them with an explicit
warning. Fully fixed schedules still reject incompatible trip lengths. Zero nights
does not select a sleeper service or establish actual same-day feasibility.
Explicit timetable selection and overnight/pass-day accounting are now supported
as described above; initial holiday generation still uses daytime illustrative corridors.

Next planned priority: phase 6 travel integrations, specifically broader
self-hosted MOTIS coverage along the honeymoon corridor when relevant travel
dates are published, then better station matching, transfer margins and
through-service identity. User-applied timetable snapshots already update calendars.
See [coverage priorities](motis.md). Phase 7 real Docker/PostgreSQL/model and
backup/restore validation remains necessary before declaring a stable MVP.

Latest increment: compact stop cards, square desktop/mobile-responsive native
dialog with train sections (departures, reservations, notes), ferry research
dialog, on-demand intermediate-stay previews, and card removal controls. Must-see
removal requires confirmation and atomically updates preferences/other required
flags with revision checks. Starting/final/locked stays remain protected.
Timetable summaries show only results actually queried in this browser session,
not invented booking confirmation. The catalog now has 124 destinations and 17
island final-stay options; see [sources and limitations](data-sources.md).

## Step 1 — Infrastructure and database

Implemented local Docker Compose services, frontend/backend Dockerfiles, explicit Alembic migrations, PostgreSQL-ready models, idempotent seeds, health API and edit-token hashing. Public container manifest digests are pinned. No `.env`, API keys, host installation or permissions were changed.

Verified here: migration upgrade/downgrade/upgrade and metadata drift check on SQLite; PostgreSQL DDL generation with JSONB and timezone-aware timestamps. Actual Docker startup, PostgreSQL runtime and NVIDIA inference require the user's machine.

## Step 2 — Railway graph and route generation

Implemented 124 destinations, 444 directed illustrative rail connections plus 18 endpoint-transfer research corridors, a NetworkX MultiDiGraph, bounded required-stop ordering, a preferred-stop insertion beam, scoring and similarity penalties. Daily caps are not enforced; long legs show advice and previewed intermediate-stay suggestions. Defaults to Italy; France/Corsica, Spain, Croatia and Greece are selectable, with an island-only filter. Multi-ferry endpoint tails are explicit, not international trains. Map additions try each insertion slot rather than appending geographically earlier cities near the endpoint. Segment search prefers forward corridors but allows a return through a hub. Repeated overnight visits have independent calendar/nights records. Ranking penalizes travel time and unnecessary revisits.

The six-must-see cap is removed. Above five required stops, a bounded insertion beam covers the full required list. The UI separates route editing from must-see selection on an existing itinerary, and disconnected cities remain selectable with an explanation at generation. Retry first saves the current form to the same trip, then generates using those settings. Constraint errors show the required vs available pass/calendar days. A catalog audit confirms every city connected to Oslo can be the sole must-see with a sufficient calendar and pass allowance; the default seven-day pass remains insufficient for some long detours ending in southern Italy.

All corridor times are unreviewed engineering fixtures. Graph search uses the fastest curated corridor per waypoint pair; it can miss feasible alternatives requiring a different corridor or required-stop order outside the bounded search. Further work: operator-reviewed data, multiple corridor candidates per pair, stronger diversity guarantees and broader non-rail coverage.

## Step 3 — Scheduling, persistence and editing

Implemented calendar-night allocation, exact dates or day offsets, estimated pass days and known incompatibility checks, plus create/read/patch/delete trips and generate/list/select alternatives. Add/remove/reorder/lock/nights/endpoint edits recalculate automatically. Explicit night overrides survive subsequent edits; required and locked stays are protected. Impossible edits are atomic. Trip and itinerary revisions reject stale changes.

Preference updates preserve saved ordered stays and recalculate alternatives; they do not globally optimize existing edits. Preferred stops are soft requests during initial generation; use Add stop to guarantee a new stay in an existing route. Lock conflicts are rejected instead of silently moving locked stays. Budgets are stored, not treated as verified cost estimates.

## Step 4 — Frontend

Implemented a responsive trip form, restore/update preferences, pass fields, budgets, alternatives, selection, browser recovery token, local model settings, recommendation panel and on-demand travel discovery. The map fills the available width up to a 2400px layout and takes 78% of desktop viewport height. It shows a toggleable clickable rail network and highlights the itinerary through its transit nodes. City panels include country, interests, suggested nights, curated attractions, a city-guide link and connections. New stays are inserted in a feasible order. A city search, keyboard picker, label collision handling, fullscreen controls and a fit-route action support exploration. Horizontal stop cards wrap into rows and retain nights, locks, ordering, map focus and outgoing leg information. An original train icon appears in the header and browser tab.

Map initialization is separate from marker/route updates, so selecting a city or editing settings preserves the map instance. MapLibre v6's worker URL is explicitly configured for Next's bundler; missing this leaves GeoJSON rail lines unrendered even though DOM city markers appear. OpenStreetMap tile failures leave graph layers available. TanStack Query manages city, network, model and recommendation data; Zustand holds alternative selection.

City clicks, search results and route edits only update selection/data; they do not pan, zoom or refit the map. Camera changes are explicit through pan/zoom controls or Fit route/Europe. Double-click zoom is disabled. Panning is constrained to the European bounding region (25°W–45°E, 33°N–72°N), with horizontal world wrapping disabled.

Production build/type checks and Vitest tests pass. Browser checks cover create/edit/reopen, infeasible edits, mobile/settings, city details, map additions, desktop map dimensions and horizontal stop layout. Browser tests substitute background tiles so network availability does not affect route interaction checks. Shared libraries and fonts were extracted into a temporary directory to run Chromium without system installation. Docker cannot run in this workspace; its frontend development target and override are prepared for the user's machine.

## Step 5 — Local AI

Implemented Ollama structured schema requests, model listing, connection test, selectable local model, schema/curated-ID/tag validation, one retry, caching by inputs/model/schema/prompt, and deterministic fallback. No model free text becomes transport facts. Explanations are constructed from validated tags. Recommendations run only on request, not on itinerary edits. There is no cloud adapter; enabling a fallback flag cannot cause a cloud call.

Mock contract tests pass. Actual Qwen model behavior, performance, GPU use and VRAM fit need user verification.

## Step 6 — Travel discovery

Implemented provider interfaces, date/party validation and flight/hotel external search links with empty offers and no invented prices. Official Interrail reference retrieval is on demand, fixed to reviewed source URLs, limited in size/time, cached for 24 hours, timestamped and explicitly not interpreted as pass validity. Redirects are not followed; retrieval failures and expired cached content return `unknown`.

Live flight/hotel adapters, provider selection, authorized API keys, terms-specific caching, offer repricing, fees/baggage and live-offer tables remain pending until a provider is chosen. No keys are needed for current fallback links.

Honeymoon presentation adds two-traveller defaults, a saved pass-class selector, and booking guides on map corridors and overnight-to-overnight rail legs. Guides retain exact departure dates when available, include operator links for transit countries, distinguish pass reservations from ordinary tickets, and offer copyable research details and seating/compartment tips. They explicitly return no prices, offers or live-availability timestamps. The Booking data page and [API assessment](rail-api-assessment.md) recommend testing All Aboard first, with optional Transitland network data and Entur's open Norwegian timetable service. No live rail API adapter, provider-key collection or purchase mutation has been enabled.

## Step 7 — Validation and release

Backend coverage includes Hypothesis calendar cases, every connected city as a single must-see, branch-line revisits, more than six required stops, retry after updated preferences, and atomic failed edits. Frontend checks include retry request/revision assertions, production compilation/type checks, and browser scenarios for create/edit/reopen, mobile layout, map interaction and recovering from a failed generation. Previous infrastructure checks cover SQLite migrations, metadata drift and PostgreSQL offline DDL generation. Two PostgreSQL integration tests are provided but skipped without an explicit disposable test database.

Before calling this a stable MVP: run PostgreSQL migration/persistence/concurrency tests, Docker and GPU smoke checks, actual browser/mobile/WebGL scenarios, backup/restore, data review, and real local-model contract tests. Public deployment still needs authentication and HTTPS; no production deployment is configured.
# Self-hosted timetable increment

Coverage is now the priority over budgets/bookings. Optional manifests are supplied
for public SNCF GTFS and administrator-obtained Swiss, Austrian and Danish GTFS
archives; defaults and existing imports remain unchanged. A real isolated SNCF
import returned Paris–Lyon, Lyon–Marseille and Paris–Milan departures through the
backend adapter for 20 October 2026. The focused MOTIS suite passes 37 tests.
Italy-wide timetables, Italian NeTEx support and other expansion imports remain
unverified or unimplemented. The subsequent All Aboard increment at the top of
this document adds an optional external rail research adapter. See the [coverage/access shortlist](timetable-coverage.md)
for user-owned account requests; no Swedish download or credential inspection
was performed for this increment.

Optional MOTIS v2.11.3 Docker service/import job, checksum-verified release,
explicit GTFS preparation with provenance/calendar auditing, backend plan API v6
adapter and on-demand per-leg timetable UI are implemented. The first German
long-distance feed was downloaded/imported and Hamburg–Munich departures were
verified against a real MOTIS binary. Docker execution remains unverified here.
See [setup, limitations and coverage priorities](motis.md).

The multi-day generator still uses illustrative corridors, not MOTIS schedules.
An unreachable **preferred** city no longer vetoes a feasible mandatory route.
Daily caps have since been removed. Legacy preferences are accepted but ignored.
Long rail journeys are advisory, with suggestions that users can add as stays.
Estimated transit nights advance the calendar; endpoint ferry/ground transfers
have their own persisted mode, zero rail-pass days and unverified ferry benefits.
Actual-world feasibility is not inferred from catalog failures. Exact timetables
can require more days than these lower-bound illustrative allowances.

