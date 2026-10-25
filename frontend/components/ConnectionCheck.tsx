"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { ConnectionPlan } from "../lib/connection-types";

type Result = { status: string; latest_arrival_at_start: string; ready_at_destination: string; origin_timezone: string; destination_timezone: string; before_margin_minutes: number | null; onward_margin_minutes: number | null; arrival_day_change: number; early_or_late_arrival: boolean; crossing_minutes: number; warnings: string[]; notice: string };
const localStamp = (value: string) => value.replace("T", " ").replace(/:\d{2}([+-]\d{2}:\d{2})$/, "$1");
export default function ConnectionCheck({ connectionId, plan }: { connectionId: string; plan: ConnectionPlan }) {
  const [start, setStart] = useState("");
  const [departure, setDeparture] = useState("");
  const [arrival, setArrival] = useState("");
  const [onward, setOnward] = useState("");
  const [onwardBuffer, setOnwardBuffer] = useState(30);
  const [onwardTransfer, setOnwardTransfer] = useState(0);
  const [ferryBuffer, setFerryBuffer] = useState(plan.steps.find(step => step.kind === "check_in")?.estimated_minutes || 0);
  const [portAccess, setPortAccess] = useState(plan.steps.find(step => step.kind === "port_access")?.estimated_minutes || 0);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  function changed() { generation.current++; setResult(null); setError(""); setBusy(false); }
  async function check(event: FormEvent) {
    event.preventDefault();
    const version = ++generation.current;
    setBusy(true); setResult(null); setError("");
    try {
      const answer = await api<Result>("travel/connections/check", "POST", { connection_id: connectionId, arrival_at_start: start || null, ferry_departure: departure, ferry_arrival: arrival, onward_departure: onward || null, onward_check_in_minutes: onwardBuffer, onward_transfer_minutes: onwardTransfer, ferry_check_in_minutes: ferryBuffer, port_access_minutes: portAccess });
      if (version === generation.current) setResult(answer);
    } catch (problem) { if (version === generation.current) setError((problem as Error).message); }
    finally { if (version === generation.current) setBusy(false); }
  }
  return <details className="connection-check"><summary>Check researched connection times</summary>
    <p>Enter dates and clock times from your research, local to each location. This calculates margins against the listed allowances. Times are not verified, saved or applied to your trip.</p>
    <form onSubmit={check} onChange={changed}>
      <label>Arrive at starting station / city · optional<input type="datetime-local" value={start} onChange={event => setStart(event.target.value)} /></label>
      <div className="row"><label>Ferry departure · port local time<input type="datetime-local" required value={departure} onChange={event => setDeparture(event.target.value)} /></label>
      <label>Ferry arrival · port local time<input type="datetime-local" required value={arrival} onChange={event => setArrival(event.target.value)} /></label></div>
      <div className="row"><label>Station / city to port · minutes<input type="number" min={0} max={720} value={portAccess} onChange={event => setPortAccess(Number(event.target.value))} /></label><label>Ferry check-in / boarding allowance · minutes<input type="number" min={0} max={360} value={ferryBuffer} onChange={event => setFerryBuffer(Number(event.target.value))} /></label></div>
      <small>Adjust these assumptions to your ticket and actual transfer. Changes affect this check only.</small>
      <small>Original budget before sailing: {plan.before_departure_minutes} minutes. Budgeted after landing: {plan.after_arrival_minutes} minutes.</small>
      <label>Onward service departure · destination local time · optional<input type="datetime-local" value={onward} onChange={event => setOnward(event.target.value)} /></label>
      {onward && <><label>Transfer to onward station / airport · minutes<input type="number" min={0} max={1440} value={onwardTransfer} onChange={event => setOnwardTransfer(Number(event.target.value))} /><small>Add transport from the named destination to the next departure point; airport access is not automatically included.</small></label><label>Extra check-in / boarding time for onward service · minutes<input type="number" min={0} max={360} value={onwardBuffer} onChange={event => setOnwardBuffer(Number(event.target.value))} /><small>Use the onward operator’s requirements; the default 30 minutes is a planning assumption.</small></label></>}
      <button type="submit" disabled={busy || !departure || !arrival}>{busy ? "Checking margins…" : "Calculate connection margins"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {result && <div role="status" className={result.status === "insufficient_margin" ? "idea-limitation" : "connection-result"}>
      <strong>{result.status === "insufficient_margin" ? "These times leave too little margin" : result.status === "fits_allowances" ? "Fits the planning allowances · connection unverified" : "Arrival and access times · connecting services not checked"}</strong>
      <p>Reach the starting point by {localStamp(result.latest_arrival_at_start)} ({result.origin_timezone}).</p>
      <p>Ready at the named destination / onward station around {localStamp(result.ready_at_destination)} ({result.destination_timezone}).</p>
      {result.before_margin_minutes != null && <p>Spare margin before the ferry: {result.before_margin_minutes} minutes.</p>}
      {result.onward_margin_minutes != null && <p>Spare margin for onward service: {result.onward_margin_minutes} minutes.</p>}
      <p>Arrival calendar date: {result.arrival_day_change === 0 ? "same date" : `${result.arrival_day_change} day(s) later`} in the arrival port’s local time.</p>
      {result.warnings.map(warning => <p key={warning}>{warning}</p>)}
      <small>{result.notice}</small>
    </div>}
  </details>;
}
