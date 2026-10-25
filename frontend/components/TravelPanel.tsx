"use client";
import { FormEvent, useState } from "react";
import { api } from "../lib/api";
import { AirportAccess, duration } from "../lib/connection-types";
type SearchResult = { provider: string; search_url: string; notice: string; status: string; currency: string; trip_type?: string; search_links?: { departure_date: string; search_url: string }[] };
type Rules = { verification_status: string; source_url: string; source_excerpt: string | null; cached: boolean; retrieved_at: string | null; expires_at: string | null; notice: string };
type Endpoint = { destination_id: string; name: string; arrival_date: string | null; departure_day: number; arrival_day: number };
export default function TravelPanel({ endpoint, airport, returnDate, airportAccess }: { endpoint: Endpoint; airport: string | null; returnDate: string | null; airportAccess?: AirportAccess }) {
  const [departureAirport, setDepartureAirport] = useState(airport || "");
  const [flightDate, setFlightDate] = useState(returnDate || "");
  const [flexibleFlights, setFlexibleFlights] = useState(false);
  const [flightDateEnd, setFlightDateEnd] = useState(returnDate || "");
  const [checkIn, setCheckIn] = useState(endpoint.arrival_date || "");
  const [checkOut, setCheckOut] = useState(returnDate || "");
  const [adults, setAdults] = useState(2);
  const [rooms, setRooms] = useState(1);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [rules, setRules] = useState<Rules | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function search(event: FormEvent, kind: "flights" | "hotels") {
    event.preventDefault(); setBusy(true); setError(""); setResult(null);
    try {
      setResult(await api<SearchResult>(`travel/${kind}/search`, "POST", kind === "flights" ? { origin_airport: departureAirport, departure_date: flightDate || null, departure_date_end: flexibleFlights ? flightDateEnd || null : null, trip_type: "one_way", adults, currency: "NOK" } : { destination_id: endpoint.destination_id, check_in: checkIn || null, check_out: checkOut || null, adults, rooms, currency: "NOK" }));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function fetchRules() {
    setBusy(true); setError("");
    try { setRules(await api<Rules>("travel/rail-rules", "POST", { topic: "reservations" })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <section className="travel-panel"><h3>A lovely place to end the honeymoon.</h3><p>Two adults and one room to start with. Your flight home is one-way; choose an exact departure date or a flexible range. Searches open booking sites; prices and availability are checked there. Flight research does not change your itinerary or hotel dates.</p>
    {airportAccess && <div className="airport-access"><h4>Getting to a return airport</h4><p>{airportAccess.airport ? `Candidate airport: ${airportAccess.airport}${airportAccess.name ? ` · ${airportAccess.name}` : ""}. ` : ""}{airportAccess.route}</p>{airportAccess.estimated_minutes != null && <p>{duration(airportAccess.estimated_minutes)} illustrative transfer allowance, separate from your itinerary.</p>}{!!airportAccess.ferry_crossings && <p>Includes {airportAccess.ferry_crossings} extra ferry crossing(s). Consider a night near the airport before flying.</p>}<small>{airportAccess.notice}</small>{airportAccess.airport && airportAccess.airport !== departureAirport && <button type="button" onClick={() => { setDepartureAirport(airportAccess.airport!); setResult(null); }}>Research flights from {airportAccess.airport}</button>}</div>}
    <label>Adults<input type="number" min={1} max={9} value={adults} onChange={e => { setAdults(+e.target.value); setResult(null); }} /></label>
    <div className="travel-grid"><form onSubmit={e => search(e, "flights")}><h4>{departureAirport || "Choose airport"} → Bergen · one-way</h4><label>Departure airport · IATA<input value={departureAirport} required pattern="[A-Z]{3}" maxLength={3} onChange={event => { setDepartureAirport(event.target.value.toUpperCase()); setResult(null); }} /></label><label>Flight departure<input type="date" required value={flightDate} onChange={e => { setFlightDate(e.target.value); setResult(null); }} /></label><label className="flight-flexible"><input type="checkbox" checked={flexibleFlights} onChange={e => { setFlexibleFlights(e.target.checked); if (!flightDateEnd || flightDateEnd < flightDate) setFlightDateEnd(flightDate); setResult(null); }} /> Flexible departure dates</label>{flexibleFlights && <><label>Latest flight departure<input type="date" required min={flightDate || undefined} value={flightDateEnd} onChange={e => { setFlightDateEnd(e.target.value); setResult(null); }} /></label><small>Up to 31 dates. Compare a separate one-way search for each day; these are not return-trip dates.</small></>}<button disabled={busy || !/^[A-Z]{3}$/.test(departureAirport)}>Prepare flight search</button></form>
    <form onSubmit={e => search(e, "hotels")}><h4>Stay in {endpoint.name}</h4><div className="row"><label>Check-in<input type="date" required value={checkIn} onChange={e => { setCheckIn(e.target.value); setResult(null); }} /></label><label>Check-out<input type="date" required min={checkIn || undefined} value={checkOut} onChange={e => { setCheckOut(e.target.value); setResult(null); }} /></label></div><label>Rooms<input type="number" min={1} max={15} value={rooms} onChange={e => { setRooms(+e.target.value); setResult(null); }} /></label><button disabled={busy}>Prepare accommodation search</button></form></div>
    {error && <p role="alert">{error}</p>}{result && <div className="message"><p>{result.notice}</p>{result.search_links && result.search_links.length > 1 ? <div className="booking-links" aria-label="One-way departure searches">{result.search_links.map(link => <a key={link.departure_date} href={link.search_url} target="_blank" rel="noopener noreferrer">One-way · {link.departure_date} ↗</a>)}</div> : <a href={result.search_url} target="_blank" rel="noopener noreferrer">Open external search ↗</a>}<small> · {result.currency} · No live offers retrieved</small></div>}
    <details><summary>Rail reservations · official source</summary><p>Fetch the official reference on demand. The source is cached for up to 24 hours and does not confirm your individual pass validity.</p><button disabled={busy} onClick={fetchRules}>{busy ? "Working…" : "Retrieve official source"}</button>
    {rules && <div className="rail-source"><p>Status: {rules.verification_status}{rules.cached ? " · cached" : ""}</p><p>{rules.notice}</p>{rules.source_excerpt && <blockquote>{rules.source_excerpt}</blockquote>}<a href={rules.source_url} target="_blank" rel="noopener noreferrer">Open official source ↗</a>{rules.retrieved_at && <p className="caption">Retrieved: {new Date(rules.retrieved_at).toLocaleString()} · Expires: {new Date(rules.expires_at!).toLocaleString()}</p>}</div>}</details>
  </section>;
}
