# API usage

FastAPI OpenAPI at `/docs` is the executable contract. All application endpoints use `/api/v1`; the browser proxy exposes the same suffix through `/api`.

## Create, generate and reopen

```json
{
  "total_days": 21,
  "required_stops": ["prague", "venice"],
  "preferences": {"endpoint_region": "southern_italy", "final_stay_nights": 4},
  "pass": {"type": "global", "validity_type": "flexi", "travel_days_total": 7}
}
```

POST this body to `/trips`. Save `id` and `edit_token`. Supply `X-Edit-Token` for every trip/itinerary mutation and for recommendation requests. Only its digest is stored server-side. GET `/trips/{id}` returns the saved request, trip revision and alternatives, never the edit token.

POST `/trips/{id}/generate` returns saved alternatives if they already exist; it does not silently replace edits. GET `/trips/{id}/itineraries` lists alternatives. POST `/itineraries/{id}/select` selects one alternative. DELETE `/trips/{id}` removes its plans and normalized records.

After a failed generation, retry must first PATCH the saved trip with the current form and `expected_revision`, then POST `/trips/{id}/generate`. The frontend now performs both steps and retains the new trip revision even if generation fails again. Previously retry silently reused the original request.

Required and preferred lists support up to 90 cities. Required lists above five use a bounded insertion search instead of enumerating factorial permutations. Route feasibility depends on calendar days, rail-pass allowance and supported connections, not a daily cap. Legacy `preferences.max_daily_travel_hours` is deprecated and ignored, including on saved trips. A branch-line visit may return through a previous hub. `stops[].visit_number` and `is_revisit` distinguish repeated overnight visits, each with its own calendar interval. City-based edits reject ambiguous repeated-hub edits with `MULTIPLE_VISITS`.

Legs include `mode` (`rail` or `ferry_transfer`), `rail_minutes`, `is_long_journey`,
`travel_advice`, `suggested_stop_ids` and `travel_nights_estimate`. Journeys over
eight hours are advisory; no artificial daily overnight stops are inserted.
With no requested intermediate stays, the planner offers one midpoint stay.
Athens can use the explicit Bari–Patras ferry / onward ground-transfer research
corridor, allowed only when completing an endpoint, not as an intermediate rail
shortcut. Source, booking links and estimated components are in `connections`.
Other unmodeled gaps still need data; no arbitrary flight/ferry is invented.

`total_nights = stay_nights + transit_nights_estimate = total_days - 1`.
Transit nights advance arrival dates. Complete 24-hour blocks in a rail leg add
estimated transit nights and rail-pass days. These are lower-bound allowances:
departure times, layovers and midnight crossings may increase them. Endpoint
ferry/ground legs have zero **rail** pass days, with ferry benefits and pass-day
requirements unverified. Their dates do not extend rail pass-validity checks.

## Edit a route

`GET /itineraries/{id}/legs/{zero_based_index}/stop-suggestions` is read-only and
on demand. It returns up to six intermediate-stay ideas with `before_minutes`,
`after_minutes`, `extra_travel_minutes`, suggested and actually allocated nights,
interest matches, `extra_pass_days`, `can_add` and a constraint explanation.
Candidates include existing transit cities and small nearby detours, checked
against a non-persisted insertion preview at `position = leg_index + 1`. Estimates
are not dated train services. Ferry legs return no rail-stop suggestions.

An ordinary `remove_stop` still protects must-see stops. To deliberately remove
one from the selected route **and** the trip's must-see list, send
`remove_required: true` and `expected_trip_revision` alongside the existing
itinerary revision. The UI asks for confirmation. The mutation is atomic;
authorization, stale revisions, locks, the starting city and final endpoint remain
protected. Other alternatives retain the city only as an optional stay, with
updated required flags and revisions. The response includes `trip_revision`.

`preferences.endpoint_region` now also accepts `islands`. There are 17 new
island endpoints. Some use a multi-connection terminal tail (Bari → Athens →
Naxos, for example). These gateway stays can be edited without requiring an
international train, and automatically inserted/unprotected gateways can be
dropped when changing the endpoint. All ferry details remain unverified research.

PATCH `/itineraries/{id}`:

