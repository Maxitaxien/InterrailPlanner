"use client";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import RailTimetables, { TimetableSummary } from "./RailTimetables";
import Modal from "./Modal";
type Guide = { origin: string; destination: string; via: string[]; operators: { label: string; url: string }[]; notes: string[]; reservation_url: string; timetable_url: string; rules_url: string; couple_tip: string; notice: string; guidance_reviewed_on: string };
export type TravelPlan = { kind: "overnight_intent" | "timetable"; status_label: string; needs_recheck: boolean; queried_at?: string; recheck_after?: string; arrival_date?: string; journey?: { departure: string; arrival: string; legs: { train: string | null; operator: string | null; origin?: string; destination?: string; departure?: string; arrival?: string; origin_timezone?: string | null; destination_timezone?: string | null }[] } };
type Props = { originId: string; destinationId: string; via?: string[]; departureDate?: string | null; travelClass?: 1 | 2; plan?: TravelPlan; busy?: boolean; exactDates?: boolean; onPlan?: (operation: "set_leg_plan" | "set_journey" | "clear_leg_plan", id?: string) => Promise<boolean> };
const EMPTY_VIA: string[] = [];
const TABS = ["Departures", "Reservations", "Journey notes"] as const;
function savedTime(value: string, zone?: string | null) {
  return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: zone || "UTC" }).format(new Date(value)) + ` (${zone || "UTC"})`;
}

