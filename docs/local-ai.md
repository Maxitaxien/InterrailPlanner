# Saved city ideas with fresh web research

Open **Things to do in …** on a stop card or map city panel. The square dialog
loads saved results only. Describe the kind of day you want, then explicitly
choose **Generate & save ideas**. Local Ollama can suggest activities beyond the
curated catalog, with rough time allowances and references for follow-up.

Every result is saved to the trip's database, including its question, model,
preferences, generation settings, timestamp, source excerpts and reference dates.
Reopening or reloading does not generate, search, or refresh. Every explicit
Generate or Regenerate plans a query and runs a fresh search, even
for an identical prompt. There is no local-only or cached-generation option.
**Regenerate & save new version** keeps the old version;
the latest 20 versions are listed behind **Saved recommendations**. Each entry
is titled from its prompt; click to expand it, or use **Use this prompt** to copy
its settings into the editor without generating. Browsing entries does not change
your draft. Delete an individual version with confirmation to permanently remove
it from this trip; other versions are unaffected. No AI
or search runs on deletion. They survive route changes and
can be requested for catalog cities not yet in the itinerary. Deleting the trip
also removes its private idea sets.

Ideas are **unverified inspiration**, even with citations. Search snippets do not
prove a model's claims. Recheck venue existence, opening dates, accessibility,
tickets and prices with official sources before a honeymoon a year away. Neither
model output nor a source can edit the route, calendar, reservations or budget.
No booking or purchase tools are exposed to the model.

## Upgrade first

Back up PostgreSQL, rebuild the backend, and apply migration `938e271ac640`:

```sh
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml build backend
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml run --rm backend alembic upgrade head
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml -f compose.search.yaml up -d
```

Configure the SearXNG secret below before starting with the search override.
Omit the MOTIS override only if you do not use MOTIS. No feed preparation, Swedish
download, inference, or web search is triggered by this migration/startup.
Frontend development mode reloads the new UI automatically.

## Larger local model: first candidate for 16 GB VRAM

