# Compare final stays and plan connections

The planner now compares final destinations and exposes the access time hidden
inside the existing ferry/ground allowances. Both features use local catalogue
data. They need no provider keys, feed download, migration or new seed import if
the coastal catalogue is already loaded. Rebuild both application images using
your usual Compose files and overrides.

## Choose a final destination

Click **Compare final destinations** beside the endpoint selector. Choose a
common Italian starting point and up to six stays, then click **Compare selected
stays**. The initial shortlist includes Corfu, Kefalonia, Crete and your current
endpoint when available. Opening the dialog makes no comparison/provider call.

The desktop comparison table, shown as complete destination cards on mobile, shows:

- Estimated travel from the chosen Italian city, excluding earlier holiday legs.
- Ferry crossings, separate ground legs and potentially seasonal sailings.
- Lower-bound transit-night allowances, with no invented arrival clock time.
- Candidate return airports and any extra ferry/ground access required.

Expand a destination for its modeled city/port route, the time breakdown and
individual connection steps. Sort by estimated time or ferry count. **Choose**
changes the draft endpoint before generation, or explicitly applies a normal
revision-checked endpoint edit to an existing itinerary. Locked stays, required
stops, pass limits and calendar constraints still apply. A failed change leaves
the comparison open and preserves the saved route. Comparing alone writes
nothing and does not apply timetable snapshots or change trip preferences.

The backend uses the shortest modeled graph path from the selected origin; this
is not a query to MOTIS or a commercial provider. Changing the starting point or
shortlist clears stale results. Unsupported pairs return an explicitly
unselectable `no_modeled_route`, not proof that real transport is impossible.

## What the numbers mean

Every ferry corridor now exposes a `connection_plan` alongside its original
components. It allocates the existing buffer into port access, ferry check-in /
boarding, extra connection margin, disembarkation and destination access, keeping
explicit road legs before or after the crossing in the correct order. The steps
sum to the original corridor budget exactly once: no minutes are silently added
or counted twice. Existing itinerary dates and transit nights are not changed
just by opening or reopening the planner.

Named approaches include Bari Centrale to its assigned terminal, Napoli Centrale
to its assigned terminal, Genova Piazza Principe to its assigned terminal, Athens
city/rail arrival to the assigned Piraeus gate, and Split railway station to the
assigned berth. Exact docks, ticket offices and local services need checking
against the actual booking. Patras–Zakynthos explicitly places its Kyllini road
transfer before ferry boarding. Igoumenitsa–Lefkada remains ground travel over
the mainland bridge and has no sailing or ferry check-in step.

