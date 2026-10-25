"""Explicit research corridors, not timetable services or pass entitlements."""

ENDPOINT_TRANSFERS = [{
    "id": "bari-athens-ferry-transfer", "origin_id": "bari", "destination_id": "athens",
    "mode": "ferry_transfer", "estimated_minutes": 1560, "overnight_nights": 1,
    "transfers": 2, "service_type": "Ferry via Patras + onward ground transfer",
    "night_train": False, "estimate_quality": "illustrative", "reviewed_at": None,
    "source": "Superfast Italy–Greece route reference; duration is an illustrative planning allowance, not a sailing time.",
    "source_url": "https://www.superfast.com/en-gb/special-offers/sail-rail",
    "booking_url": "https://www.superfast.com/en-gb",
    "onward_url": "https://www.hellenictrain.gr/en",
    "reservation_warning": "Book ferry and onward travel separately. Verify sailing dates, cabin/seat, port transfers, onward bus/train services and all fares. Interrail inclusion or discounts are not verified.",
    "components": [
        {"mode": "ferry", "origin": "Bari", "destination": "Patras", "estimated_minutes": 1080},
        {"mode": "ground_transfer", "origin": "Patras", "destination": "Athens", "estimated_minutes": 240},
        {"mode": "buffer", "description": "Illustrative check-in and connection allowance", "estimated_minutes": 240},
    ],
}]


def island_corridor(origin, destination, minutes, operator, source, booking, departure, arrival, crossing, overnight=0, seasonal=False):
    """Durations are research allowances, not extracted sailing times."""
    return {
        "id": f"{origin}-{destination}-ferry-transfer", "origin_id": origin, "destination_id": destination,
        "mode": "ferry_transfer", "estimated_minutes": minutes, "overnight_nights": overnight,
        "transfers": 1, "service_type": f"{operator} ferry + port transfers",
        "night_train": False, "estimate_quality": "illustrative", "reviewed_at": None,
        "source": f"{operator} route reference; all durations are illustrative planning allowances, not sailings.",
        "source_url": source, "booking_url": booking, "operator": operator,
        "seasonal": seasonal,
        "reservation_warning": "Research connection only. Confirm operating dates, seasonal schedules, check-in, cabins/seats, local transfers and return airport access. Fares and Interrail benefits are unknown." + (" This route may be seasonal; do not assume a daily or year-round sailing." if seasonal else ""),
        "components": [
            {"mode": "ferry", "origin": departure, "destination": arrival, "estimated_minutes": crossing},
            {"mode": "buffer", "description": "Illustrative port access, check-in and onward local-transfer allowance", "estimated_minutes": minutes-crossing},
        ],
    }


ENDPOINT_TRANSFERS += [
    island_corridor("bari", "corfu", 840, "Superfast", "https://www.superfast.com/en-gb/ports-destinations", "https://www.superfast.com/en-gb", "Bari", "Corfu", 660, 1, True),
    island_corridor("naples", "sicily", 900, "Tirrenia", "https://en.tirrenia.it/ferry-sicily/", "https://en.tirrenia.it/", "Naples", "Palermo", 660, 1),
    island_corridor("genoa", "sardinia", 960, "Tirrenia", "https://en.tirrenia.it/ferry-sardinia/", "https://en.tirrenia.it/", "Genoa", "Porto Torres", 720, 1),
    island_corridor("genoa", "corsica", 720, "Moby", "https://www.mobylines.com/routes/ferries-corsica/genoa-bastia-genoa/", "https://www.mobylines.com/", "Genoa", "Bastia", 480, 0, True),
]
for island, crossing in [("capri", 90), ("ischia", 120), ("procida", 90)]:
    ENDPOINT_TRANSFERS.append(island_corridor("naples", island, crossing+120, "Caremar", "https://easy.caremar.it/en/rates/", "https://shop.caremar.it/en/", "Naples", island.title(), crossing))
for island, crossing in [("syros", 300), ("paros", 300), ("naxos", 360), ("santorini", 540), ("crete", 660), ("milos", 420)]:
    ENDPOINT_TRANSFERS.append(island_corridor("athens", island, crossing+180, "Blue Star / Hellenic Seaways", "https://www.bluestarferries.com/en-gb/piraeus-port-map", "https://www.bluestarferries.com/en-gb", "Piraeus (Athens)", "Heraklion" if island == "crete" else island.title(), crossing, 1 if island == "crete" else 0))
