"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

type Location = { uid: string; name: string; countryCode: string; isMeta: boolean };
type Segment = { origin: { name: string }; destination: { name: string }; departureAt: string; arrivalAt: string; transport: string; identifier: string | null; operator: { name: string } };
type Result = { status: string; message: string; environment: string; notice: string; checked_at: string | null; journeys: { segments: Segment[] }[] };

export default function ExternalRailTimetables({ originId, destinationId, date }: { originId: string; destinationId: string; date: string }) {
  const [locations, setLocations] = useState<{ origin: Location[]; destination: Location[] } | null>(null);
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    setLocations(null); setOrigin(""); setDestination(""); setResult(null); setMessage(""); setBusy(false);
    return () => { generation.current++; };
  }, [originId, destinationId, date]);
  async function findLocations() {
    const current = ++generation.current;
    setBusy(true); setMessage(""); setResult(null);
    try {
      const answers = await Promise.all([originId, destinationId].map(city_id => api<{ status: string; message: string; locations: Location[] }>("travel/rail/allaboard/locations", "POST", { city_id })));
      if (generation.current !== current) return;
      if (answers.some(item => item.status !== "ok")) { setMessage(answers.find(item => item.status !== "ok")!.message); return; }
      setLocations({ origin: answers[0].locations, destination: answers[1].locations });
      setOrigin(""); setDestination("");
      if (answers.some(item => !item.locations.length)) setMessage("No nearby provider locations returned for one of these cities. Coverage may be limited.");
    } catch (error) { if (generation.current === current) setMessage(error instanceof Error ? error.message : "Locations unavailable."); }
    finally { if (generation.current === current) setBusy(false); }
  }
  async function search() {
    const current = ++generation.current;
    setBusy(true); setMessage(""); setResult(null);
    try {
      const answer = await api<Result>("travel/rail/allaboard/timetables", "POST", { origin_id: originId, destination_id: destinationId, origin_uid: origin, destination_uid: destination, departure_date: date });
      if (generation.current === current) setResult(answer);
    } catch (error) { if (generation.current === current) setMessage(error instanceof Error ? error.message : "Search unavailable."); }
    finally { if (generation.current === current) setBusy(false); }
  }
  return <details className="rail-timetables"><summary>Search additional rail coverage · All Aboard</summary>
    <p>For gaps in our imported timetables, try the optional rail provider. Each button makes a provider request. Times are local to each station; these results are research and cannot be applied to your calendar.</p>
    <button type="button" disabled={busy} onClick={findLocations}>{busy ? "Working…" : "Find provider cities / stations"}</button>
    {locations && <>
      <label>Provider origin<select value={origin} disabled={busy} onChange={event => { setOrigin(event.target.value); setResult(null); }}><option value="">Choose origin</option>{locations.origin.map(item => <option key={item.uid} value={item.uid}>{item.name}{item.isMeta ? " (city)" : ""}</option>)}</select></label>
      <label>Provider destination<select value={destination} disabled={busy} onChange={event => { setDestination(event.target.value); setResult(null); }}><option value="">Choose destination</option>{locations.destination.map(item => <option key={item.uid} value={item.uid}>{item.name}{item.isMeta ? " (city)" : ""}</option>)}</select></label>
      <button type="button" disabled={busy || !date || !origin || !destination || origin === destination} onClick={search}>Search All Aboard for {date || "a selected date"}</button>
    </>}
    {message && <p role="status">{message}</p>}
    {result && <div aria-live="polite"><p>{result.environment === "test" && <strong>Sandbox research · </strong>}{result.message}</p>
      {result.journeys.map((journey, index) => <article className="timetable-journey" key={index}><h4>Journey {index + 1}</h4><ol>{journey.segments.map((segment, i) => <li key={i}>
        <strong>{segment.operator.name} · {segment.transport.replaceAll("_", " ")} {segment.identifier}</strong>
        <div>{segment.origin.name} → {segment.destination.name}</div>
        <small>{segment.departureAt.replace("T", " ")} → {segment.arrivalAt.replace("T", " ")} · station-local times</small>
      </li>)}</ol></article>)}
      <small>{result.notice}</small>{result.checked_at && <small>Queried {new Date(result.checked_at).toLocaleString()}</small>}
    </div>}
  </details>;
}
