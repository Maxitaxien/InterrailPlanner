# Data sources and confidence

## Self-hosted timetable inputs

The [current expansion machinery and credentials](timetable-integrations.md)
cover optional national feeds and a separate All Aboard research adapter.
All Aboard results are not loaded into MOTIS or persisted as itinerary snapshots.
FerryhAPI remains pending its actual partner technical contract.


The [coverage/access assessment](timetable-coverage.md) documents optional France,
Switzerland, Austria and Denmark feed manifests and the remaining API candidates.
Optional manifests are not evidence of an imported or journey-tested network.

The default MOTIS inputs now combine [GTFS.de German long-distance
rail](https://www.gtfs.de/en/feeds/de_fv/) (CC BY 4.0) with [Entur's Norwegian
timetable exports](https://developer.entur.no/open-data/timetable) for Vy Rail,
SJ Nord and Go-Ahead Nordic ([NLOD 2.0](https://data.norge.no/nlod/en/2.0)).
Downloaded archives remain unchanged; provenance records retain checksums and
original download times, while this app derives rail-calendar and nearby-city
summaries. These datasets do not constitute complete European coverage or
Interrail passholder booking inventory. See [MOTIS setup](motis.md) for the dated
smoke checks and optional authorized Swedish feed. All prepared source metadata
is distinguished from the running server's actual import version.

## Italian ferry gateways and western Greek islands

Eight further places are now modeled: **Brindisi, Ancona, Salerno and Piombino**
as rail-connected coastal stays/gateways, and **Elba/Portoferraio, Paxos/Gaios,
Ithaca/Vathy and Meganisi/Spartochori** as island final stays. The current catalogue
has **146 destinations, 25 island endpoint options, 466 directed illustrative rail
edges and 36 one-way ferry/ground research corridors**. All four Italian gateways
can be selected as the common starting point in endpoint comparison.

| Gateway / stay | Modeled route to research | Official route / access reference |
| --- | --- | --- |
| Brindisi | Rail from Bari or Lecce, separate transfer to Costa Morena, then Igoumenitsa or seasonal Corfu ferry | [Trenitalia Brindisi Air&Port Link](https://www.trenitalia.com/it/regionale/collegamenti-regionale/brindisi-air-port-link.html), [Grimaldi Igoumenitsa](https://www.grimaldi-lines.com/en/route/brindisi-igoumenitsa/), [seasonal Corfu](https://www.grimaldi-lines.com/en/route/brindisi-corfu/) |
| Ancona | Adriatic rail corridor from Bologna/toward Bari, then separate ferry to Igoumenitsa or Patras | [Grimaldi Ancona–Igoumenitsa](https://www.grimaldi-lines.com/en/route/ancona-igoumenitsa/), [Superfast ports](https://www.superfast.com/en-gb/ports-destinations) |
| Salerno | Rail from Naples, then assigned commercial-port terminal and Palermo ferry | [Grimaldi Salerno–Palermo](https://www.grimaldi-lines.com/en/route/salerno-palermo/) |
| Piombino / Elba | Rail approach from Florence with changes; verify final train/bus/road access to Piombino Marittima, then Portoferraio ferry | [Trenitalia Elba Link](https://www.trenitalia.com/it/regionale/collegamenti-regionale/elba-link.html), [Moby / Toremar route](https://www.mobylines.com/routes/ferries-elba/piombino-portoferraio-piombino/) |
| Paxos / Gaios | Italy–Corfu crossing, then separate Corfu–Paxos ferry | [Kerkyra Lines Corfu–Paxos](https://kerkyralines.com/route/kerkyra-paxoi/), [Visit Greece Paxi](https://www.visitgreece.gr/en/islands/cyclades/paxi) |
| Ithaca / Vathy | Italy–Patras, then Patras–Sami–Pisaetos service and separate road transfer to Vathy | [Levante Patras–Sami–Ithaca](https://www.levanteferries.com/en/routes/patra-sami-ithaki/) |
| Meganisi / Spartochori | Italy–Igoumenitsa, road to Lefkada, onward road to Nydri, ferry to Spilia, local access to Spartochori | [West Ferry](https://westferry.gr/), [Visit Greece Ionian islands](https://www.visitgreece.gr/en/mainland/ionian-islands) |

Brindisi is a ferry gateway and a waterfront stay, not a guarantee of a beach
holiday beside the international terminal. Costa Morena is separate from the old
town and railway station. Ancona and Salerno also require the correct check-in
location/berth; Piombino town station and Piombino Marittima are distinct access
points. The app's rail approach does not assert that every train reaches the quay
or that a final bus is covered by Interrail. The detailed transfer plans retain
those port-access allowances outside the rail corridor.

The new western Greek stays supplement existing Corfu, Lefkada, Kefalonia and
Zakynthos. They need extra connections: there is **no direct Italy–Paxos,
Italy–Ithaca or Italy–Meganisi sailing asserted by this model**. Sami on the Ithaca
service is a port call, not an invented extra change of ferry; Pisaetos-to-Vathy
road access is explicit. Meganisi's Lefkada Town-to-Nydri transfer and
Spilia-to-Spartochori local access are explicit, and are included in its stated
time budget exactly once. Brindisi–Corfu and the Paxos leg are flagged potentially
seasonal, with their dated operation still to check. Antipaxos is mentioned only
as a separately researched day-boat excursion from Paxos, not a modeled endpoint.

Return-airport candidates are mainland Pisa for Elba, Corfu for Paxos, Kefalonia
for Ithaca and Aktion for Meganisi. Each island candidate explicitly includes a
separate return ferry and local/road access; no island is assigned a fictional
airport or direct flight to Bergen. All durations are app planning allowances,
not extracted sailings or protected connections. Operator terms, dated services,
foot-passenger access, check-in, accommodation and flight availability remain
unverified.

Rebuild the backend and rerun `python -m app.scripts.seed_data` in its environment.
The merge is idempotent and preserves saved trips; no migration/API key is
needed. Existing trips need an explicit edit/recalculation to use new corridors.
MOTIS city diagnostics include these points on the next explicit preparation,
without downloading or importing anything automatically.

Validation: 227 Python tests passed with two PostgreSQL tests skipped, plus 12
frontend tests and seven focused desktop/mobile browser scenarios. All added
stays generated sample routes, and seed/import merges remained idempotent.
No live sailing or flight availability was queried.

## Coastal expansion: 17 October 2026

`coastal_expansion.json` adds **14 final stays** and individual city-panel highlights.
All are available in their country endpoint selector and on the map. Coastal
pins offer **Make coastal final destination**; island pins keep their existing
final-destination action. Four new island stays also appear in the island filter.
The seed importer merges these additions idempotently and preserves saved trips;
rebuild the backend and rerun `python -m app.scripts.seed_data`. No migration or
new API key is required. MOTIS preparation now audits nearby rail stops for the
expanded city catalog when explicitly rerun; this does not add timetable feeds.

| Area | New final stays | Modeled access to research |
| --- | --- | --- |
| Greek Ionian mainland | Igoumenitsa, Sivota (Epirus), Parga, Preveza | Bari–Igoumenitsa ferry, then separately arranged road transfers for the smaller towns |
| Western Greece / Ionian islands | Patras, Kefalonia/Sami, Zakynthos Town, Lefkada Town | Bari–Patras; onward Patras–Sami ferry for Kefalonia; road to Kyllini plus a second ferry for Zakynthos; Igoumenitsa then road over the mainland bridge for Lefkada |
| Puglia | Monopoli, Polignano a Mare | Illustrative regional rail corridors from Bari |
| Campania / Calabria | Sorrento, Tropea | EAV local rail from Naples to Sorrento; rail corridor with changes to Tropea |
| Sicily / Aeolian islands | Cefalù, Lipari | Existing Naples–Palermo ferry followed by Palermo–Cefalù rail; Siremar Naples–Lipari ferry |

These routes prioritize western Greece without the detour through Athens.
Corfu remains an existing option from Bari, with its seasonal caveat. Parga and
Sivota have relatively short road-transfer allowances; this is a planning choice,
not a guarantee of convenient scheduled public transport. No direct Italy–Parga,
Italy–Lefkada or Italy–Zakynthos ferry is asserted. Lefkada's final segment is
explicitly road travel over its bridge and the transfer dialog labels it as
**ground transfer**, not a sailing. Airport hints identify island airports or
nearby mainland airports, not verified flights to Bergen; Lefkada has no silently
assigned island airport.

Route references: [Superfast ports](https://www.superfast.com/en-gb/ports-destinations),
[Levante routes](https://www.levanteferries.com/en/routes/),
[Kyllini–Zakynthos](https://www.levanteferries.com/en/routes/kyllini-zakynthos/),
[Siremar Aeolian routes](https://www.carontetourist.it/it/isole-eolie),
[EAV](https://www.eavsrl.it/), and [Cefalù regional rail](https://www.trenitalia.com/en/connections/cefalu-line.html).
Destination references: [Parga](https://www.visitgreece.gr/en/islands/Epiro/Parga),
[Epirus](https://www.visitgreece.gr/en/islands/Epirus),
[Lefkada and its bridge](https://www.visitgreece.gr/en/islands/ionian/lefkada),
[Puglia](https://www.italia.it/en/puglia),
[Tropea / Costa degli Dei](https://www.italia.it/it/calabria/costa-degli-dei),
and [Cefalù](https://www.visitsicily.info/en/cefalu/).

All times, buffers, changes and transit-night allowances remain illustrative;
references establish routes to investigate, not dated schedules. Verify operating
days, cabins, port/station transfers and road transport independently. Road and
ferry legs consume no **rail** pass days in this model; the separate Palermo–Cefalù
rail segment does. EAV has a separate operator link and a warning that pass
acceptance is not assumed. No real-time availability, flights, prices or pass
benefits were verified.

## Island expansion

`island_endpoints.json` adds 17 representative island ports/final stays, originally taking
the catalog to 124 destinations. That increment had 444 rail seed edges and 18
one-way endpoint research connections; current totals after the coastal expansion
below are **146 destinations, 466 rail edges and 36 endpoint-transfer corridors**. Rerun the seed
import after rebuilding. These are island final-stay options, not newly invented
railway stations or a complete island-hopping timetable.

| Region | Island stays | Operator route reference |
| --- | --- | --- |
| Greece | Corfu; Syros, Paros, Naxos, Santorini, Crete/Heraklion, Milos via Athens/Piraeus | [Superfast](https://www.superfast.com/en-gb/ports-destinations), [Blue Star port/route guide](https://www.bluestarferries.com/en-gb/piraeus-port-map) |
| Italy | Sicily/Palermo, Sardinia/Porto Torres, Capri, Ischia, Procida | [Tirrenia Sicily](https://en.tirrenia.it/ferry-sicily/), [Sardinia](https://en.tirrenia.it/ferry-sardinia/), [Caremar](https://easy.caremar.it/en/rates/) |
| Croatia | Hvar, Vis, Brač/Supetar, Korčula/Vela Luka from Split | [Jadrolinija local route index](https://www.jadrolinija.hr/hr/putovanja) |
| Corsica | Bastia from Genoa | [Moby Genoa–Bastia](https://www.mobylines.com/routes/ferries-corsica/genoa-bastia-genoa/) |

Reference pages establish a corridor to research, **not availability on honeymoon
dates**. Every crossing duration, port/check-in allowance and overnight count in
our catalog is illustrative, not extracted from a timetable. Corfu from Bari and
Genoa–Bastia are flagged potentially seasonal. All operators can change service;
check dated sailings and disruptions. In particular, no assumption is made about
current Italy–Croatia international ferries: the modeled Croatian island legs
start at Split after the estimated rail journey.

The map points represent named ports/localities, not every part of an island.
Airport codes are research hints, not verified flights to Bergen. Islands without
a mapped airport require separate return-airport/ferry research; no mainland
airport is silently presented as being on the island. Local/port access, cabin or
seat inventory, prices and pass benefits are unverified. Ferries are not counted
as ordinary rail-pass days, and any ferry-specific pass requirements remain unknown.

`backend/data/destinations.json`, `rail_connections.json` and `attractions.json` provide the original 45 cities, 128 directed illustrative corridors and 45 city/attraction suggestions. `map_expansion.json` adds 62 cities and 158 bidirectional schematic corridors, for 107 cities and 444 directed edges. Coverage now includes Great Britain, Luxembourg, Slovakia and Romania, plus more international and domestic connections in the existing countries. The catalog includes major cities and useful rail interchanges; it is not a strict population ranking or the complete Interrail network.

The expansion references the [official Interrail network overview](https://www.interrail.eu/en/plan-your-trip/interrail-railway-map). Durations and transfer counts are planning fixtures, not extracted live services or operator-verified timetables. Some corridors represent journeys requiring changes. The seed importer merges additions idempotently; existing installations must rerun it after rebuilding the backend.

Additional references are recorded in `map_expansion.json`: Interrail's published railway map and its Great Britain, Slovakia and Romania network guides. The map UI links to the full official network. Greece has no modeled international train connection, but Athens is reachable as an endpoint via rail to Bari, ferry to Patras, and separately checked onward ground travel.

Every rail connection stores source, estimate quality, nullable review time, service type, night-train flag and reservation warning. Country transitions are computed from the endpoints. Both directions are explicit; symmetric times and zero transfer defaults are approximations, not verified direct services. API route legs include the underlying connection provenance.

`app/services/endpoint_transfers.py` supplies the separate one-way endpoint
research corridor without changing the rail database or requiring a seed update.
The [Superfast operator reference](https://www.superfast.com/en-gb/special-offers/sail-rail)
lists Italy–Greece routes including Bari–Patras. The **26-hour total** (18-hour
crossing allowance, four-hour onward-ground allowance and four-hour buffer) is an
illustrative fixture, not a published sailing or transfer timetable. One overnight
allowance is included. Research onward transport with
[Hellenic Train](https://www.hellenictrain.gr/en) and current local options;
no direct Patras–Athens train is asserted. Cabin availability, fares, pass benefits
and service dates are unknown. Blue dashed map lines distinguish this mixed
endpoint connection from rail. This is not unrestricted multimodal routing.

MapLibre uses OpenStreetMap background tiles with attribution. The browser requests those tiles from `tile.openstreetmap.org`, which receives its IP address and requested map area. The rail network is drawn as schematic edges; the highlighted itinerary follows its transit nodes. Lines are not railway geometry. Tile failures leave cities and routes usable, and a keyboard city picker supports browsers without WebGL. Timetable lookup, pass rules, airport transfers and authorized live offers remain separate concerns.

Official rail reference sources, fetched only when requested:

- [Interrail reservations](https://www.interrail.com/en/plan-your-trip/reservations)
- [Interrail trains by country](https://www.interrail.com/en/plan-your-trip/tips-and-tricks/trains-europe/trains-country)

Retrieved source excerpts are untrusted text, shown without HTML execution, not interpreted as definitive pass rules. Current sources may refuse automated retrieval. Fixed source URLs and no redirects prevent arbitrary URL fetching. Cache expiry is 24 hours; failures do not present expired content as current.

Ollama adapter protocol references: [structured outputs](https://docs.ollama.com/capabilities/structured-outputs) and [model listing](https://docs.ollama.com/api/tags). AI output is schema-validated and limited to curated IDs/tags. No API keys, scraped booking prices or verified live transport facts are included in the seed.
