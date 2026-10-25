# Architecture

Next.js serves the browser and proxies `/api/*` to FastAPI `/api/v1/*`. FastAPI uses SQLAlchemy and PostgreSQL; Alembic owns schema changes. Tests use isolated SQLite databases with foreign keys enabled. No production fallback to SQLite is configured.

The MultiDiGraph retains directed service alternatives. The generator uses shortest corridors through bounded required-stop orders, a preferred-stop insertion beam, and scoring/similarity penalties. There is no daily rail cap. Long legs expose advice and suggested intermediate stays rather than being rejected. An explicit one-way Bari–Patras ferry / Athens ground-transfer corridor can complete the endpoint; it is not a rail edge or an intermediate shortcut. Other gaps still require modeled data. The bounded search returns up to three alternatives and does not claim optimality.

The scheduler treats N calendar days as N-1 nights, including stays and estimated transit nights. Each full 24-hour rail block adds a lower-bound transit night and pass day; the modeled endpoint ferry has an explicit overnight allowance and zero rail-pass days. Transit nights advance arrival dates. Actual departure times and layovers can require more days. Required stops have stays; other graph nodes may be transit-only. Final nights stay fixed and spare nights go to unlocked intermediate stays; with none requested, one midpoint exploration stay is offered. Night trains still require dedicated modeling. Ferry-pass benefits are not inferred from rail validity.

Money uses fixed-precision numeric columns. Time stamps are timezone-aware in PostgreSQL. Core request preferences/pass details and complete immutable route values are JSONB; normalized stops and legs are replaced transactionally with each revision. The trip-pass table initially stores the typed pass contract as JSONB.

Trip edit tokens contain 256 random bits, are returned once, and are stored only as SHA-256 digests. Mutations use `X-Edit-Token`. Browser recovery uses localStorage; there are no user accounts. Reads are accessible to anyone who has the trip UUID. This is intended for a loopback-only local installation.

Itinerary edits use an atomic conditional revision update. Rejected calculations never persist partial edits. Locked stays retain nights and calendar intervals. Required stops and Oslo cannot be removed. Generating an already planned trip returns its alternatives without replacing saved edits.

Ollama requests use schema-constrained output. Only curated attraction IDs and category tags are accepted, then descriptions/explanations are rendered from curated text and templates. One retry precedes deterministic fallback. No cloud adapter exists. Explicit recommendation requests prevent inference from rerunning on each edit. Successful results are cached by complete relevant context and schema.

Travel providers are separate interfaces. Current flights/hotels return external search links and zero offers; no prices are inferred. Official rail references are fetched only on request from fixed URLs with size/time bounds and a 24-hour cache. Source retrieval does not determine individual pass validity.
