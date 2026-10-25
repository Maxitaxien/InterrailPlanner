# Timetable expansion setup

Reviewed 17 October 2026. MOTIS supplies routing, and the national feeds supply
its schedules. External journey APIs are queried separately and never bulk-loaded
into MOTIS. No API subscription, message to a provider or purchase was made here.

## Accounts and files to supply

| Priority | Source | What you supply | Implemented machinery |
| --- | --- | --- | --- |
| 1 | [Trafiklab GTFS Sverige 2](https://www.trafiklab.se/api/gtfs-datasets/gtfs-sverige-2/) | `TRAFIKLAB_GTFS_API_KEY`, if not already configured | Existing host-only downloader, quota ledger and local GTFS manifest. This increment did not inspect or use your key. |
| 1 | [Rejseplan Labs](https://labs.rejseplan.dk/hc/da/articles/21553113674909-Adgang-til-data-fra-Labs) | Your enquiry is already sent. Request authorized **GTFS Schedule/Static**, then place the ZIP at `motis/downloads/denmark.zip`. | Local feed preparation/auditing/import path. No guessed Danish authentication flow: a journey API key may not grant bulk-feed access. |
| 2 | [All Aboard](https://allaboard.eu/join) | `ALLABOARD_API_KEY`; start with test access. Confirm private schedule-only eligibility, fees and Italian/cross-border operators. | Server-side GraphQL location and journey adapters, explicit train-dialog controls, safe local readiness reporting. Disabled by default. |
| 2 | [Ferryhopper FerryhAPI](https://partners.ferryhopper.com/ferryhapi) | Your enquiry is already sent. Obtain partner docs, sandbox endpoint, exact auth scheme/credentials, port catalogue, schedule examples, limits and storage terms. | Readiness reporting and documented integration requirements. **Live ferry adapter is pending this technical contract**; no guessed key variable or request format. |
| 2 | [SNCF Voyageurs](https://transport.data.gouv.fr/datasets/horaires-sncf) | No key. Explicitly select the public feed. | Existing French manifest, checksum cache and GTFS audit; included by the new preparation manager on request. |
| 2 | [ÖBB](https://data.oebb.at/de/datensaetze~soll-fahrplan-gtfs~) | No key. Accept publisher terms and save the selected GTFS archive as `motis/downloads/austria.zip`. | Existing local archive manifest plus preparation manager. Domestic named-operator scope; verify international services separately. |
| 2 | [Swiss Open Data Mobility](https://opentransportdata.swiss/en/cookbook/timetable-cookbook/gtfs/) | No key for timetable file downloads. Select the appropriate year and save `motis/downloads/switzerland.zip`. | Existing local archive manifest plus preparation manager. National mixed-mode archive may exceed current feed size limits. |

Italy is the main remaining rail gap. All Aboard is a candidate on-demand source,
not proof of national or passholder coverage. The official Italian NAP Trenitalia
NeTEx source still requires a validated import/conversion path; this project's
GTFS prep does not accept it. Greece, Croatia and Slovenia rail branches remain
unverified; a ferry API does not fill their rail schedules. Trainline and direct
Trenitalia commercial partnerships remain alternatives if All Aboard declines
this use. No Transitland or second rail-provider key is needed initially.

## Enable the prepared rail API

All Aboard's [setup contract](https://docs.allaboard.eu/intro/getting-started)
documents the `api-key` and `session` headers, test/live hosts and GraphQL path.
The [scope guide](https://docs.allaboard.eu/intro/scopes) documents the base `test`
or `live` scope. Ask for the least access that permits locations/journeys. This
application contains no offer queries, booking mutations or payment operations.
Confirm the account's permitted usage and fees before enabling it.

Put the key in the server `.env` yourself, not in chat or browser settings:

```dotenv
ALLABOARD_ENABLED=true
ALLABOARD_API_KEY=your-private-key
ALLABOARD_ENVIRONMENT=test
ALLABOARD_TIMEOUT_SECONDS=30
```

Compose passes these only to the backend. Recreate/rebuild that service with your
usual Compose overrides. For real research change the environment to `live` only
after live access is approved. Sandbox output is explicitly labelled in the UI.

Open a train leg, expand **Search additional rail coverage · All Aboard**, then
click **Find provider cities / stations**. This makes two explicit nearby-location
lookups. Choose both provider locations, then search the selected date. A city
(meta) location is preferred in the list but never silently chosen. The provider
searches the whole selected pair with its NON_STOP journey variant (which can
include train changes but avoids planned overnight stopovers). There are no
background requests, automatic retries or automatic MOTIS-to-paid-provider fallback.

The [provider schema](https://docs.allaboard.eu/ref/types) defines DateTime as a
naive station-local time. The app preserves and labels those strings rather than
inventing timezone offsets or elapsed durations. Buses and ferries retain their
actual modes. Pending/errors/unsupported stopovers are not reported as proof of
no service. Results cannot be applied to the itinerary, stored as rail snapshots,
or used for pass-day calculations yet. Server responses use `Cache-Control:
no-store`; this feature writes no provider results to the database. The UI holds
only current research in component memory and clears it when the city pair/date
changes or the component unmounts. Timezone resolution and provider-approved
persistent storage are required before calendar application can be added.

Requests have a fixed HTTPS host selected by the test/live enum, a 60-second
maximum configured timeout, a 2 MB response limit and no redirect following.
Upstream exceptions and GraphQL messages are not returned to the browser. Keys
use secret-valued backend configuration and are absent from readiness responses.

## Manage feed preparation without dropping expansions

Read-only local readiness (no downloads, credentials, imports or server requests):

```sh
python3 motis/coverage.py status
```

The status distinguishes absent archives, public download inputs and prepared
rail calendars. It does not validate archive bytes, a running import or journeys.
To add sources explicitly after obtaining their archives:

```sh
python3 motis/coverage.py prepare \
  --include france --include sweden --include denmark \
  --include austria --include switzerland
```

Include only sources you have access to. Missing required local archives fail
before downloading/staging. The command retains previously prepared **known**
expansions even if you omit their `--include` on a later run. Previously prepared
custom sources cause a refusal: use the original `prepare.py` with your complete
manifest set instead. Broken previous metadata also causes a refusal. Source
licences, attribution, checksums and calendar/city diagnostics use the existing
preparation workflow. Calendars are never extended. This command prepares the
default feeds plus selected/retained expansions; it performs no MOTIS import,
restart, Swedish refresh or authenticated feed download.

Back up and stop the running service before preparing its work directory, then
import and restart as described in [MOTIS setup](motis.md#add-and-maintain-feeds).
Preparation by itself does not expand the running server. No current import was
changed during this increment; all new automated tests use isolated fixtures.

## Check real connecting services after import

Choose an actual published date, then run inside the backend environment:

```sh
python -m app.scripts.check_timetable_corridors --date 2026-10-20
```

For Compose, prefix with `docker compose` and the same overrides used to run your
app, followed by `exec backend`. The command searches eight city pairs through
the configured MOTIS only: Oslo–Gothenburg, Gothenburg–Copenhagen,
Copenhagen–Hamburg, Hamburg–Munich, Munich–Milan, Milan–Bari, Paris–Milan and
Zurich–Milan. It does not contact publishers or external commercial APIs, download
feeds, save snapshots, or modify trips. It returns a JSON report and exits nonzero
unless all eight return scheduled journeys. Empty searches remain coverage/date/
station-matching diagnostics, not proof that the real journey is impossible.

Run with your actual dates when published. Example dates are not future service
promises. Interrail acceptance, supplements, cabins, availability, connection
margins and operating changes still require verification.

## Remaining partner-dependent work

For FerryhAPI, verify the exact product received (not all Greek ferry suppliers
have the same API). Next implementation needs its real authentication, port IDs,
route/date search contract, timezone semantics, schedule/availability distinction,
error/limit behavior and permitted storage. Test Italy–Greece crossings and each
requested island; never infer Croatian coverage from a general operator list.
The existing ferry/ground corridor research and booking links continue to work.

For Denmark, if the approval provides only a journey API rather than GTFS, a
separate adapter needs that approved API's technical contract. Do not send those
credentials to MOTIS or rename response XML as GTFS.

Tests validate the new contracts using synthetic credentials/responses, feed
retention/failure behavior, explicit UI requests and cleared stale research.
Live All Aboard/FerryhAPI access and Danish/Austrian/Swiss imports have not been
validated. Docker/PostgreSQL/GPU runtime validation remains a separate unfinished
item in the implementation plan; Docker is unavailable in this workspace.
