"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { MapDestination } from "./RouteMap";
import Modal from "./Modal";
import ConnectionCheck from "./ConnectionCheck";
import { ConnectionPlan, duration } from "../lib/connection-types";

type Connection = { origin: string; destination: string; connection_id: string; mode: string; estimated_minutes: number; service_type: string; source_url: string | null; reservation_warning: string | null; connection_plan: ConnectionPlan | null };
type Comparison = { endpoint_id: string; name: string; status: string; selectable: boolean; notice?: string; route_names?: string[]; estimated_minutes?: number; breakdown_minutes?: Record<string, number>; ferry_crossings?: number; onward_ground_legs?: number; transit_nights_lower_bound?: number; seasonal?: boolean; burden?: string; caveats?: string[]; connections?: Connection[]; airport_access: { airport: string | null; name: string | null; route: string; estimated_minutes: number | null; ferry_crossings: number | null; status: string; notice: string } };
type Result = { origin_id: string; origin_name: string; comparisons: Comparison[]; notice: string };

export default function EndpointComparison({ destinations, currentEndpoint, onChoose, busy }: { destinations: MapDestination[]; currentEndpoint?: string; onChoose: (id: string) => Promise<boolean> | boolean; busy?: boolean }) {
  const [open, setOpen] = useState(false);
  const [origin, setOrigin] = useState("bari");
  const [selected, setSelected] = useState<string[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("selected");
  const generation = useRef(0);
  const endpoints = destinations.filter(city => city.is_endpoint);
  const origins = destinations.filter(city => city.country_code === "IT" && city.category !== "island" && city.id !== "cefalu");
  useEffect(() => () => { generation.current++; }, []);
  function invalidate() { generation.current++; setResult(null); setLoading(false); setError(""); }
  function show() {
    invalidate(); setOpen(true);
    setSelected([...new Set([currentEndpoint, "corfu", "kefalonia", "crete"].filter((id): id is string => !!id && endpoints.some(city => city.id === id)))].slice(0, 4));
  }
  function toggle(id: string) { invalidate(); setSelected(current => current.includes(id) ? current.filter(value => value !== id) : current.length < 6 ? [...current, id] : current); }
  async function compare() {
    const version = ++generation.current;
    setLoading(true); setError(""); setResult(null);
    try {
      const answer = await api<Result>("travel/endpoints/compare", "POST", { origin_id: origin, endpoint_ids: selected });
      if (version === generation.current) setResult(answer);
    } catch (problem) { if (version === generation.current) setError((problem as Error).message); }
    finally { if (version === generation.current) setLoading(false); }
  }
  async function choose(id: string) {
    setError("");
    try { if (await onChoose(id)) { invalidate(); setOpen(false); } else setError("This endpoint could not be applied. Check the planner’s route constraints."); }
    catch (problem) { setError((problem as Error).message); }
  }
  const comparisons = result ? [...result.comparisons].sort((a, b) => sort === "time" ? (a.estimated_minutes ?? Infinity) - (b.estimated_minutes ?? Infinity) : sort === "ferries" ? (a.ferry_crossings ?? Infinity) - (b.ferry_crossings ?? Infinity) : 0) : [];
  return <>
    <button type="button" className="endpoint-compare-toggle" disabled={!endpoints.length || busy} onClick={show}>Compare final destinations</button>
    <Modal open={open} onClose={() => { invalidate(); setOpen(false); }} title="Find your final stretch of sunshine">
      <p>Compare up to six stays from the same Italian starting point. Your earlier holiday route is excluded; choosing a destination recalculates your trip separately.</p>
      <label>Compare from<select value={origin} onChange={event => { invalidate(); setOrigin(event.target.value); }}>{origins.map(city => <option value={city.id} key={city.id}>{city.name}</option>)}</select></label>
      <fieldset className="endpoint-options"><legend>Final stays · {selected.length} of 6</legend>{endpoints.map(city => <label key={city.id}><input type="checkbox" checked={selected.includes(city.id)} disabled={!selected.includes(city.id) && selected.length >= 6} onChange={() => toggle(city.id)} />{city.name} <small>{city.country_code}</small></label>)}</fieldset>
      <button type="button" disabled={loading || !selected.length || busy} onClick={compare}>{loading ? "Comparing…" : "Compare selected stays"}</button>
      {error && <p role="alert">{error}</p>}
      {result && <section className="endpoint-comparison-results" aria-label="Endpoint comparison results">
        <p role="status">{result.notice}</p>
        <label>Order comparison<select value={sort} onChange={event => setSort(event.target.value)}><option value="selected">Selection order</option><option value="time">Shortest estimated travel</option><option value="ferries">Fewest ferry crossings</option></select></label>
        <div className="comparison-table-wrap"><table className="comparison-table"><caption>From {result.origin_name} · all times are planning allowances</caption><thead><tr><th>Final stay</th><th>Travel burden</th><th>Ferries & onward travel</th><th>Return-airport access</th><th>Choose</th></tr></thead><tbody>{comparisons.map(item => <tr key={item.endpoint_id}>
          <th scope="row">{item.name}</th>
          <td data-label="Travel burden">{item.status === "modeled" ? <><strong>{duration(item.estimated_minutes!)}</strong><small>{item.burden}</small><small>{item.transit_nights_lower_bound} minimum transit night(s); actual departure times may require more.</small></> : item.notice}</td>
          <td data-label="Ferries & onward travel">{item.status === "modeled" && <><strong>{item.ferry_crossings} ferry crossing(s)</strong><small>{item.onward_ground_legs} separately modeled ground leg(s), plus port / station access.</small>{item.seasonal && <small>Potentially seasonal</small>}</>}</td>
          <td data-label="Return-airport access"><strong>{item.airport_access.airport || "Airport needs research"}{item.airport_access.name ? ` · ${item.airport_access.name}` : ""}</strong><small>{item.airport_access.route}</small><small>{item.airport_access.estimated_minutes == null ? "Transfer duration unverified" : `${duration(item.airport_access.estimated_minutes)} illustrative transfer budget`}</small>{!!item.airport_access.ferry_crossings && <small>Return access needs {item.airport_access.ferry_crossings} extra ferry crossing(s).</small>}</td>
          <td data-label="Choose"><button type="button" disabled={busy || !item.selectable || item.endpoint_id === currentEndpoint} onClick={() => choose(item.endpoint_id)}>{item.endpoint_id === currentEndpoint ? "Current final stay" : `Choose ${item.name}`}</button></td>
        </tr>)}</tbody></table></div>
        {comparisons.filter(item => item.status === "modeled").map(item => <details key={item.endpoint_id} className="comparison-route"><summary>{item.name} · route, connections & arrival planning</summary>
          <p>{item.route_names?.join(" → ")}</p>
          <dl className="comparison-breakdown">{Object.entries(item.breakdown_minutes || {}).filter(([, minutes]) => minutes > 0).map(([kind, minutes]) => <div key={kind}><dt>{kind.replaceAll("_", " ")}</dt><dd>{duration(minutes)}</dd></div>)}</dl>
          {item.caveats?.map(note => <p className="booking-hint" key={note}>{note}</p>)}
          <p className="booking-hint">{item.airport_access.notice}</p>
          {item.connections?.map((connection, index) => <section className="modal-section" key={index}><h3>{connection.origin} → {connection.destination}</h3><p>{duration(connection.estimated_minutes)} · {connection.service_type}</p>
            {connection.connection_plan && <><ol className="connection-steps">{connection.connection_plan.steps.map((step, i) => <li key={i}>{step.label}<strong>{duration(step.estimated_minutes)}</strong></li>)}</ol><small>{connection.connection_plan.notice}</small>{connection.connection_plan.arrival_notes.map(note => <p key={note}>{note}</p>)}{connection.connection_plan.ferry_count === 1 && <ConnectionCheck connectionId={connection.connection_id} plan={connection.connection_plan} />}</>}
            {connection.reservation_warning && <p>{connection.reservation_warning}</p>}
            {connection.source_url?.startsWith("https://") && <a href={connection.source_url} target="_blank" rel="noopener noreferrer">Route reference ↗</a>}
          </section>)}
        </details>)}
      </section>}
    </Modal>
  </>;
}