for island, arrival, crossing in [("hvar", "Hvar", 120), ("vis", "Vis", 180), ("brac", "Supetar (Brač)", 90), ("korcula", "Vela Luka (Korčula)", 240)]:
    ENDPOINT_TRANSFERS.append(island_corridor("split", island, crossing+120, "Jadrolinija", "https://www.jadrolinija.hr/hr/putovanja", "https://shop.jadrolinija.hr/shop/?lang=en", "Split", arrival, crossing))


def coastal_road_transfer(origin, destination, minutes, departure, arrival):
    """Separately arranged road transfer after a ferry, not a scheduled bus."""
    return {
        "id": f"{origin}-{destination}-ground-transfer", "origin_id": origin, "destination_id": destination,
        "mode": "ferry_transfer", "estimated_minutes": minutes, "overnight_nights": 0,
        "transfers": 1, "service_type": "Onward road transfer after Italy ferry",
        "night_train": False, "estimate_quality": "illustrative", "reviewed_at": None,
        "source": "Illustrative private/local road-transfer allowance, not a published bus or ferry service.",
        "source_url": "https://www.visitgreece.gr/en/islands/ionian/lefkada" if destination == "lefkada" else "https://www.visitgreece.gr/en/islands/Epirus",
        "onward_url": "https://www.visitgreece.gr/",
        "reservation_warning": "Arrange and budget this road transfer separately; no direct scheduled bus is asserted. Check arrival/check-in times and local transport. No ferry sails on this segment." + (" Lefkada is reached over its mainland bridge." if destination == "lefkada" else ""),
        "components": [{"mode": "ground_transfer", "origin": departure, "destination": arrival, "estimated_minutes": minutes}],
    }


ENDPOINT_TRANSFERS += [
    island_corridor("bari", "igoumenitsa", 780, "Superfast", "https://www.superfast.com/en-gb/ports-destinations", "https://www.superfast.com/en-gb", "Bari", "Igoumenitsa", 600, 1),
    island_corridor("bari", "patras", 1320, "Superfast", "https://www.superfast.com/en-gb/ports-destinations", "https://www.superfast.com/en-gb", "Bari", "Patras", 1080, 1),
    island_corridor("patras", "kefalonia", 420, "Levante Ferries", "https://www.levanteferries.com/en/routes/", "https://www.levanteferries.com/en/", "Patras", "Sami (Kefalonia)", 240),
    island_corridor("naples", "lipari", 1140, "Siremar", "https://www.carontetourist.it/it/isole-eolie", "https://www.carontetourist.it/it", "Naples", "Lipari", 960, 1),
]
for town, minutes, arrival in [("parga", 90, "Parga"), ("sivota", 60, "Sivota (Epirus)"), ("preveza", 120, "Preveza"), ("lefkada", 180, "Lefkada Town via mainland bridge")]:
    ENDPOINT_TRANSFERS.append(coastal_road_transfer("igoumenitsa", town, minutes, "Igoumenitsa", arrival))
ENDPOINT_TRANSFERS.append({
    "id": "patras-zakynthos-ferry-transfer", "origin_id": "patras", "destination_id": "zakynthos",
    "mode": "ferry_transfer", "estimated_minutes": 420, "overnight_nights": 0, "transfers": 2,
    "service_type": "Road transfer to Kyllini + Levante ferry to Zakynthos",
    "night_train": False, "estimate_quality": "illustrative", "reviewed_at": None,
    "source": "Levante Kyllini–Zakynthos route reference plus separately arranged ground transfer; illustrative allowances only.",
    "source_url": "https://www.levanteferries.com/en/routes/kyllini-zakynthos/",
    "booking_url": "https://www.levanteferries.com/en/",
    "reservation_warning": "Not a direct ferry from Italy or Patras to Zakynthos. Arrange Patras–Kyllini road transport separately, then verify and book the island ferry. Check dates, connection margins and all fares; pass benefits are unknown.",
    "components": [
        {"mode": "ground_transfer", "origin": "Patras", "destination": "Kyllini", "estimated_minutes": 120},
        {"mode": "ferry", "origin": "Kyllini", "destination": "Zakynthos Town", "estimated_minutes": 90},
        {"mode": "buffer", "description": "Illustrative connection, check-in and local-transfer allowance", "estimated_minutes": 210},
    ],
})


