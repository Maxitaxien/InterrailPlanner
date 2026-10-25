"""Candidate return-airport access, deliberately independent of flight availability.

All minutes below are app planning allowances, not timed public services. Codes
are candidates to research; no direct flight to Bergen is asserted.
"""
OVERRIDES = {
    'salerno': ('NAP', 'Naples', 'Separately checked rail / road transfer to Naples airport', 180, 0),
    'piombino': ('PSA', 'Pisa', 'Rail / road transfer to Pisa airport, with changes', 180, 0),
    'elba': ('PSA', 'Pisa', 'Ferry to Piombino + separately checked rail / road transfer to Pisa airport', 360, 1),
    'paxos': ('CFU', 'Corfu', 'Separate ferry to Corfu + ground transfer to Corfu airport; verify seasonal departure days', 300, 1),
    'ithaca': ('EFL', 'Kefalonia', 'Road to Pisaetos + separately checked ferry to Sami + road transfer to Kefalonia airport', 360, 1),
    'meganisi': ('PVK', 'Aktion / Preveza', 'Access to Spilia + ferry to Nydri + road transfer over the Lefkada bridge to Aktion airport', 330, 1),

    'capri': ('NAP', 'Naples', 'Ferry to Naples + ground transfer to airport', 240, 1),
    'ischia': ('NAP', 'Naples', 'Ferry to Naples + ground transfer to airport', 270, 1),
    'procida': ('NAP', 'Naples', 'Ferry to Naples + ground transfer to airport', 210, 1),
    'sardinia': ('AHO', 'Alghero', 'Porto Torres → Alghero airport by road', 90, 0),
    'lipari': ('CTA', 'Catania', 'Ferry to Milazzo + separately arranged road transfer to Catania airport', 420, 1),
    'lefkada': ('PVK', 'Aktion / Preveza', 'Road transfer over the mainland bridge to Aktion airport', 90, 0),
    'parga': ('PVK', 'Aktion / Preveza', 'Separately arranged road transfer to Aktion airport', 150, 0),
    'sivota': ('PVK', 'Aktion / Preveza', 'Separately arranged road transfer to Aktion airport', 180, 0),
    'igoumenitsa': ('PVK', 'Aktion / Preveza', 'Separately arranged road transfer to Aktion airport', 180, 0),
    'monopoli': ('BRI', 'Bari', 'Rail / road transfer to Bari airport', 120, 0),
    'polignano': ('BRI', 'Bari', 'Rail / road transfer to Bari airport', 105, 0),
    'tropea': ('SUF', 'Lamezia Terme', 'Rail / road transfer to Lamezia Terme airport', 150, 0),
    'sorrento': ('NAP', 'Naples', 'Separately checked road / rail transfer to Naples airport', 180, 0),
    'cefalu': ('PMO', 'Palermo', 'Rail / road transfer through Palermo to its airport', 180, 0),
    'hvar': ('SPU', 'Split', 'Ferry to Split + ground transfer to Split airport', 300, 1),
    'vis': ('SPU', 'Split', 'Ferry to Split + ground transfer to Split airport', 360, 1),
    'korcula': ('SPU', 'Split', 'Ferry from Vela Luka to Split + ground transfer to Split airport', 420, 1),
    'lecce': ('BDS', 'Brindisi', 'Separately checked road / rail transfer to Brindisi airport', 120, 0),
}


def airport_access(city):
    if city.id in OVERRIDES:
        code, name, route, minutes, ferries = OVERRIDES[city.id]
        return {'airport': code, 'name': name, 'route': route, 'estimated_minutes': minutes,
                'ferry_crossings': ferries, 'status': 'illustrative_candidate',
                'notice': 'App transfer allowance includes local access and connection margin, but excludes airport check-in and waiting for scheduled services. Check actual transport and allow a separate night before a flight if needed. No flight availability checked.'}
    if city.airport:
        return {'airport': city.airport, 'name': None,
                'route': 'Ground access from the named stay to its catalogued airport; exact route and transfer duration need research.',
                'estimated_minutes': None, 'ferry_crossings': 0, 'status': 'access_not_timed',
                'notice': 'An airport code is not a flight connection or a timed transfer. Local services, operating hours and Bergen flights are unverified.'}
    return {'airport': None, 'name': None, 'route': 'Return airport and onward access still need research.',
            'estimated_minutes': None, 'ferry_crossings': None, 'status': 'unknown',
            'notice': 'No airport route or flight availability has been established.'}