```json
{"expected_revision": 1, "operation": "set_nights", "destination_id": "prague", "nights": 4}
```

Other operations: `reorder_stop` requires `position`; `add_stop` accepts an optional `position`. Omitting it tries every insertion slot and selects the shortest feasible itinerary while retaining existing stays and locks. `lock_stop` uses `locked`; `remove_stop` and `change_endpoint` use `destination_id`. Positions are zero-based; Oslo is fixed at zero and the endpoint remains last. Impossible edits return 422 without changing the stored result. Stale revisions return 409. Locking protects both nights and calendar interval.

## Map data

- GET `/destinations`: city coordinates, country, interests, suggested nights, endpoint status and airport.
- GET `/destinations/{id}`: the same city fields plus curated `attractions` with names, descriptions and provenance.
- GET `/rail-network`: directed rail corridors with estimated duration, changes, service type and provenance. The map groups opposite directions visually; route planning retains directionality.

The selected itinerary's `legs[].via` contains transit city IDs. Use these to draw the route through actual graph nodes rather than connecting overnight stays directly. The lines remain schematic; these are not surveyed railway geometries or current train timetables.

## Update trip preferences

PATCH `/trips/{id}`:

```json
{"expected_revision": 1, "total_days": 24, "budget": {"total": "32000.00"}, "preferences": {"interests": ["culture", "food"]}}
```

Nested supplied fields are merged, then the entire request is revalidated. Existing ordered stays and explicit nights are preserved while scheduling/scoring are recalculated. All alternatives must remain feasible. To switch date mode supply both `date_mode` and `start_date` (including null for flexible dates). New preferred stops remain soft; use add_stop for a guaranteed stay in a saved route.

## Recommendations and travel discovery

POST `/travel/rail/booking-guide` accepts `origin_id`, `destination_id`, optional `via` (including both endpoints), `departure_date`, `adults` (default two), `travel_class` (1 or 2) and `ticket_mode` (`pass` or `tickets`). It returns country-relevant operator links, official reference URLs and general booking guidance. No external network call or provider credential is needed. Its `status` is `guidance_only`; offers are empty, price is null and `availability_checked_at` is null. `guidance_reviewed_on` is a static review date, not a live provider timestamp. See [the coverage and signup assessment](rail-api-assessment.md).

- GET `/ai/models`: installed local model names and availability; cloud is always disabled in this build.
- POST `/ai/test` with `{}` or `{"model":"qwen3:14b"}`: test schema-based local inference.
- POST `/itineraries/{id}/recommendations` with the same model body and edit token: validated curated ranking, or deterministic fallback. Cache key includes model, prompt, schema, preferences and catalog context.
- POST `/travel/flights/search` with `origin_airport`, first/only `departure_date`, optional inclusive `departure_date_end`, `adults` and optional `currency`. `trip_type` defaults to and only accepts `one_way`. Ranges support up to 31 departure dates. Returns a one-way Google Flights search intent per date in `search_links`, with the first date retained as `search_url`. These are individual date links, not a verified native Google flexible-range search, return-trip dates or a live price comparison. Empty offers and no retrieval timestamp; destination is BGO. Confirm search settings on the booking site. Flight research does not edit the trip or hotel dates.
- POST `/travel/hotels/search` with `destination_id`, exact `check_in`/`check_out`, `adults`, `rooms` and optional `currency`: link-only accommodation search.
- POST `/travel/rail-rules` with `{"topic":"reservations"}` or `{"topic":"countries"}`: retrieve/cache a fixed official source reference. Status stays `needs_verification`, or `unknown` on failure.

## Errors and confidence

```json
{"error":{"code":"PASS_LIMIT_EXCEEDED","message":"The estimated rail travel days exceed the remaining pass days.","details":{"travel_days_estimate":7,"remaining":2}}}
```

Known incompatible passes are rejected. Returned estimates remain `needs_verification`, or `unknown` if flexi travel-day limits are absent. Illustrative graph data never establishes definitive pass validity. Currency fields accept uppercase three-letter codes; provider-specific currency support remains future work.

