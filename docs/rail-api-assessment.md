# Rail booking and timetable assessment

**17 October update:** an optional All Aboard location/journey research adapter is
now prepared, disabled by default, with no offers or persistent external results.
Danish and ferry access enquiries have been sent. See [current setup and exact
credentials](timetable-integrations.md). The older assessments below describe
provider suitability, not the current integration status.

**Current priority:** broader self-hosted timetable coverage, not booking or budget
integrations. See the [current coverage and account shortlist](timetable-coverage.md)
before signing up; older booking-oriented recommendations below are background.

Assessed 16 October 2026 for a private honeymoon planner starting in Oslo, travelling through Europe and finishing in the south.

## What works now

Every itinerary leg and selectable map corridor has a collapsible booking guide. It defaults to two adults and offers a travel date, passholder versus regular-ticket research, the selected pass class, operator/planner links, reservation guidance and a copyable journey summary. It includes all countries represented by the leg's transit cities. Actual dated legs use the saved stop's departure date; editing the research date does not alter the itinerary.

The guide is generated locally. It does not fetch offers, reserve seats, issue tickets, confirm a departure or identify the operating carrier for a particular train. Its response explicitly has empty offers, a null price and no availability-check timestamp. The guidance review date is separate from live verification.

## Suggested accounts

1. **Request All Aboard test access first.** Its [API documentation](https://docs.allaboard.eu/) covers journeys and prices; its [travel-card documentation](https://docs.allaboard.eu/tickets/travel-cards) describes Interrail passholder products. Follow [Getting Started](https://docs.allaboard.eu/intro/getting-started) for an account and test key. Confirm that personal-project access is permitted, and test passholder offers before enabling live access. Do not sign up for several commercial APIs before testing this option.
2. **Transitland Explorer is optional for network/timetable work.** The [REST API](https://www.transit.land/documentation/rest-api) exposes GTFS-related entities; the [trip API](https://www.transit.land/documentation/rest-api/trips) exposes service calendars. Its [plans page](https://www.transit.land/plans-pricing) offers Explorer access. Importantly for this itinerary, the [hosted transit routing documentation](https://www.transit.land/documentation/routing-platform/transit-otp/) currently lists US coverage, not European journey planning. REST feed coverage and hosted routing coverage are separate. Audit each rail feed's scope and service dates first. A schedule response is not a booking, fare or Interrail reservation.
3. **Entur's open Norwegian journey planner requires no API key.** It does require an identifying application header. See [Entur's portal](https://developer.entur.no/) and [client identification](https://developer.entur.no/terms-of-service). Its [pass-reservation OSDM service](https://developer.entur.no/docs/partner-services/osdm) is a separate authenticated partner product, not part of the public journey API.

No live provider adapter or provider-key input has been added yet. Current links work without an API account. Do not send secrets into browser storage or commit them to this repository.

## Booking coverage to validate

All Aboard's [published inventory](https://allaboard.eu/operators) includes the countries in the central Oslo-to-Italy corridor, but country-level presence does not prove inventory for a specific departure or rail pass.

| Corridor | Published operator examples | Test before relying on it |
| --- | --- | --- |
| Norway / Sweden | Vy, SJ | Cross-border journeys and passholder reservations |
| Denmark / Germany | DSB, DB | Copenhagen–Hamburg; two adjacent seats and seasonal rules |
| Austria / Italy | ÖBB, Trenitalia | Munich–Milan alternatives, actual border crossing, supplement and passholder product |
| Italy | Trenitalia | Milan–Bari; passholder versus ordinary fares and chosen travel class |
| France / Great Britain | SNCF, Eurostar | Passholder allocation, international service and reservation availability |
| Switzerland / Spain | SBB, Renfe | Exact trains, products and pass handling |
| Croatia, Slovenia, Poland, Romania, Portugal, Greece | Not established by this assessment | Ask the provider about each itinerary; retain official booking links |

The catalog has more countries than any confirmed ticketing integration. Keep timetable coverage, saleable tickets and passholder availability as separate capabilities.

## The user's other sources

The [Interrail company directory](https://www.interrail.com/en/plan-your-trip/tips-and-tricks/trains-europe/railway-companies) supplies pass/operator rules, including exclusions and service-specific exceptions. It is a public reference, not a live inventory API. The UI links to it and avoids marking an entire schematic leg as reservation-free or pass-valid.

[Interrail Planner's data-source page](https://interrail-planner.com/data-sources) is a useful index of underlying feeds rather than an API offered to this app. It describes importing timetables into a routing engine and identifies some publishers whose reuse terms are unclear. Any feed import needs its publisher's licence, attribution, freshness and cross-border coverage checked separately.

## First live integration acceptance cases

With an approved test key, query Oslo–Gothenburg, Copenhagen–Hamburg, Munich–Milan and Milan–Bari for the honeymoon's actual dates and two adults. Discover supported travel-card codes rather than inventing Interrail identifiers. Check the same passenger/pass/class data during both offer selection and booking. Keep test/live environments explicit, report missing inventory without fabricating alternatives, and request prices only when the traveller actively searches.

Start with search and offer display. Issuing tickets, charging money and handling cancellations need a separate user-confirmed booking flow. Nothing in the current UI creates a reservation or purchase.
# Updated direction: self-hosted timetables

The chosen timetable approach is now self-hosted MOTIS, not Transitland hosted
routing or All Aboard journey search. See [MOTIS setup](motis.md). All Aboard is
optional future passholder reservation pricing; defer account setup until we
validate coverage. The earlier provider assessment below remains background,
not the current implementation recommendation.

