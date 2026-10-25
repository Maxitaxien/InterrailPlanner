"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import Modal from "./Modal";
type Suggestion = { destination_id: string; name: string; origin: string; destination: string; before_minutes: number; after_minutes: number; extra_travel_minutes: number; suggested_nights: number; planned_nights: number | null; extra_pass_days: number | null; reason: string; can_add: boolean; limitation: string | null };
const duration = (minutes: number) => `${Math.floor(minutes/60)}h${minutes % 60 ? ` ${minutes%60}m` : ""}`;

export default function StopSuggestions({ itineraryId, revision, legIndex, busy, onAdd, error }: { itineraryId: string; revision: number; legIndex: number; busy: boolean; onAdd: (city: string, position: number) => Promise<boolean>; error?: string }) {
  const [open, setOpen] = useState(false);
  const [addFailed, setAddFailed] = useState(false);
  const query = useQuery({ queryKey: ["stop-suggestions", itineraryId, revision, legIndex], queryFn: () => api<{ suggestions: Suggestion[]; notice: string }>(`itineraries/${itineraryId}/legs/${legIndex}/stop-suggestions`), enabled: open, retry: false, staleTime: 60000 });
  return <><button type="button" className="leg-action" onClick={() => setOpen(true)}>Find an in-between stop</button>
    <Modal open={open} onClose={() => setOpen(false)} title="Make time for somewhere lovely">
      <p className="modal-intro">Places along this leg, with a preview of the travel split and time to stay. Nothing changes until you add one.</p>
      {query.isPending && <p>Finding places and checking your calendar…</p>}
      {query.error && <p role="alert">{query.error.message} <button type="button" onClick={() => query.refetch()}>Retry stop ideas</button></p>}
      {addFailed && <p role="alert">{error || "The stay could not be added. Your trip is unchanged; refresh the suggestions or review the trip settings."}</p>}
      {query.data && <>{!query.data.suggestions.length && <p>No suitable intermediate cities were found in this catalog. Explore the map to add a different stay.</p>}
        <div className="stop-ideas">{query.data.suggestions.map(idea => <article className="stop-idea" key={idea.destination_id}>
          <h3>{idea.name}</h3><p>{idea.reason}</p><div className="travel-split"><span>{idea.origin} → {idea.name}<strong>{duration(idea.before_minutes)}</strong></span><span>{idea.name} → {idea.destination}<strong>{duration(idea.after_minutes)}</strong></span></div>
          <p><strong>{idea.suggested_nights} nights suggested</strong>{idea.planned_nights != null && ` · ${idea.planned_nights} night(s) allocated in this trip`}<br />{idea.extra_travel_minutes ? `${duration(idea.extra_travel_minutes)} extra travel` : "No extra corridor travel"}{idea.extra_pass_days != null && ` · ${idea.extra_pass_days > 0 ? "+" : ""}${idea.extra_pass_days} estimated rail-pass day(s)`}</p>
          {idea.limitation && <p className="idea-limitation">{idea.limitation}</p>}<button type="button" disabled={busy || !idea.can_add} onClick={async () => { setAddFailed(false); if (await onAdd(idea.destination_id, legIndex+1)) setOpen(false); else setAddFailed(true); }}>Add a stay in {idea.name}</button>
        </article>)}</div><p className="modal-footnote">{query.data.notice}</p></>}
    </Modal></>;
}