These are **app planning allowances**, not official operator deadlines. Current
buffer allocation uses up to 45 minutes for initial port access, 90 for check-in,
and 30 each for disembarkation and destination access; any remainder is an extra
boarding margin. Smaller existing buffers allocate proportionally. The original
allowance can be inadequate for a particular sailing or traveller: use the ticket
requirements and the checker overrides below. No live traffic or queue estimate
is supplied. Consult the [Superfast boarding reference](https://www.superfast.com/en-gb/check-in-boarding)
and the actual operator/ticket; no universal deadline was inferred from that page.

The comparison's travel-burden labels are transparent relative categories:
**Longer journey** means over 18 estimated hours or at least two ferries;
**Some onward travel** means over eight hours or a separate ground leg;
otherwise it is **Shorter journey**. They are not scores of destination quality or
guarantees of an easy connection. Transit-night lower bounds use the larger of
whole 24-hour blocks and the catalogued overnight allowances. Real sailing times,
waiting between services and accommodation access can require extra nights.

## Check researched times

Inside a ferry's connection details, expand **Check researched connection times**.
Enter the ferry departure and arrival dates/times in each port's local time.
Optionally supply your arrival at the named starting station/city and an onward
service's departure. Adjust station/city-to-port minutes and ferry check-in /
boarding minutes to your researched transfer and ticket. For onward travel, add
any transfer to another station or airport and that service's own check-in time.
The default onward boarding allowance is an app assumption, not an airline rule.

**Calculate connection margins** reports the latest starting-point arrival, the
estimated time ready at the named destination, and spare or missing minutes.
Italy/Greece timezone offsets are handled separately, including date changes.
Skipped and ambiguous daylight-saving times are rejected. The checker also
flags early/late port arrivals **or** early/late destination access after a long
ground transfer; it warns when the onward service needs more time or another
night. The window used for the early/late flag is before 07:00 or from 22:00 local.

`fits_allowances` means only that the entered times fit the chosen assumptions.
It does not check operating hours, a real departure, a through ticket, a protected
connection, cabins, luggage storage or accommodation check-in. `times_only` means
no incoming/onward departure was supplied to compare. Every input change clears
the old result. Checker inputs and results live only in the current component;
there is no database write, automatic query, or calendar application.

## Return-airport access

The same airport-access information appears in comparison and the trip's return
travel panel. Some catalogue airports have no established transfer time; these
remain explicitly untimed. Selected coastal/island stays have separate
illustrative access candidates, for example Capri/Ischia/Procida through Naples,
Lefkada through mainland Aktion, and Lipari through Milazzo to Catania. Return
ferry waiting, exact operating dates, airport check-in and flight availability
are not established. Consider a night near the airport when appropriate.

An inferred candidate does **not** replace a destination's stored airport or
silently start a flight search. Click **Research flights from …** to use that
candidate, or enter another three-letter airport code. Then explicitly prepare
the existing one-way flight search. No direct flight to Bergen is claimed.

## API contracts and compatibility

POST `/api/v1/travel/endpoints/compare`:

```json
{"origin_id":"bari","endpoint_ids":["corfu","kefalonia","crete"]}
```

The origin must be a rail-connected Italian catalogue city; endpoint IDs must be
unique final stays, with one to six selected. The response contains route steps,
consistent minute totals, ferry/ground counts, seasonality, airport access and
limitations for each choice. No trip ID or edit token is needed for read-only
research; applying an endpoint still uses the existing authenticated edit API.

POST `/api/v1/travel/connections/check`:

```json
{
  "connection_id":"bari-corfu-ferry-transfer",
  "arrival_at_start":"2027-06-10T20:00",
  "ferry_departure":"2027-06-10T22:00",
  "ferry_arrival":"2027-06-11T06:00",
  "onward_departure":"2027-06-11T10:00",
  "ferry_check_in_minutes":90,
  "port_access_minutes":45,
  "onward_transfer_minutes":0,
  "onward_check_in_minutes":30
}
```

Example times are synthetic, not a sailing. The backend selects the fixed
corridor, countries and timezones; clients cannot inject profiles or URLs. The
checker supports one ferry per corridor, rejects ground-only and unknown IDs,
and requires a positive elapsed crossing of at most seven days. Offset-bearing
input is rejected: use the location's local clock. Optional station arrival and
onward departure can be omitted. Override bounds are validated.

The rail-network endpoint and newly generated route connections include
`connection_plan`. Route results expose `airport_access`. Older saved routes get
derived connection/airport details during serialization without modifying saved
JSON, itinerary revisions, selected timetable snapshots or their calendar.
Existing component fields and duration budgets remain available for compatibility.

Tests cover every modelled endpoint, budget sums, station/road/check-in ordering,
Italy/Greece timezones, midnight and early/late arrivals, DST rejection, short
margins, overrides, read-only operation, old-route compatibility, explicit UI
requests, endpoint application and the mobile comparison layout. Provider access
and actual dated services remain the separate timetable-integration workstream.


Validation for this increment: the full Python run passed 223 tests with two
PostgreSQL runtime tests skipped. The 28-test focused comparison/connection suite
also covers the subsequent late-ground-arrival and onward-airport case. Frontend
unit checks passed 12 tests; production compilation/TypeScript checks passed.
All 22 browser scenarios passed against a disposable seeded SQLite backend,
including desktop/mobile comparison, explicit selection and saved-route reopening.
Browser dependencies/fonts were extracted to a temporary directory; no system
packages or application credentials were installed or changed.