# Additional rail-to-ferry gateways and western Ionian final stays. The route
# references establish research corridors, not dated departures or through tickets.
ENDPOINT_TRANSFERS += [
    island_corridor("brindisi", "igoumenitsa", 720, "Grimaldi Lines", "https://www.grimaldi-lines.com/en/route/brindisi-igoumenitsa/", "https://www.grimaldi-lines.com/en/", "Brindisi · Costa Morena", "Igoumenitsa", 480, 1),
    island_corridor("brindisi", "corfu", 660, "Grimaldi Lines", "https://www.grimaldi-lines.com/en/route/brindisi-corfu/", "https://www.grimaldi-lines.com/en/", "Brindisi · Costa Morena", "Corfu", 420, 1, True),
    island_corridor("ancona", "igoumenitsa", 1320, "Grimaldi / Minoan", "https://www.grimaldi-lines.com/en/route/ancona-igoumenitsa/", "https://www.grimaldi-lines.com/en/", "Ancona", "Igoumenitsa", 1080, 1),
    island_corridor("ancona", "patras", 1680, "Superfast", "https://www.superfast.com/en-gb/ports-destinations", "https://www.superfast.com/en-gb", "Ancona", "Patras", 1440, 1),
    island_corridor("salerno", "sicily", 840, "Grimaldi Lines", "https://www.grimaldi-lines.com/en/route/salerno-palermo/", "https://www.grimaldi-lines.com/en/", "Salerno · assigned commercial-port terminal", "Palermo", 600, 1),
    island_corridor("piombino", "elba", 180, "Moby / Toremar", "https://www.mobylines.com/routes/ferries-elba/piombino-portoferraio-piombino/", "https://www.mobylines.com/", "Piombino Marittima", "Portoferraio (Elba)", 60),
    island_corridor("corfu", "paxos", 240, "Kerkyra Lines", "https://kerkyralines.com/route/kerkyra-paxoi/", "https://kerkyralines.com/", "Corfu · confirm departure terminal", "Gaios (Paxos)", 120, 0, True),
]


def onward_island_corridor(origin, destination, minutes, operator, source, departure, arrival, crossing, before=None, after=None):
    """Keep outlying departure/arrival ports distinct from the named island stay."""
    edge = island_corridor(origin, destination, minutes, operator, source, source, departure, arrival, crossing)
    ground = []
    if before:
        ground.append({"mode": "ground_transfer", "origin": before[0], "destination": before[1], "estimated_minutes": before[2]})
    ferry = edge['components'][0]
    if after:
        ground_after = [{"mode": "ground_transfer", "origin": after[0], "destination": after[1], "estimated_minutes": after[2]}]
    else:
        ground_after = []
    buffer = minutes - crossing - sum(part['estimated_minutes'] for part in ground + ground_after)
    edge['components'] = ground + [ferry] + ground_after + [{"mode": "buffer", "description": "Illustrative port, check-in and local access allowance", "estimated_minutes": buffer}]
    edge['reservation_warning'] += " Port calls and local road transfers are separate from the named stay; check departure days and arrange road transport independently."
    return edge


ENDPOINT_TRANSFERS += [
    onward_island_corridor("patras", "ithaca", 525, "Levante Ferries", "https://www.levanteferries.com/en/routes/patra-sami-ithaki/", "Patras (via Sami port call)", "Pisaetos (Ithaca)", 300, after=("Pisaetos", "Vathy (Ithaca)", 45)),
    onward_island_corridor("lefkada", "meganisi", 240, "West Ferry", "https://westferry.gr/", "Nydri (Lefkada)", "Spilia (Meganisi)", 40, before=("Lefkada Town", "Nydri", 60), after=("Spilia", "Spartochori", 20)),
]


def endpoint_transfers(destinations):
    from app.services.connection_plans import connection_plan
    return [{**edge, "connection_plan": connection_plan(edge)} for edge in ENDPOINT_TRANSFERS
            if edge["origin_id"] in destinations and edge["destination_id"] in destinations]
