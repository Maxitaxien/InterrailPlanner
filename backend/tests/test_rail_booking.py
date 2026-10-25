def test_booking_guide_uses_transit_countries_and_keeps_offers_unverified(client):
    response = client.post('/api/v1/travel/rail/booking-guide', json={
        'origin_id': 'hamburg', 'destination_id': 'venice',
        'via': ['hamburg', 'munich', 'innsbruck', 'venice'],
        'departure_date': '2027-06-14', 'travel_class': 1,
    })
    assert response.status_code == 200, response.text
    guide = response.json()
    assert guide['countries'] == ['DE', 'AT', 'IT']
    assert guide['via'] == ['Munich', 'Innsbruck']
    assert {operator['label'] for operator in guide['operators']} == {'Deutsche Bahn', 'ÖBB', 'Trenitalia'}
    assert guide['adults'] == 2 and guide['travel_class'] == 1
    assert guide['departure_date'] == '2027-06-14'
    assert guide['status'] == 'guidance_only' and guide['reservation_status'] == 'check_exact_train'
    assert guide['offers'] == [] and guide['price'] is None and guide['availability_checked_at'] is None
    assert any('Brenner' in note for note in guide['notes'])
    assert 'adjacent seats' in guide['couple_tip']
    assert all(operator['url'].startswith('https://') for operator in guide['operators'])


def test_booking_guide_handles_flexible_dates_and_ordinary_tickets(client):
    guide = client.post('/api/v1/travel/rail/booking-guide', json={
        'origin_id': 'london', 'destination_id': 'paris', 'ticket_mode': 'tickets', 'adults': 1
    }).json()
    assert guide['departure_date'] is None
    assert guide['ticket_mode'] == 'tickets'
    assert guide['operators'][0]['label'] == 'Eurostar'
    assert not any('Apply the Interrail pass' in note for note in guide['notes'])
    assert 'two adjacent' not in guide['couple_tip']


def test_booking_guide_rejects_unknown_cities_and_mismatched_path(client):
    response = client.post('/api/v1/travel/rail/booking-guide', json={'origin_id': 'unknown', 'destination_id': 'milan'})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'UNKNOWN_DESTINATION'
    for extra in [{'via': ['rome', 'milan']}, {'adults': 0}, {'travel_class': 3}, {'departure_date': 'invalid'}]:
        response = client.post('/api/v1/travel/rail/booking-guide', json={'origin_id': 'oslo', 'destination_id': 'milan', **extra})
        assert response.status_code == 422