NVIDIA lists [16 GB for the RTX 4070 Ti Super](https://www.nvidia.com/en-us/geforce/graphics-cards/40-series/rtx-4070-family/).
[Qwen3 14B in Ollama](https://ollama.com/library/qwen3:14b) is published as
Q4_K_M, about 9.3 GB of weights. That makes it a reasonable larger-model starting
candidate, **not a measured fit or speed guarantee**: KV cache, context length,
runtime overhead, other GPU applications and driver use need additional VRAM.
The default model is `qwen3:14b`. Explicit `.env` or browser model preferences
still take precedence; clear the saved browser preference to use the server default.

Explicitly download the model on your machine:

```sh
docker compose exec ollama ollama pull qwen3:14b
```

No selection is needed when using the default. City requests use the
model entered in their dialog, then the browser's saved model, then the server
default. Models are never pulled automatically.

If your root `.env` still specifies the old model, update it manually. You can
also adjust the server tuning there:

```dotenv
LLM_MODEL=qwen3:14b
LLM_TIMEOUT_SECONDS=180
LLM_NUM_CTX=8192
LLM_NUM_PREDICT=2048
LLM_THINKING=false
```

Recreate the backend with your full Compose file set after changing these values.
Start with thinking off for short, structured city suggestions. The adapter sends
the [structured output schema](https://docs.ollama.com/capabilities/structured-outputs)
and [thinking option](https://docs.ollama.com/capabilities/thinking) supported by
the pinned Ollama API. Other model families can have different thinking controls.

After **Test connection** or a city request, inspect actual placement:

```sh
docker compose exec ollama ollama ps
```

Check the processor/GPU placement rather than assuming a successful response means
full GPU residency. If memory is tight, try `LLM_NUM_CTX=4096` and
`LLM_NUM_PREDICT=1024`, close other GPU-heavy applications, or keep the 8B model.
No actual 4070 Ti Super inference benchmark was run in this workspace.

Before each generation the adapter checks local `/api/show` metadata and rejects
remote-model aliases; cloud-tagged model names/URLs are also rejected. It does
not call a cloud inference API or use an external AI API key. The administrator
must still point `OLLAMA_BASE_URL` at their own trusted Ollama instance.

## Required for new city recommendations: self-hosted SearXNG

New city recommendations always use web search; there is no enable/disable or
refresh setting. SearXNG must be configured to generate them. Saved versions
remain readable without it. Search only runs when you explicitly generate or
regenerate, never when opening saved ideas.
This is a bounded backend-controlled search, not an
autonomous browsing agent or unrestricted tool access. The supplied instance
uses DuckDuckGo and Wikipedia, not Google scraping, and requires no paid search
API account. Upstream availability/rate limits still apply.

Generate a signing secret yourself:

```sh
openssl rand -hex 32
```

Paste the result into `.env` yourself as `SEARXNG_SECRET=…`. This signs the search
service's local sessions; it is not a search-engine API key. Do not reuse your
Trafiklab or other provider keys. No secret was created, read or changed here.

Add the search override to your existing Compose file set (required for new city AI):

```sh
docker compose -f compose.yaml -f compose.dev.yaml -f compose.motis.yaml -f compose.search.yaml up -d --build
```

Keep the override on later backend recreation commands. SearXNG is exposed only
at `127.0.0.1:8081`, with an image pinned by its public registry digest and JSON
format enabled. The backend uses `http://searxng:8080`. Keep this private: the
supplied search config disables public-instance bot limiting and is not a public
search deployment. Actual container startup remains to be verified locally.

For a backend outside Docker, manually configure `SEARXNG_BASE_URL` to your
trusted instance. There is no enable/disable feature flag. URLs come from admin config,
never browser/model input. See the [SearXNG container guide](https://docs.searxng.org/admin/installation-docker.html)
and [JSON search API](https://docs.searxng.org/dev/search_api.html).

In the city dialog ask your question and explicitly generate. **Model & web
research** contains the model and optional public focus, not search toggles. The same selected local model
first creates one concise, targeted query, then reads search excerpts and answers
the original question. There are no fixed topic mappings or topic-word filters.
The optional **Research focus** supplies public keywords to prioritize; blank
lets the model plan from your question. The planner receives only city/country,
question, this optional focus and coarse planned month/season/year context when
dated, not exact visit dates, pass details, budgets, identifiers or edit tokens.
Only the generated query goes to search engines. It can disclose interests and
coarse timing: do not include private information in the question.
Basic identifier redaction, length/word limits, city anchoring and rejection of
URLs, operators, standalone numbers other than server-supplied travel years,
and common identifiers are enforced, but are
not a complete PII detector. Query planning and answer generation remain local.
If planning is unavailable, invalid or times out, an honestly labelled city-only
query is used; no raw-question or keyword-table fallback is sent externally.

The backend makes at most one search call per requested city generation, with
up to six short excerpts from one results page. It never automatically fetches
the returned URLs, follows redirects, or lets the model choose URLs/search loops.
Queries fan out to the two configured engines inside SearXNG. Only safe HTTPS
links are retained; literal IP/private-host links and embedded credentials are
discarded. Excerpts are treated as untrusted data, not instructions. Model output
may cite only known source IDs; all citations are rendered from server-owned URLs.
Prompt v8 asks for real named places, direct topic relevance, and an honest lack
of results rather than invented tours. The general query-planning instruction
lives in `backend/app/services/city_query.py`. Query wording is model-generated,
not guaranteed to be an exact template for a particular interest.
For dated trips, both model steps receive timing context. A city's dates on the
active route take precedence (including preview alternatives and repeat visits);
otherwise the overall trip window is explicitly labelled as uncertain for this
city. The planner may add a month, season or supplied year only when helpful,
not to every evergreen query. The answering model also receives exact local stay
dates and nights for seasonal suitability and pacing, but must not treat them as
proof of future venue openings, weather or event schedules. Undated trips get no
assumed season. Saved versions retain their original timing snapshot, displayed
as **Timing used**. Seasons are Northern Hemisphere meteorological labels, not
forecasts. No new migration is needed.
Each recommendation should put an actual place name in its title, explain what
to do there and why it matches the interest, and cite supporting evidence.
Self-guided walks need at least two named relevant stops supported by sources;
otherwise the model is told to omit them. Neighbourhood/address details must be
sourced, not guessed. Fewer suggestions or an empty result are preferred over
generic filler. Empty answers are saved and displayed honestly; the offline
fallback no longer substitutes a generic walk. These are prompt instructions,
not a deterministic guarantee that a local model will follow every rule.
Each generated citation requires a supporting quote found in a supplied
title/excerpt, allowing whitespace, case, accents and typographic normalization.
The answering model is instructed to assess semantic relevance and ignore
unrelated sources. Verbatim-quote validation does not mechanically prove semantic
relevance. A failed answer gets one bounded correction with validation feedback,
without another search. If it still fails but search results exist,
those results are saved as **search leads**, not AI recommendations or confirmed
venues. Their snippets and links stay available instead of a generic fallback;
no activity duration is inferred from a snippet. The UI distinguishes invalid
answers, unreachable AI and timeouts. The local model has not been benchmarked
or live-verified here.
Supporting quotes
and the exact search query are saved and shown in the dialog. These checks do
not prove a claim, place identity/location or current availability: snippets can
be stale or misleading, and full pages are not fetched. Old saved versions remain
unchanged; explicitly regenerate for the improved prompt and research pipeline.

Every web-assisted generation runs fresh query planning and one fresh SearXNG
request, including identical prompts. There is no refresh setting or search/plan
cache replay. Results and their exact query, planner/model metadata, excerpts and
retrieval dates are saved with each recommendation version. Reads/deletion never
run inference or search. Existing saved versions stay unchanged. The historical
`city_web_cache` table is left intact for compatibility but is no longer read or
written by city research. No new migration is needed.

Planning is capped at 30 seconds and shares the existing overall request deadline
with search and both answer attempts; it does not double the model time budget.

## Failure behavior and verification

If a configured search service fails, the attempt is saved as failed and any
answer is labelled as having no web evidence; this is failure handling, not a
local-only mode. Without a configured search URL, generation returns 503 before
any model calls and the UI explains the missing service. If Ollama is offline, times out or twice returns invalid
output, a clearly labelled curated fallback is saved instead. Regenerate
explicitly to retry; opening a saved fallback does not keep retrying inference.
City generation has a bounded wall-clock budget below the frontend proxy limit.
A per-process gate prevents simultaneous city requests from queuing extra GPU
work in this private single-worker deployment.

Both reading and generating saved city ideas require the trip edit token. Tests
use synthetic models/search responses and isolated databases. Migration
round-trips and browser save/reopen/version behavior were verified. Real model
quality, GPU placement, Docker/SearXNG engine access and PostgreSQL runtime still
need checks on your machine. No `.env` was read or changed, and no live key,
model download or Swedish timetable download was used during implementation.