Route score weights are configurable on the server through ROUTE_SCORE_WEIGHTS as a JSON object with interest_match, travel_efficiency, pace, diversity and endpoint_quality. Each weight must be between zero and one and their sum must be one. Defaults match the specification. Secret/environment configuration remains user-managed.
# Self-hosted rail timetables

`POST /api/v1/travel/rail/timetables` accepts `origin_id`, `destination_id`,
required `departure_date` (YYYY-MM-DD), and optional `departure_time` (HH:MM,
default 08:00, origin local time without offset). Cities must exist and differ.
Requests go only to the administrator-configured `MOTIS_BASE_URL`, never a URL
from the client. No edit token is needed for this read-only catalog lookup.

Returns `provider: self-hosted-motis`, `status` (`scheduled`, `no_journeys`,
`not_configured`, `unavailable`, `unsupported_origin`, or `invalid_local_time`),
`message`, `notice`, `checked_at`, `origin_timezone`, and up to three `journeys`.
Each journey has offset-bearing departure/arrival times, duration in minutes,
transfers, and rail/walking legs with station names, operator/train labels,
timezones and real-time indicators. `price` is null and `reservation_status` is
unknown, independently of timetable availability. `prepared_sources` contains
credits and service envelopes from the local prepared-feed manifest, not an
assertion about the running server's import version. See [MOTIS setup](motis.md).

`POST /api/v1/travel/rail/coverage` accepts `origin_id`, `destination_id` and an
optional `departure_date`. Both cities must exist. This endpoint only reads local
prepared metadata: no publisher request, MOTIS query, import or itinerary mutation
occurs. Returns `status`, `message`, `notice`, `configured`, `import_verified:
false`, endpoint stop-presence diagnostics and `sources` with rail calendar
envelopes/counts and per-source `date_status`, `origin_stops`, `destination_stops`.
Missing/old metadata remains unknown, not confirmation of absent real-world
service. A longer calendar in a different country's feed does not extend another
feed's city coverage. Dates within an envelope can still contain service gaps.
The timetable endpoint includes the same report as `coverage`; these advisory
checks never veto a search against the running server, whose imported version
may differ from the prepared files.

# Saved train-leg plans

Timetable search validates returned chronology and stores rail/walking journeys
in `rail_journey_snapshots`. Each selectable journey includes `selection_id`.
These are researched schedules, not fares or reservations. Apply migration
`6a901b28c314` before using the updated timetable endpoint.

The existing authenticated `PATCH /api/v1/itineraries/{id}` accepts three new
operations, with `expected_revision`, outgoing origin as `destination_id`, and
zero-based `leg_index`:

- `set_leg_plan`: save an unverified overnight intention, with no provider calls.
- `set_journey`: add `journey_id` equal to the opaque search selection ID. The
  server loads its own snapshot, verifies city pair and 24-hour selection expiry,
  and requires exact trip dates. Raw client journey times are rejected.
- `clear_leg_plan`: remove the intention/selection and use corridor estimates.

All recalculate atomically and retain locked calendar intervals, night overrides,
trip duration and pass checks. Dated departures pin cumulative stay allocation.
`journey_plans` are keyed by city-pair and visit occurrence, not unstable indexes;
plans whose pair disappears are dropped with a warning. Reopened leg summaries
recompute freshness without fetching anything. Expiry prevents a new selection,
but does not erase an already selected snapshot. Zero-night saved connections
reject overlapping arrival/departure times; transfer margins remain unverified.

# Saved city activity ideas

`DELETE /api/v1/trips/{trip_id}/cities/{destination_id}/ideas/{idea_id}` requires
the trip edit token and removes only that trip/city's saved version. Returns 204,
or 404 for a missing version or scope mismatch. Does not run inference/search,
change the route, or run search/inference. No new migration is required.

`GET /api/v1/trips/{trip_id}/cities/{destination_id}/ideas` requires the trip edit
token and returns up to 20 saved versions, default model and a web-availability
flag. It only reads local records; no search or inference occurs.

