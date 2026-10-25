"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import ExternalRailTimetables from "./ExternalRailTimetables";

type Leg = { mode: string; origin: string; destination: string; departure: string; arrival: string; origin_timezone: string | null; destination_timezone: string | null; operator: string | null; train: string | null; real_time: boolean; stay_seated: boolean };
type Result = { status: string; message: string; notice: string; checked_at: string | null; origin_timezone: string | null; journeys: { selection_id?: string; departure: string; arrival: string; duration_minutes: number; transfers: number; legs: Leg[] }[]; prepared_sources: { id: string; name: string; source_url: string; license_url: string; attribution: string; coverage: string; service_start: string; service_end: string }[] };
type Coverage = { status: string; message: string; notice: string; sources: { id: string; name: string; source_url: string; license_url: string; attribution: string; rail_service_start: string | null; rail_service_end: string | null; rail_trip_count: number | null; date_status: string; origin_stops: string; destination_stops: string }[] };

function stamp(value: string, zone: string | null) {
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: zone || "UTC" }).format(new Date(value)) + ` (${zone || "UTC"})`;
}

export type TimetableSummary = { count: number; minutes: number; date: string };
export default function RailTimetables({ originId, destinationId, date, onSummary, onChoose, busy }: { originId: string; destinationId: string; date: string; onSummary?: (summary: TimetableSummary | null) => void; onChoose?: (id: string) => Promise<void>; busy?: boolean }) {
  const [time, setTime] = useState("08:00");
  const coverage = useQuery({
    queryKey: ["rail-coverage", originId, destinationId, date],
    queryFn: () => api<Coverage>("travel/rail/coverage", "POST", { origin_id: originId, destination_id: destinationId, departure_date: date || null }),
    retry: false, staleTime: 60000,
  });
  const result = useQuery({
    queryKey: ["rail-timetables", originId, destinationId, date, time],
    queryFn: () => api<Result>("travel/rail/timetables", "POST", { origin_id: originId, destination_id: destinationId, departure_date: date, departure_time: time }),
    enabled: false, retry: false, staleTime: 60000,
  });
  useEffect(() => {
    const journeys = result.data?.journeys;
    onSummary?.(!result.isFetching && journeys?.length ? { count: journeys.length, minutes: Math.min(...journeys.map(item => item.duration_minutes)), date } : null);
  }, [result.data, result.isFetching, date, onSummary]);
  return <section className="rail-timetables" aria-label="Self-hosted train timetables">
    <h4>Find actual train departures</h4>
    <p className="booking-hint">Searches between these cities using our imported feeds. The train route may differ from the schematic map corridor. Searching alone does not change your itinerary; applying a departure explicitly recalculates its calendar.</p>
    {coverage.data && <div className="booking-hint" aria-label="Prepared timetable coverage">
      <strong>Coverage check · prepared files only</strong>
      <p>{coverage.data.message}</p>
      {!!coverage.data.sources.length && <details><summary>Feed dates, city coverage & credits</summary>
        <p>{coverage.data.notice}</p>
        {coverage.data.sources.map(source => <p key={source.id}>
          <a href={source.source_url} target="_blank" rel="noopener noreferrer">{source.name}</a>
          <small>Rail calendar: {source.rail_service_start || "not audited"} – {source.rail_service_end || "not audited"}{source.date_status === "outside_envelope" ? " · outside your search date" : ""}</small>
          <small>Nearby rail stops · origin: {source.origin_stops.replaceAll("_", " ")} · destination: {source.destination_stops.replaceAll("_", " ")}</small>
          {source.rail_trip_count != null && <small>{source.rail_trip_count.toLocaleString()} rail trips in the prepared archive</small>}
          <small>{source.attribution} · <a href={source.license_url} target="_blank" rel="noopener noreferrer">Licence</a></small>
        </p>)}
      </details>}
    </div>}
    {coverage.error && <p className="booking-hint">Coverage metadata could not be checked. You can still search timetables.</p>}
    <label>Depart after (origin local time)<input type="time" value={time} onChange={event => setTime(event.target.value)} /></label>
    <button type="button" disabled={!date || !time || result.isFetching} onClick={() => result.refetch()}>{result.isFetching ? "Searching timetables…" : "Search self-hosted timetables"}</button>
    {!date && <p className="booking-hint">Choose a travel date above to search.</p>}
    {result.error && <p role="alert">{result.error.message} Try the search again.</p>}
    {result.data && !result.isFetching && <div aria-live="polite">
      <p>{result.data.message}</p>
      {result.data.journeys.map((journey, index) => <article className="timetable-journey" key={`${journey.departure}-${index}`}>
        <h4>{Math.floor(journey.duration_minutes / 60)}h {journey.duration_minutes % 60}m · {journey.transfers} change{journey.transfers === 1 ? "" : "s"}</h4>
        <p>{stamp(journey.departure, journey.legs[0]?.origin_timezone || null)} → {stamp(journey.arrival, journey.legs.at(-1)?.destination_timezone || null)}</p>
        <details><summary>Train changes & times</summary><ol>{journey.legs.map((leg, i) => <li key={i}>
          <strong>{leg.mode === "WALK" ? "Walk / station transfer" : [leg.operator, leg.train || leg.mode.replaceAll("_", " ")].filter(Boolean).join(" · ")}</strong>
          <div>{leg.origin} → {leg.destination}</div>
          <small>{stamp(leg.departure, leg.origin_timezone)} → {stamp(leg.arrival, leg.destination_timezone)}</small>
          {leg.stay_seated && <small>Stay on the train.</small>}
          {leg.real_time && <small>Includes real-time updates.</small>}
        </li>)}</ol></details>
        <small>Pass acceptance, reservations, supplements and seat availability: not verified.</small>
        {onChoose && journey.selection_id && <button type="button" disabled={busy} onClick={() => onChoose(journey.selection_id!)}>Use this departure in itinerary</button>}
      </article>)}
      <small>{result.data.notice}</small>
      {result.data.checked_at && <small>Timetable queried {new Date(result.data.checked_at).toLocaleString()}</small>}
      {!!result.data.prepared_sources?.length && <details><summary>Prepared timetable sources & credits</summary><p className="booking-hint">These are prepared inputs; restart MOTIS after import to load changes. Date envelopes do not guarantee daily service or coverage.</p>{result.data.prepared_sources.map(source => <p key={source.id}><a href={source.source_url} target="_blank" rel="noopener noreferrer">{source.name}</a> · <a href={source.license_url} target="_blank" rel="noopener noreferrer">Licence</a><small>{source.attribution}</small><small>{source.service_start} – {source.service_end} · {source.coverage}</small></p>)}</details>}
    </div>}
    <ExternalRailTimetables originId={originId} destinationId={destinationId} date={date} />
  </section>;
}
