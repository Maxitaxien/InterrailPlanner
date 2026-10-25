"use client";
import { FormEvent, useEffect, useState } from "react";

import { api } from "../lib/api";
import { useEditorStore } from "../lib/editor-store";
import { useQuery } from "@tanstack/react-query";
import TravelPanel from "../components/TravelPanel";
import RouteMap, { MapDestination, RailEdge } from "../components/RouteMap";
import RailBookingDetails, { TravelPlan } from "../components/RailBookingDetails";
import EndpointTransferDetails from "../components/EndpointTransferDetails";
import StopSuggestions from "../components/StopSuggestions";
import Modal from "../components/Modal";
import CityIdeas from "../components/CityIdeas";
import EndpointComparison from "../components/EndpointComparison";
import { AirportAccess } from "../lib/connection-types";
type Destination = MapDestination & { country_code: string; is_endpoint: boolean };
type Stop = { destination_id: string; name: string; nights: number; arrival_day: number; departure_day: number; arrival_date: string | null; departure_date?: string | null; is_required: boolean; is_locked: boolean; latitude: number; longitude: number };
type Route = { id: string; revision: number; is_selected: boolean; name: string; stops: Stop[]; legs: { origin_id: string; destination_id: string; via: string[]; estimated_minutes: number; mode?: string; rail_minutes?: number; is_long_journey?: boolean; travel_advice?: string; travel_plan?: TravelPlan; suggested_stop_ids?: string[]; connections?: RailEdge[] }[]; score: number; travel_days_estimate: number; total_nights: number; transit_nights_estimate?: number; total_rail_minutes?: number; has_non_rail_transfer?: boolean; warnings: string[]; return_date: string | null; return_day: number; airport: string | null; airport_access?: AirportAccess };
type Saved = { id: string; token: string };
type TripData = { id: string; revision: number; itineraries: Route[]; request: {
  total_days: number; start_date: string | null; required_stops: string[]; preferred_stops: string[];
  preferences: { interests: string[]; pace: string; final_stay_nights: number; endpoint_id: string | null; endpoint_region: string };
  budget: { total: string | null; final_stay: string | null };
  pass: { type: string; validity_type: string; country_code: string | null; travel_days_total: number | null; travel_days_used: number; valid_from: string | null; valid_until: string | null; travel_class?: 1 | 2 };
} };
export default function Home() {
  const destinationQuery = useQuery({ queryKey: ["destinations"], queryFn: () => api<Destination[]>("destinations"), staleTime: 86400000 });
  const destinations = destinationQuery.data ?? [];
  const networkQuery = useQuery({ queryKey: ["rail-network"], queryFn: () => api<RailEdge[]>("rail-network"), staleTime: 86400000 });
  const [tripRevision, setTripRevision] = useState(1);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [routes, setRoutes] = useState<Route[]>([]);
  const { active, setActive } = useEditorStore();
  const [days, setDays] = useState(21);
  const [start, setStart] = useState("");
  const [required, setRequired] = useState(["prague", "venice"]);
  const [preferred, setPreferred] = useState<string[]>([]);
  const [endpoint, setEndpoint] = useState("");
  const [region, setRegion] = useState("southern_italy");
  const regionCountry: Record<string,string> = { southern_italy: "IT", southern_france: "FR", spain: "ES", croatia: "HR", greece: "GR" };
  const [finalNights, setFinalNights] = useState(4);
  const [passDays, setPassDays] = useState(7);
  const [passUsed, setPassUsed] = useState(0);
  const [passType, setPassType] = useState("global");
  const [railClass, setRailClass] = useState<1 | 2>(2);
  const [validityType, setValidityType] = useState("flexi");
  const [countryCode, setCountryCode] = useState("NO");
  const [validFrom, setValidFrom] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [pace, setPace] = useState("balanced");
  const [interests, setInterests] = useState(["culture", "food", "beaches"]);
  const [budget, setBudget] = useState("");
  const [finalBudget, setFinalBudget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [focusCity, setFocusCity] = useState<{ id: string }>();
  const [mapMode, setMapMode] = useState<"route" | "must-see">("route");
  const [reopenId, setReopenId] = useState("");
  const [reopenToken, setReopenToken] = useState("");
  const [removing, setRemoving] = useState<Stop | null>(null);
  useEffect(() => {
    try {
      const stored = localStorage.getItem("interrail:last-trip");
      if (stored) { const value = JSON.parse(stored) as Saved; setSaved(value); load(value.id); }
    } catch { setNotice("Browser storage is unavailable. Keep a copy of your trip ID and edit token."); }
  }, []);
  function restore(trip: TripData) {
    const r = trip.request;
    setTripRevision(trip.revision); setDays(r.total_days); setStart(r.start_date || "");
    setRequired(r.required_stops); setPreferred(r.preferred_stops);
    setEndpoint(r.preferences.endpoint_id || ""); setRegion(r.preferences.endpoint_region);
    setFinalNights(r.preferences.final_stay_nights);
    setPace(r.preferences.pace); setInterests(r.preferences.interests);
    setBudget(r.budget.total || ""); setFinalBudget(r.budget.final_stay || "");
    setPassType(r.pass.type); setValidityType(r.pass.validity_type); setCountryCode(r.pass.country_code || "NO");
    setRailClass(r.pass.travel_class || 2);
    setPassDays(r.pass.travel_days_total || 7); setPassUsed(r.pass.travel_days_used);
    setValidFrom(r.pass.valid_from || ""); setValidUntil(r.pass.valid_until || "");
    setRoutes(trip.itineraries); setActive(Math.max(0, trip.itineraries.findIndex(r => r.is_selected)));
  }
  async function load(id: string) {
    try { restore(await api<TripData>(`trips/${id}`)); }
    catch (e) { setError((e as Error).message); }
  }
  function remember(value: Saved) {
    setSaved(value);
    try { localStorage.setItem("interrail:last-trip", JSON.stringify(value)); }
    catch { setNotice("Could not store this trip in your browser. Save the trip ID and token below."); }
  }
  function formRequest() {
    return {
        total_days: days, start_date: start || null, date_mode: start ? "exact" : "flexible",
        required_stops: required, preferred_stops: preferred,
        preferences: { interests, pace, final_stay_nights: finalNights, endpoint_id: endpoint || null, endpoint_region: region },
        budget: { total: budget || null, final_stay: finalBudget || null, currency: "NOK" },
        pass: { type: passType, country_code: passType === "one_country" ? countryCode : null, validity_type: validityType, travel_days_total: validityType === "flexi" ? passDays : null, travel_days_used: passUsed, valid_from: validFrom || null, valid_until: validUntil || null, travel_class: railClass }
      };
  }
  async function updatePreferences() {
    if (!saved) return;
    setBusy(true); setError(""); setNotice("");
    try {
      restore(await api<TripData>(`trips/${saved.id}`, "PATCH", { expected_revision: tripRevision, ...formRequest() }, saved.token));
      setNotice("Trip preferences saved and alternatives recalculated.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function create(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const trip = await api<{ id: string; revision: number; edit_token: string }>("trips", "POST", formRequest());
      setTripRevision(trip.revision);
      const value = { id: trip.id, token: trip.edit_token }; remember(value); setRoutes([]); setActive(0);
      setRoutes(await api<Route[]>(`trips/${trip.id}/generate`, "POST", {}, value.token));
      setNotice("Trip saved. Your edit token stays in this browser.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function retryGeneration() {
    if (!saved) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const updated = await api<TripData>(`trips/${saved.id}`, "PATCH", { expected_revision: tripRevision, ...formRequest() }, saved.token);
      setTripRevision(updated.revision);
      setRoutes(await api<Route[]>(`trips/${saved.id}/generate`, "POST", {}, saved.token));
      setActive(0); setNotice("Routes generated using your current stops and settings.");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function edit(operation: string, destination_id: string, fields: object = {}) {
    if (!saved || !route) return false;
    setBusy(true); setError("");
    try {
      const updated = await api<Route & { trip_revision?: number }>(`itineraries/${route.id}`, "PATCH", { expected_revision: route.revision, operation, destination_id, ...fields }, saved.token);
      setRoutes(old => old.map(r => r.id === updated.id ? updated : updated.trip_revision != null ? { ...r, revision: r.revision+1, stops: r.stops.map(stop => stop.destination_id === destination_id ? { ...stop, is_required: false } : stop) } : r));
      if (updated.trip_revision != null) {
        setTripRevision(updated.trip_revision);
        setRequired(current => current.filter(city => city !== destination_id));
        setPreferred(current => current.filter(city => city !== destination_id));
      }
      setNotice("Changes saved and itinerary recalculated.");
      return true;
    } catch (e) { setError((e as Error).message); return false; }
    finally { setBusy(false); }
  }
  async function select() {
    if (!saved || !route) return;
    setBusy(true); setError("");
    try { await api(`itineraries/${route.id}/select`, "POST", {}, saved.token); await load(saved.id); setNotice("Alternative selected."); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const route = routes[active];
  const toggle = (values: string[], value: string) => values.includes(value) ? values.filter(v => v !== value) : [...values, value];
  function choosePlanningStop(destination: MapDestination) {
    if (destination.id === "oslo") return;
    setError("");
    setPreferred(current => current.filter(id => id !== destination.id));
    if (destination.category === "island" || destination.category === "coastal") {
      setEndpoint(destination.id);
      setRegion(current => current === "islands" ? current : ({ IT: "southern_italy", GR: "greece", HR: "croatia", FR: "southern_france" }[destination.country_code || ""] || "any"));
      setRequired(current => current.filter(id => id !== destination.id));
      return;
    }
    setRequired(current => current.includes(destination.id) ? current.filter(id => id !== destination.id) : [...current, destination.id]);
  }
  async function chooseRouteStop(destination: MapDestination) {
    if (!route || busy) return;
    const current = route.stops.find(stop => stop.destination_id === destination.id);
    if (current) {
      if (current.is_required || current.is_locked || current.destination_id === "oslo" || current.destination_id === route.stops.at(-1)?.destination_id) return;
      await edit("remove_stop", destination.id);
    } else if (destination.is_endpoint) {
      await edit("change_endpoint", destination.id);
    } else {
      await edit("add_stop", destination.id);
    }
  }
  return <main>
    <header><a className="brand" href="/"><img src="/icon.svg" width={34} height={34} alt="" /> Interrail Helper</a><div className="header-links"><a href="/booking-data">Booking data</a><a href="/settings">AI settings</a><span className="pill">OUR HONEYMOON · BY RAIL</span></div></header>
    <section className="intro"><p className="eyebrow honeymoon-eyebrow">JUST THE TWO OF YOU · A HONEYMOON BY RAIL</p><h1>Take the scenic way.</h1><p>Slow mornings, beautiful stops, and a little longer together in the sun.</p><span className="honeymoon-note">♡ Two travellers · one shared adventure · Oslo → a little further south</span></section>
    {destinationQuery.error && <div className="message error" role="alert">{destinationQuery.error.message} <button onClick={() => destinationQuery.refetch()}>Retry connection</button></div>}
    {networkQuery.error && <div className="message error" role="alert">Rail connections could not load. <button onClick={() => networkQuery.refetch()}>Retry rail network</button></div>}
    {error && <div className="message error" role="alert">{error} <button onClick={() => saved && load(saved.id)}>Reload saved routes</button></div>}
    {notice && <div className="message" role="status">{notice}</div>}
    <div className="workspace"><aside><form onSubmit={create}>
      <div className="section-title"><span className="number">01</span><h2>Shape your honeymoon</h2></div>
      <div className="row"><label>Calendar days<input type="number" min={2} max={90} value={days} onChange={e => setDays(+e.target.value)} required /></label><label>Start date · optional<input type="date" value={start} onChange={e => setStart(e.target.value)} /></label></div>
      <label>Final region<select value={region} onChange={e => { setRegion(e.target.value); setEndpoint(""); }}><option value="southern_italy">Italy & islands</option><option value="southern_france">France & Corsica</option><option value="spain">Spain</option><option value="croatia">Croatia & islands</option><option value="greece">Greece & islands · ferry connections</option><option value="islands">All island stays</option><option value="any">Explore all regions</option></select></label>
      <label>Southern endpoint<select value={endpoint} onChange={e => setEndpoint(e.target.value)}><option value="">Explore alternatives</option>{destinations.filter(d => d.is_endpoint && (region === "islands" ? d.category === "island" : !regionCountry[region] || d.country_code === regionCountry[region])).map(d => <option key={d.id} value={d.id}>{d.name}{d.category === "island" ? " · ferry" : ""}</option>)}</select></label>
      <EndpointComparison destinations={destinations} currentEndpoint={route?.stops.at(-1)?.destination_id || endpoint} busy={busy} onChoose={async id => {
        if (route) return await edit("change_endpoint", id);
        setEndpoint(id);
        const country = destinations.find(city => city.id === id)?.country_code || "";
        setRegion(({ IT: "southern_italy", GR: "greece", HR: "croatia", FR: "southern_france", ES: "spain" } as Record<string, string>)[country] || "any");
        setRequired(current => current.filter(city => city !== id));
        setPreferred(current => current.filter(city => city !== id));
        return true;
      }} />
      <label>Must-see stops</label><p className="map-helper">Explore cities on the map to choose stops. Oslo is always the start.</p><div className="selected-stops">{required.length ? required.map(id => <button type="button" key={id} aria-label={`Remove ${destinations.find(d => d.id === id)?.name || id} from must-see stops`} onClick={() => setRequired(current => current.filter(cityId => cityId !== id))}>{destinations.find(d => d.id === id)?.name || id} ×</button>) : <small>No must-see stops selected yet.</small>}</div>
      <details><summary>Preferred stops</summary><div className="chips">{destinations.filter(d => d.id !== "oslo" && !required.includes(d.id) && !d.is_endpoint).map(d => <button type="button" aria-pressed={preferred.includes(d.id)} key={d.id} onClick={() => setPreferred(toggle(preferred, d.id))}>{d.name}</button>)}</div></details>
      <label>Final stay · nights<input type="number" min={0} max={30} value={finalNights} onChange={e => setFinalNights(+e.target.value)} /></label><small>No daily rail cap. Set a stop to 0 nights for a visit without a hotel stay; this does not select a night train. We’ll flag long journeys and suggest places to break them up. Some endpoints include separately booked ferry or ground transfers.</small>
      <label>Your pace<select value={pace} onChange={e => setPace(e.target.value)}><option value="balanced">Balanced</option><option value="relaxed">Relaxed</option><option value="fast">Fast</option></select></label>
      <fieldset><legend>Make room for</legend><div className="chips">{["culture", "food", "beaches", "nature", "history", "relaxation"].map(i => <button type="button" key={i} aria-pressed={interests.includes(i)} onClick={() => setInterests(toggle(interests, i))}>{i}</button>)}</div></fieldset>
      <details><summary>Your existing pass</summary><div className="row"><label>Pass<select value={passType} onChange={e => setPassType(e.target.value)}><option value="global">Global</option><option value="one_country">One Country</option></select></label><label>Validity<select value={validityType} onChange={e => setValidityType(e.target.value)}><option value="flexi">Flexi</option><option value="continuous">Continuous</option></select></label></div>
      {passType === "one_country" && <label>Pass country · ISO code<input value={countryCode} pattern="[A-Z]{2}" maxLength={2} onChange={e => setCountryCode(e.target.value.toUpperCase())} required /></label>}
      <label>Pass travel class<select value={railClass} onChange={e => setRailClass(+e.target.value as 1 | 2)}><option value={2}>Second class</option><option value={1}>First class</option></select></label>
      {validityType === "flexi" && <div className="row"><label>Total travel days<input type="number" min={1} max={90} value={passDays} onChange={e => setPassDays(+e.target.value)} /></label><label>Already used<input type="number" min={0} max={90} value={passUsed} onChange={e => setPassUsed(+e.target.value)} /></label></div>}
      <div className="row"><label>Valid from · optional<input type="date" value={validFrom} onChange={e => setValidFrom(e.target.value)} /></label><label>Valid until · optional<input type="date" value={validUntil} onChange={e => setValidUntil(e.target.value)} /></label></div></details>
      <details><summary>Optional budget · NOK</summary><div className="row"><label>Whole trip<input type="number" min={0} step="0.01" value={budget} onChange={e => setBudget(e.target.value)} /></label><label>Final stay<input type="number" min={0} step="0.01" value={finalBudget} onChange={e => setFinalBudget(e.target.value)} /></label></div><small>Saved as preferences. Prices and budget feasibility are not yet estimated.</small></details>
      {saved && <button type="button" className="update-trip" disabled={busy || !destinations.length} onClick={updatePreferences}>Save preferences to this trip</button>}
      <button className="primary" disabled={busy || !destinations.length}>{busy ? "Working…" : "Create trip & find routes ↗"}</button>
    </form>{!route && <div className="planning-map"><RouteMap destinations={destinations} network={networkQuery.data} selectedIds={endpoint ? [...required, endpoint] : required} planning busy={busy} travelClass={railClass} tripId={saved?.id} token={saved?.token} onDestinationClick={choosePlanningStop} /></div>}</aside>
    <section className="results" aria-live="polite"><div className="section-title"><span className="number">02</span><h2>Your journey south</h2></div>
      {!route ? <div className="empty"><span>◎</span><h3>Good journeys start with a few ideas.</h3><p>Choose your must-see stops. We’ll connect the corridors, leave time to explore, and save your plan.</p><p className="muted">{destinations.length} cities across Europe. Explore the map to find your next stop.</p>{saved && <><p>Adjust your stops, trip length or pass allowance above, then retry with those settings.</p><button disabled={busy} onClick={retryGeneration}>Retry generation for saved trip</button></>}</div> : <>
        <nav className="alternatives" aria-label="Route alternatives">{routes.map((r,i) => <button disabled={busy} aria-pressed={active === i} key={r.id} onClick={() => setActive(i)}>{r.name}{r.is_selected ? " ✓" : ""}</button>)}</nav>
        <div className="route-heading"><div><p className="eyebrow">YOUR RAIL ITINERARY</p><h2>{route.name}</h2></div><button disabled={busy || route.is_selected} onClick={select}>{route.is_selected ? "Selected ✓" : "Choose this route"}</button></div>
        <div className="stats"><div><strong>{route.total_nights}</strong><span>nights away</span></div><div><strong>{route.travel_days_estimate}</strong><span>estimated pass days</span></div><div><strong>{Math.round(route.score * 100)}%</strong><span>preference score</span></div></div>
        <p className="journey-overview">{Math.round((route.total_rail_minutes ?? route.legs.filter(leg => !leg.mode || leg.mode === "rail").reduce((sum, leg) => sum + leg.estimated_minutes, 0)) / 60)}h estimated rail time in total · no daily cap.{!!route.transit_nights_estimate && ` Includes ${route.transit_nights_estimate} estimated night(s) in transit within your nights away.`}{route.has_non_rail_transfer && " Endpoint ferry / ground travel is separate from rail and needs its own booking."}</p>
        <div className="map-mode chips"><button type="button" aria-pressed={mapMode === "route"} onClick={() => setMapMode("route")}>Edit route</button><button type="button" aria-pressed={mapMode === "must-see"} onClick={() => setMapMode("must-see")}>Choose must-see cities</button>{mapMode === "must-see" && <small>Choose cities, then save your trip preferences above.</small>}</div>
        <RouteMap destinations={destinations} network={networkQuery.data} stops={route.stops} legs={route.legs} selectedIds={required} planning={mapMode === "must-see"} busy={busy} focusCity={focusCity} travelClass={railClass} tripId={saved?.id} token={saved?.token} itineraryId={route.id} onDestinationClick={mapMode === "must-see" ? choosePlanningStop : chooseRouteStop} />
        <p className="caption">Explore a city to add a stay or change your endpoint. New stops are placed in the shortest feasible order.</p>
        <div className="route-stops">
          <div className="route-stops-heading"><h3>Stops on this route</h3><small>{route.stops.length} cities · follow left to right</small></div>
          {route.stops.map((s, i) => <article key={`${s.destination_id}-${i}`} className="route-stop-card">
            <div><small>{String(i + 1).padStart(2, "0")} · {s.arrival_date || `Day ${s.arrival_day + 1}`}{s.is_required && " · REQUIRED"}</small><h3>{s.name}</h3><span>{s.nights === 0 ? (i === 0 ? "Departure city" : "Day visit · no overnight stay") : `${s.nights} ${s.nights === 1 ? "night" : "nights"}`}{s.is_locked ? " · locked" : ""}</span></div>
            <button type="button" className="show-city" onClick={() => { setFocusCity({ id: s.destination_id }); document.querySelector(".results .map-explorer")?.scrollIntoView({ block: "start" }); }}>Explore {s.name} on map</button>
            {i > 0 && i < route.stops.length-1 && <button type="button" className="remove-stop" aria-label={`Remove ${s.name} from route`} disabled={busy || s.is_locked || route.stops.filter(stop => stop.destination_id === s.destination_id).length > 1} title={s.is_locked ? "Unlock this stay first" : "Remove this stay and recalculate the journey"} onClick={() => setRemoving(s)}>Remove stop</button>}
            <CityIdeas destinationId={s.destination_id} name={s.name} tripId={saved?.id} token={saved?.token} itineraryId={route.id} />
            {i === route.stops.length - 1 && <label>Switch final destination<select value={s.destination_id} disabled={busy} onChange={e => edit("change_endpoint", e.target.value)}>{destinations.filter(d => d.is_endpoint).map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
            {i > 0 && s.destination_id !== "oslo" && route.stops.filter(stop => stop.destination_id === s.destination_id).length === 1 && <div className="stop-controls">
              <label className="inline">Nights <input aria-label={`Nights in ${s.name}`} key={`${route.id}-${route.revision}-${s.destination_id}`} type="number" min={0} max={89} defaultValue={s.nights} disabled={busy || s.is_locked} onBlur={async e => { const input = e.currentTarget; const n = input.value === "" ? NaN : +input.value; if (n !== s.nights && Number.isInteger(n) && n >= 0 && n <= 89) { if (!await edit("set_nights", s.destination_id, { nights: n })) input.value = String(s.nights); } else input.value = String(s.nights); }} onKeyDown={e => { if (e.key === "Enter") e.currentTarget.blur(); }} /></label>
              <button disabled={busy} onClick={() => edit("lock_stop", s.destination_id, { locked: !s.is_locked })}>{s.is_locked ? "Unlock" : "Lock"}</button>
              {i < route.stops.length - 1 && <><button aria-label={`Move ${s.name} earlier`} disabled={busy || s.is_locked || i === 1} onClick={() => edit("reorder_stop", s.destination_id, { position: i - 1 })}>←</button><button aria-label={`Move ${s.name} later`} disabled={busy || s.is_locked || i === route.stops.length - 2} onClick={() => edit("reorder_stop", s.destination_id, { position: i + 1 })}>→</button></>}
            </div>}
            {route.legs[i] && <p className="next-leg">↳ {Math.floor(route.legs[i].estimated_minutes / 60)}h {route.legs[i].estimated_minutes % 60}m estimated {route.legs[i].mode && route.legs[i].mode !== "rail" ? "ferry + onward transfer" : "rail"} to {route.stops[i + 1]?.name}<small>{route.legs[i].via.slice(1, -1).map(id => destinations.find(destination => destination.id === id)?.name || id).join(" · ") || (route.legs[i].mode === "ferry_transfer" ? "Via Patras · separate booking" : "Rail corridor")}</small></p>}
            {route.legs[i]?.is_long_journey && <small className="long-leg-badge">{route.legs[i].mode === "ferry_transfer" ? "Check crossing & port transfers" : "Long journey · consider a stay along the way"}</small>}
            {route.legs[i] && (!route.legs[i].mode || route.legs[i].mode === "rail") && <StopSuggestions key={`ideas-${route.id}-${route.revision}-${i}`} itineraryId={route.id} revision={route.revision} legIndex={i} busy={busy} error={error} onAdd={(city, position) => edit("add_stop", city, { position })} />}
            {route.legs[i] && (route.legs[i].mode && route.legs[i].mode !== "rail" ? <EndpointTransferDetails transfers={route.legs[i].connections || []} /> : <RailBookingDetails key={`${route.id}-${i}-${s.destination_id}-${route.stops[i + 1].destination_id}`} originId={s.destination_id} destinationId={route.stops[i + 1].destination_id} via={route.legs[i].via} departureDate={s.departure_date} travelClass={railClass} plan={route.legs[i].travel_plan} busy={busy} exactDates={!!start} onPlan={(operation, id) => edit(operation, s.destination_id, { leg_index: i, ...(id ? { journey_id: id } : {}) })} />)}
          </article>)}
        </div>
        <div className="return"><strong>Return to Bergen · {route.return_date || `Day ${route.return_day+1}`}</strong><p>{route.airport ? `Nearby departure airport: ${route.airport}.` : "Research the return airport and any extra ferry or ground transfer."} Flights and airport transfers need separate verification.</p></div>
        <TravelPanel key={`travel-${route.id}-${route.revision}`} endpoint={route.stops[route.stops.length-1]} airport={route.airport} returnDate={route.return_date} airportAccess={route.airport_access} />
        <details className="warnings"><summary>Before you book · limitations & pass checks</summary><ul>{route.warnings.map(w => <li key={w}>{w}</li>)}</ul><p>Pass status: needs verification. These estimates are not a statement of ticket validity.</p></details>
      </>}
      {saved && <details className="saved"><summary>Saved trip & recovery</summary><p>Trip ID: <code>{saved.id}</code></p><label>Edit token<input readOnly type="password" value={saved.token} onFocus={e => e.currentTarget.select()} /></label><small>Keep this token private. Anyone with it can edit this trip. Trips are readable by ID in this local MVP.</small></details>}
      <details><summary>Reopen another trip</summary><label>Trip ID<input value={reopenId} onChange={e => setReopenId(e.target.value)} /></label><label>Edit token<input type="password" value={reopenToken} onChange={e => setReopenToken(e.target.value)} /></label><button disabled={busy || !reopenId || !reopenToken} onClick={async () => { setBusy(true); setError(""); try { await api(`trips/${reopenId}`); remember({ id: reopenId, token: reopenToken }); await load(reopenId); } catch(e) { setError((e as Error).message); } finally { setBusy(false); } }}>Reopen trip</button></details>
    </section></div><footer>Built for planning, with room for uncertainty. Verify transport details before booking.</footer>
    <Modal open={!!removing} onClose={() => !busy && setRemoving(null)} title={removing ? `Remove ${removing.name}?` : "Remove stop"}>
      <p>This removes the overnight stay and redistributes its nights. Your journey may still pass through this city.</p>
      {removing?.is_required && <p>This is a must-see. Confirming also removes it from the trip’s must-see list. Other alternatives may still visit it as an optional stay.</p>}
      <div className="modal-actions"><button type="button" disabled={busy} onClick={() => setRemoving(null)}>Keep this stop</button><button type="button" className="danger-action" disabled={busy} onClick={async () => { if (removing && await edit("remove_stop", removing.destination_id, removing.is_required ? { remove_required: true, expected_trip_revision: tripRevision } : {})) setRemoving(null); }}>Remove stay & recalculate</button></div>
      {error && <p role="alert">{error}</p>}
    </Modal>
  </main>;
}
