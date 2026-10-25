from urllib.parse import urlencode
from datetime import timedelta
from app.providers.base import SearchResult

class FlightSearchLinks:
    async def search(self, request):
        end = request.departure_date_end or request.departure_date
        links = []
        for offset in range((end - request.departure_date).days + 1):
            day = request.departure_date + timedelta(days=offset)
            query = f"One way flights from {request.origin_airport} to BGO on {day.isoformat()} for {request.adults} adults"
            links.append({"departure_date": day.isoformat(), "search_url": "https://www.google.com/travel/flights?" + urlencode({"q": query, "curr": request.currency})})
        return SearchResult(provider="external-search", status="link_only", offers=[],
            search_url=links[0]["search_url"], search_links=links, trip_type="one_way", currency=request.currency,
            notice="One-way flight search links only. Each date is a separate departure, not a return flight. No prices or availability have been checked; confirm one-way selection, dates, passengers, baggage and terms on the booking site.")

class AccommodationSearchLinks:
    async def search(self, request):
        params = {"ss": request.destination_name, "checkin": request.check_in.isoformat(), "checkout": request.check_out.isoformat(),
            "group_adults": request.adults, "no_rooms": request.rooms, "group_children": 0, "selected_currency": request.currency}
        return SearchResult(provider="external-search", status="link_only", offers=[],
            search_url="https://www.booking.com/searchresults.html?" + urlencode(params), currency=request.currency,
            notice="External search link only. No price, availability, taxes, fees or cancellation terms have been checked.")