`POST` to the same URL accepts optional `question` (3–600 characters), `model`,
`research_focus` (optional public search keywords, max 120 characters),
`itinerary_id` (optional UUID of a route owned by this trip; defaults to the
selected route), and the compatibility field `refresh` (no longer needed: every POST creates a new
version). The removed `use_web` and `refresh_web` fields are no longer accepted.
The city must exist but need not yet be a route stop. Every POST uses the selected
local model to plan one query, runs a fresh search and uses the same model to
answer, saving a new version even for identical input. There are no search flags
or generation-cache replay. Missing `SEARXNG_BASE_URL` returns
`WEB_SEARCH_NOT_CONFIGURED` (503) before any inference. GET never searches
or regenerates, even when results are old.

Responses include `id`, `saved_at`, `cached`, `request`, `model`, `source`,
`introduction`, `ideas`, `sources`, `web_status`, `web_used`, `web_cached` and an
explicit uncertainty warning. Time allowances and all idea text are unverified.
`generation_status` distinguishes `generated`, `invalid_response`, `unavailable`
and `timeout`. If local AI fails but useful web excerpts exist, `source` is
`web_research`: its items are source leads, not activity recommendations; their
time allowance is not a venue visit estimate. `web_query` preserves the search;
`request.travel_context` preserves planned visit dates, nights and month/season/year
periods. City visits on the requested route take precedence over the overall trip
window; repeat visits are preserved, and undated trips return null context. A
foreign itinerary returns 404. Only coarse timing reaches the query planner and
may appear in search; exact visit dates stay in local generation/saved data.
`query_plan` records the query, planner version, source, status and selected model.
Planner failure uses a labelled city-only fallback. `web_cached` is false for new
web requests; source snapshots are saved but not replayed for generation.
Only provided source IDs can be cited; the model cannot return clickable URLs
or trigger actions. Only the validated generated query is sent to SearXNG, not
the raw question or trip record. Basic redaction and query guards are not a
complete PII detector; generated interests can still be disclosed. Unknown
citations/schema errors get at most one model retry, then
a labelled saved fallback. Remote-model aliases are rejected before inference.

Migration `938e271ac640` is required. See [local AI setup](local-ai.md).



## Additional timetable sources

GET `/api/v1/travel/timetable-sources` reads only local provider configuration;
no publisher or provider network call occurs. It exposes no credential values.
FerryhAPI reports `awaiting_partner_contract` until its actual technical contract
is available. MOTIS configuration status does not verify an import.

POST `/api/v1/travel/rail/allaboard/locations` accepts `{city_id}` and explicitly
queries up to ten nearby provider locations in the catalog city's country.
POST `/api/v1/travel/rail/allaboard/timetables` accepts `origin_id`,
`destination_id`, `origin_uid`, `destination_uid`, `departure_date`. Provider UIDs
are selected from location results. Requests cannot configure hosts or headers.
Both endpoints return `not_configured` without network I/O unless the provider
is enabled and keyed server-side. Search distinguishes `scheduled`, `pending`,
`no_journeys` and `unavailable`. A pending result never causes an automatic retry.

All Aboard responses have `Cache-Control: no-store`. No provider results are
persisted or returned as selectable itinerary snapshots. Station-local time
strings retain the provider's documented semantics; modes retain bus/ferry/train
identity. Sandbox output includes `environment: test`. No fares, availability,
passholder rules or bookings are queried. See [setup](timetable-integrations.md).


## Endpoint comparison and connection margins

POST `/travel/endpoints/compare` accepts `origin_id` (connected Italian city,
default Bari) and one to six unique `endpoint_ids`. It returns local modeled
routes, minute breakdowns, ferry/ground counts, overnight lower bounds, seasonal
caveats and return-airport candidates. A missing modeled route is unselectable;
no provider request or itinerary mutation occurs.

POST `/travel/connections/check` accepts a modeled ferry `connection_id`, naive
local `ferry_departure` and `ferry_arrival`, optional `arrival_at_start` and
`onward_departure`, plus optional port-access/ferry-check-in overrides and onward
transfer/check-in minutes. It resolves each country's timezone, rejects DST gaps
and overlaps, reports spare/short minutes and flags early/late arrivals. Times
are user research only and are never persisted or applied to the calendar.

Network/itinerary transfer connections expose `connection_plan`; itinerary
results also expose `airport_access`. Older saved routes receive derived details
without writes or revision changes. See [full contracts and assumptions](endpoint-comparison.md).
