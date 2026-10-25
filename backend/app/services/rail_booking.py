"""Operator links and planning guidance, never a live offer or issued ticket."""
COMPANIES = "https://www.interrail.com/en/plan-your-trip/tips-and-tricks/trains-europe/railway-companies"
RESERVATIONS = "https://www.interrail.com/en/plan-your-trip/reservations"
TIMETABLE = "https://www.interrail.com/en/plan-your-trip/interrail-timetable"
REVIEWED = "2026-10-16"

# Places to check, not a claim that these operators run a particular departure.
OPERATORS = {
    "NO": [("Entur", "https://entur.no/"), ("Vy", "https://www.vy.no/en")],
    "SE": [("SJ", "https://www.sj.se/en")],
    "DK": [("DSB", "https://www.dsb.dk/en/")],
    "DE": [("Deutsche Bahn", "https://int.bahn.de/en")],
    "AT": [("ÖBB", "https://www.oebb.at/en/")],
    "IT": [("Trenitalia", "https://www.trenitalia.com/en.html")],
    "CH": [("SBB", "https://www.sbb.ch/en")],
    "FR": [("SNCF Connect", "https://www.sncf-connect.com/en-en/")],
    "ES": [("Renfe", "https://www.renfe.com/es/en")],
    "PT": [("CP", "https://www.cp.pt/passageiros/en")],
    "NL": [("NS International", "https://www.nsinternational.com/en")],
    "BE": [("SNCB International", "https://www.b-europe.com/EN")],
    "GB": [("National Rail", "https://www.nationalrail.co.uk/")],
    "CZ": [("České dráhy", "https://www.cd.cz/en/")],
    "SK": [("ZSSK", "https://www.zssk.sk/en/")],
    "HU": [("MÁV", "https://www.mavcsoport.hu/en")],
    "SI": [("Slovenian Railways", "https://potniski.sz.si/en/")],
    "HR": [("HŽPP", "https://www.hzpp.hr/en")],
    "PL": [("PKP Intercity", "https://www.intercity.pl/en/")],
    "GR": [("Hellenic Train", "https://www.hellenictrain.gr/en")],
    "RO": [("CFR Călători", "https://www.cfrcalatori.ro/en/")],
    "LU": [("CFL", "https://www.cfl.lu/en-gb")],
}

def booking_guide(request, destinations):
    ids = request.via or [request.origin_id, request.destination_id]
    countries = list(dict.fromkeys(destinations[city].country_code for city in ids))
    links = []
    for country in countries:
        links.extend({"label": name, "url": url, "country_code": country} for name, url in OPERATORS.get(country, []))
    if "GB" in countries and any(country in countries for country in ("FR", "BE", "NL")):
        links.insert(0, {"label": "Eurostar", "url": "https://www.eurostar.com/", "country_code": "international"})
    notes = ["Search the exact train before deciding whether a reservation is needed; a schematic corridor can include several services."]
    if request.ticket_mode == "pass":
        notes.append("Apply the Interrail pass to each traveller. A passholder reservation is different from buying another full-price ticket.")
    else:
        notes.append("Compare the total for your party, luggage and the fare's change/refund conditions before paying.")
    if "IT" in countries or "FR" in countries or "ES" in countries:
        notes.append("High-speed and regional services can have different pass and reservation rules; check the selected service in the official directory.")
    if "GB" in countries and len(countries) > 1:
        notes.append("For a Channel crossing, check Eurostar passholder availability separately from ordinary ticket availability.")
    if "IT" in countries and any(country in countries for country in ("DE", "AT")):
        notes.append("If the chosen Alpine service uses the Brenner or Tarvisio route, check supplements as well as seat reservations.")
    if "sorrento" in ids:
        links.append({"label": "EAV · Naples–Sorrento", "url": "https://www.eavsrl.it/", "country_code": "IT"})
        notes.append("The Naples–Sorrento local railway is operated by EAV. Research its separate fares and pass acceptance; Interrail inclusion is not assumed.")
    origin, destination = destinations[request.origin_id], destinations[request.destination_id]
    return {
        "status": "guidance_only", "reservation_status": "check_exact_train", "offers": [], "price": None,
        "availability_checked_at": None, "guidance_reviewed_on": REVIEWED,
        "origin": origin.name, "destination": destination.name,
        "via": [destinations[city].name for city in ids[1:-1]], "countries": countries,
        "departure_date": request.departure_date.isoformat() if request.departure_date else None,
        "adults": request.adults, "travel_class": request.travel_class, "ticket_mode": request.ticket_mode,
        "operators": links, "notes": notes,
        "reservation_url": RESERVATIONS, "timetable_url": TIMETABLE, "rules_url": COMPANIES,
        "couple_tip": "Choose two adjacent seats if available. For an overnight train, compare a private compartment for two with shared accommodation." if request.adults == 2 else "Check seats together where possible, and confirm each traveller's berth and luggage needs.",
        "notice": "Booking guidance and external links only. No departure, fare, seat availability or passholder allocation has been checked. Operator links open their planners; copy your journey details into them.",
    }