export default function RailBookingDetails({ originId, destinationId, via = EMPTY_VIA, departureDate, travelClass = 2, plan, busy, exactDates, onPlan }: Props) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<typeof TABS[number]>("Departures");
  const [date, setDate] = useState(departureDate || "");
  const [adults, setAdults] = useState(2);
  const [ticketMode, setTicketMode] = useState<"pass" | "tickets">("pass");
  const [copyMessage, setCopyMessage] = useState("");
  const [checked, setChecked] = useState<TimetableSummary | null>(null);
  const [planError, setPlanError] = useState("");
  async function savePlan(operation: "set_leg_plan" | "set_journey" | "clear_leg_plan", id?: string) {
    setPlanError("");
    if (!onPlan) return;
    if (await onPlan(operation, id)) setOpen(false);
    else setPlanError("This change could not be saved. Check the itinerary error and adjust the stays, locks or departure date.");
  }
  useEffect(() => { setDate(departureDate || ""); setCopyMessage(""); setChecked(null); }, [departureDate, originId, destinationId]);
  const guide = useQuery({ queryKey: ["rail-booking", originId, destinationId, via, date, adults, travelClass, ticketMode], queryFn: () => api<Guide>("travel/rail/booking-guide", "POST", { origin_id: originId, destination_id: destinationId, via, departure_date: date || null, adults, travel_class: travelClass, ticket_mode: ticketMode }), enabled: open && adults >= 1 && adults <= 9, staleTime: 3600000, retry: false });
  const summary = guide.data ? `${guide.data.origin} → ${guide.data.destination}${guide.data.via.length ? ` via ${guide.data.via.join(", ")}` : ""}\n${date || "Date to be decided"} · ${adults} adult${adults === 1 ? "" : "s"} · ${travelClass === 1 ? "1st" : "2nd"} class\n${ticketMode === "pass" ? "Interrail passholder: check reservations and supplements" : "Compare full-price tickets and fare conditions"}\nPreference: ${adults === 2 ? "two adjacent seats" : "seats together where possible"}. Check actual departure and connection times.` : "";
  return <div className="rail-booking"><small className="leg-confidence">{plan ? plan.status_label : checked ? `${checked.count} timetable option(s) · shortest ${Math.floor(checked.minutes/60)}h ${checked.minutes%60}m · ${checked.date}` : "Estimated corridor · timetable not checked"}</small>
    {plan?.journey && <small>{plan.journey.legs.filter(leg => leg.train).map(leg => leg.train).join(" · ")} · arrival {plan.arrival_date || "see journey details"} · reservations unknown</small>}
    <button type="button" className="leg-action" onClick={() => setOpen(true)}>Plan & book this train leg</button>
    <Modal open={open} onClose={() => setOpen(false)} title={guide.data ? `${guide.data.origin} → ${guide.data.destination}` : "Plan this train journey"}>
      <div className="journey-context booking-fields"><label>Travel date<input type="date" value={date} onChange={event => { setDate(event.target.value); setChecked(null); setCopyMessage(""); }} /></label><label>Travellers<input type="number" min={1} max={9} value={adults} onChange={event => setAdults(+event.target.value)} /></label><label>How you’ll travel<select value={ticketMode} onChange={event => setTicketMode(event.target.value as "pass" | "tickets")}><option value="pass">Interrail pass + reservations</option><option value="tickets">Compare regular train tickets</option></select></label></div>
      <p className="modal-footnote">{travelClass === 1 ? "First" : "Second"} class · research settings do not change your itinerary. No seats or fares are confirmed.</p>
      <nav className="modal-tabs" role="tablist" aria-label="Train planning sections">{TABS.map(name => <button type="button" role="tab" key={name} aria-selected={tab === name} tabIndex={tab === name ? 0 : -1} onClick={() => setTab(name)} onKeyDown={event => { if (["ArrowLeft", "ArrowRight"].includes(event.key)) { event.preventDefault(); const index = (TABS.indexOf(name) + (event.key === "ArrowRight" ? 1 : 2)) % 3; setTab(TABS[index]); (event.currentTarget.parentElement?.children[index] as HTMLElement)?.focus(); } }}>{name}</button>)}</nav>
      <div className="rail-booking-content">
        {guide.isPending && <p>Preparing journey guidance…</p>}{guide.error && <p role="alert">{guide.error.message} <button type="button" onClick={() => guide.refetch()}>Retry booking guidance</button></p>}
        <section role="tabpanel" aria-label="Departures" hidden={tab !== "Departures"}>
          {onPlan && <section className="journey-intention" aria-label="Saved travel plan"><h4>Plan now, verify later</h4>
            <p>{plan?.status_label || "Daytime corridor estimate · no departure selected"}</p>
            {plan?.journey && <div aria-label="Saved timetable journey">
              <p><strong>Saved departure</strong> · {savedTime(plan.journey.departure, plan.journey.legs[0]?.origin_timezone)}</p>
              <p><strong>Saved arrival</strong> · {savedTime(plan.journey.arrival, plan.journey.legs.at(-1)?.destination_timezone)}</p>
              <details><summary>Saved trains & station times</summary>{plan.journey.legs.map((leg, i) => <p key={i}>
                <strong>{[leg.operator, leg.train].filter(Boolean).join(" · ") || "Walking access / transfer"}</strong><br />
                {leg.origin} → {leg.destination}
                {leg.departure && leg.arrival && <small>{savedTime(leg.departure, leg.origin_timezone)} → {savedTime(leg.arrival, leg.destination_timezone)}</small>}
              </p>)}</details>
            </div>}
            <p className="booking-hint">An overnight intention budgets nights in transit without claiming a night train exists. Timetables, cabins and reservations can be checked when your dates are published. Pass-day savings are not assumed.</p>
            {plan?.kind !== "overnight_intent" && <button type="button" disabled={busy} onClick={() => savePlan("set_leg_plan")}>Plan overnight travel · unverified</button>}
            {plan && <button type="button" disabled={busy} onClick={() => savePlan("clear_leg_plan")}>Clear travel plan · use estimates</button>}
            {plan?.queried_at && <small>Saved research from {new Date(plan.queried_at).toLocaleString()}. Recheck before booking and travel.</small>}
            {!exactDates && <small>Set an exact trip start date before applying a dated departure. Overnight intentions work with flexible dates.</small>}
            {planError && <p role="alert">{planError}</p>}
          </section>}
          <RailTimetables originId={originId} destinationId={destinationId} date={date} onSummary={setChecked} busy={busy} onChoose={onPlan && exactDates ? id => savePlan("set_journey", id) : undefined} />{guide.data && <a href={guide.data.timetable_url} target="_blank" rel="noopener noreferrer">Check departures with Interrail ↗</a>}</section>
        {guide.data && <><section role="tabpanel" aria-label="Reservations" hidden={tab !== "Reservations"}><h3>What still needs booking?</h3><span className="booking-status">Guidance only · no live offers</span><p>Pass acceptance, reservation requirements, supplements and seats need checking for the exact train.</p><p className="couple-tip">{guide.data.couple_tip}</p>
          <div className="booking-links">{ticketMode === "pass" && <a href={guide.data.reservation_url} target="_blank" rel="noopener noreferrer">Passholder reservations ↗</a>}{guide.data.operators.map(operator => <a key={operator.url} href={operator.url} target="_blank" rel="noopener noreferrer">{operator.label} ↗</a>)}</div>
          <details className="secondary-notes"><summary>Operator notes & limitations</summary><ul>{guide.data.notes.map(note => <li key={note}>{note}</li>)}</ul><p>{guide.data.notice}</p><a href={guide.data.rules_url} target="_blank" rel="noopener noreferrer">Official operator & pass rules ↗</a><small>Guidance reviewed {guide.data.guidance_reviewed_on}</small></details></section>
          <section role="tabpanel" aria-label="Journey notes" hidden={tab !== "Journey notes"}><h3>Your research checklist</h3><label>Journey details to copy<textarea rows={6} readOnly value={summary} onFocus={event => event.currentTarget.select()} /></label><button type="button" onClick={async () => { try { await navigator.clipboard.writeText(summary); setCopyMessage("Journey details copied."); } catch { setCopyMessage("Select the journey details above to copy them."); } }}>Copy journey details</button>{copyMessage && <p role="status">{copyMessage}</p>}</section></>}
      </div>
    </Modal></div>;
}
