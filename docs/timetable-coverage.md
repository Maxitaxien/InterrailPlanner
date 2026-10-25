# Timetable coverage and access shortlist

Reviewed 17 October 2026. Timetables take priority over budgeting, fares and
booking. MOTIS is the local routing engine, not a supplier of European schedules:
its coverage depends on the feeds we import. A commercial journey API is a
separate future adapter, **not** a feed that can be inserted into MOTIS.

Current implementation/setup: [timetable integration machinery](timetable-integrations.md).
The Danish and ferry partner enquiries have already been sent. All Aboard now
has an opt-in, research-only adapter; test/live access is still unverified.

## What is prepared, and what is still missing

The default manifest has Norwegian Vy Rail, SJ Nord and Go-Ahead Nordic subsets,
plus German long-distance rail. It does not prove complete national coverage or
through journeys. The Swedish key/downloader is already supported, but no Swedish
download is needed now. All expansion manifests below are opt-in. Adding files
to the repository does not change the running import.

| Area | Preferred source / access | Project readiness and limitations |
| --- | --- | --- |
| Denmark | [Rejseplan Labs access application](https://labs.rejseplan.dk/hc/da/articles/21553113674909-Adgang-til-data-fra-Labs); request **GTFS Schedule/Static** | Apply through their contact form; approved users receive account/service access. Not necessarily a simple API key. A local-archive manifest is supplied. Check the approved reuse/storage terms and cross-border coverage. |
| Italy | [Italian NAP: Trenitalia NeTEx L1](https://www.cciss.it/nap/mmtis/public/catalog/Dataset/1077621) | Official planned-service source, but our preparation accepts GTFS, not this Italian NeTEx profile. Licence/access review and a validated conversion/import path remain work; there is no Italian import yet. |
| Austria | [ÖBB GTFS download](https://data.oebb.at/de/datensaetze~soll-fahrplan-gtfs~) | User must accept publisher terms before downloading. Local-archive manifest supplied. Named domestic operators only; not evidence of Munich–Milan or Nightjet through coverage. |
| Switzerland | [Official GTFS cookbook](https://opentransportdata.swiss/en/cookbook/timetable-cookbook/gtfs/) and [usage terms](https://opentransportdata.swiss/en/terms-of-use/) | File downloads do not need an API account. Local-archive manifest supplied so the administrator explicitly chooses the timetable year. National mixed-mode feeds may be large; preparation retains its size limits. |
| France | [SNCF Voyageurs national GTFS](https://transport.data.gouv.fr/datasets/horaires-sncf) | Public URL wired in `motis/feeds.france.json`; no key. Optional explicit download, with 24-hour checksum-validated cache reuse. ODbL plus additional conditions, not CC BY. Not every operator; prefer regional authority data where appropriate. |
| Greece, Croatia, Slovenia and other branches | Operator/national-access-point feeds still need individual review | No complete rail coverage established here. Do not treat the schematic map or an empty MOTIS result as proof of service or impossibility. Commercial providers below are candidates, not verified coverage for these branches. |

Published calendars are a separate limitation from geography. For example,
[Switzerland's 2027 dataset](https://data.opentransportdata.swiss/dataset/timetable-2027-gtfs2020)
lists 13 December 2026–11 December 2027, while the French publisher describes a
rolling 151-day horizon. The German free feed has a much shorter horizon. Do not
extend calendars to fabricate next year's services. A commercial key cannot make
unpublished departures available either.

## API accounts worth asking about

### 1. All Aboard — first rail API enquiry, not a required signup

[Create/request access](https://allaboard.eu/join), then follow their
[API setup](https://docs.allaboard.eu/intro/getting-started). Their API includes
journey search as well as offers: it is not only an extra-fare service. Their
[operator directory](https://allaboard.eu/operators) lists Denmark/DSB,
Italy/Trenitalia and Austria/ÖBB, among others. These listings do not prove that
our exact routes, dates, passholder products or all regional services are exposed.

Before committing, ask whether a **private, low-volume honeymoon planner** can
use journey search without selling tickets; what it costs; which journey-search
scopes are needed; and whether persisted timetable snapshots are permitted.
Their fair-use documentation forbids systematic data collection and speculative
offer probing. Do not use it to build a bulk MOTIS database. The adapter is disabled by default. `ALLABOARD_API_KEY` and explicit
`ALLABOARD_ENABLED=true` enable on-demand locations/journeys only; see the setup guide.

### 2. Ferryhopper — southern endpoint and island sailings

Contact [Ferryhopper's FerryhAPI team](https://partners.ferryhopper.com/ferryhapi) for API
partner access. Ask specifically about dated Italy–Greece crossings, Greek island
connections and Croatian island sailings, personal-project eligibility, fees,
limits and permitted caching. The public product advertises ferry inventory,
but exact routes, seasons and entitlement must be confirmed. Their FAQ explicitly
allows schedule-only use without issuing tickets, subject to partner terms. This would be a
separate ferry-search integration, not our rail-only MOTIS query or proof of
Interrail discounts. No ferry provider calls or purchases are implemented; the actual partner
contract is needed before implementing authenticated ferry requests.

### 3. Trainline Partner Solutions — alternative if rail access is unsuitable

Their [Global API](https://tps.thetrainline.com/our-products/global-api/) is aimed
at travel sellers across the UK and Europe. Ask about personal-project access,
timetable-only search, named Italian/Austrian operators, caching and fees before
registering. Treat this as commercial partner onboarding, not a guaranteed free
developer key. There is little reason to obtain both rail providers initially.

[Direct Trenitalia partnership](https://www.trenitalia.com/en/information/join-online-and-become-a-trenitalia-partner.html)
is another commercial route, but targets resellers/OTAs and entails a business
agreement. It is not the first choice for this private app. No suitable public
Hellenic Train journey API was established in this review; retain official
operator links until an authorized source is identified.

Suggested enquiry text:

> I am building a private, non-commercial Interrail honeymoon planner for two
> travellers. I need on-demand dated journeys/timetables, initially without ticket
> sales. Do you permit this use, which named operators/cross-border routes do you
> cover, what are the limits and fees, and may I persist timestamped search results
> for later review? For rail, are passholder reservations a separate product?

Keep credentials server-side and out of chat, Git, manifests and browser storage.
All Aboard uses server-side secret configuration and explicit searches. External
results are not persisted. FerryhAPI and Danish authenticated-download settings
remain undefined until their approved technical contracts are available.

## Using the prepared expansion manifests

The French public feed can be added explicitly:

```sh
python3 motis/prepare.py --extra-manifest motis/feeds.france.json
```

For the other templates, obtain the authorized GTFS ZIP yourself and save it as
`motis/downloads/denmark.zip`, `austria.zip` or `switzerland.zip`. Choose the Swiss
timetable year that covers the research dates. Do not rename NeTEx XML as a ZIP.
Then repeat `--extra-manifest` for **each archive you actually have**:

```sh
python3 motis/prepare.py \
  --extra-manifest motis/feeds.france.json \
  --extra-manifest motis/feeds.denmark.example.json \
  --extra-manifest motis/feeds.austria.example.json \
  --extra-manifest motis/feeds.switzerland.example.json
```

This is a full replacement dataset list (the four defaults plus the selected
expansions), not an append operation. Include any other previously imported
optional feeds explicitly or they will no longer be configured. Missing archives
or failed audits preserve the previous prepared configuration. Local-file feeds
make no authenticated download calls. Downloaded archives remain unchanged;
source terms, attribution, checksums and rail-calendar/city summaries are recorded.

### Verification performed here

The optional French archive was downloaded and audited in an isolated temporary
directory on 16 October 2026: 60,057 trips, including 56,571 rail trips and 4,772
rail stops; the rail-calendar envelope was 16 October 2026–31 March 2027. These
are snapshot facts, not a future guarantee or continuous service throughout that
envelope. The pinned MOTIS v2.11.3 binary imported it successfully. Through the
real backend adapter, searches for **20 October 2026** returned three scheduled
options each for Paris–Lyon, Lyon–Marseille and Paris–Milan. This does not establish
Italian domestic coverage or any other cross-border corridor. The user's existing
MOTIS work directory and running import were not changed. Docker was not tested.

The four expansion manifest schemas, merging with defaults, retained provenance,
non-extended calendars and safe failure on a missing optional archive are covered
by synthetic, network-free tests. The focused MOTIS adapter/preparation suite
passed 37 tests. Swiss, Austrian and Danish archives have not been imported here.

Back up the working MOTIS data and follow the stop → prepare → import → restart
sequence in [MOTIS setup](motis.md). A rebuild alone does not import new feeds.
Verify each dated corridor after import, particularly Copenhagen–Hamburg,
Munich–Innsbruck–Verona/Milan and Milan–Bari. Nearby stations and calendar overlap
are useful diagnostics, not proof of a working international interchange.
