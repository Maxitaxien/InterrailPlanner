"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import Modal from "./Modal";

type Source = { id: string; title: string; url: string; kind: string; retrieved_at: string | null };
type SavedIdeas = { id: string; saved_at: string; cached: boolean; source: string; model: string | null; introduction: string; warning: string; web_used: boolean; web_status: string; web_query?: string; query_plan?: { query: string; model: string | null; source: string; status: string }; query_plan_cached?: boolean; generation_status?: string; sources: Source[]; request: { question: string; model?: string; use_web?: boolean; research_focus_input?: string; travel_context?: { scope: string; periods: { month: string; year: number; season: string }[] } | null }; ideas: { title: string; description: string; why_for_you: string; time_minutes: number; best_time: string; source_ids: string[]; evidence?: { source_id: string; quote: string }[] }[] };
type History = { sets: SavedIdeas[]; default_model: string; web_available: boolean };

export default function CityIdeas({ destinationId, name, tripId, token, itineraryId }: { destinationId: string; name: string; tripId?: string; token?: string; itineraryId?: string }) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("A relaxed honeymoon day with good food, culture and a few quieter spots.");
  const [model, setModel] = useState("");
  const [researchFocus, setResearchFocus] = useState("");
  const [selected, setSelected] = useState("");
  const [showSaved, setShowSaved] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const initialized = useRef("");
  const client = useQueryClient();
  const key = ["city-ideas", tripId, destinationId, token];
  const path = `trips/${tripId}/cities/${destinationId}/ideas`;
  const history = useQuery({ queryKey: key, queryFn: () => api<History>(path, "GET", undefined, token), enabled: open && !!tripId && !!token, staleTime: 60000, retry: false, refetchOnWindowFocus: false });
  const pending = busy || deleting;
  function restoreRequest(item: SavedIdeas) {
    setQuestion(item.request.question); setModel(item.request.model || "");
    setResearchFocus(item.request.research_focus_input || "");
  }
  useEffect(() => {
    const scope = `${tripId}/${destinationId}/${token}`;
    if (open && history.data && initialized.current !== scope) {
      initialized.current = scope;
      if (history.data.sets[0]) restoreRequest(history.data.sets[0]);
    }
  }, [open, history.data, tripId, destinationId, token]);
  async function generate(refresh: boolean) {
    setBusy(true); setError(""); setNotice("");
    let chosen = model;
    try { chosen ||= localStorage.getItem("interrail:llm-model") || ""; } catch { /* Server default remains available. */ }
    try {
      const result = await api<SavedIdeas>(path, "POST", { question, model: chosen || null, research_focus: researchFocus, refresh, ...(itineraryId ? { itinerary_id: itineraryId } : {}) }, token);
      client.setQueryData<History>(key, old => ({ sets: [result, ...(old?.sets || []).filter(item => item.id !== result.id)].slice(0, 20), default_model: old?.default_model || "", web_available: old?.web_available || false }));
      setSelected(result.id);
      setShowSaved(true);
      setNotice("New ideas saved to your trip. Reopening will not generate or search again.");
    } catch (failure) { setError((failure as Error).message); }
    finally { setBusy(false); }
  }
  async function remove(id: string) {
    setDeleting(true); setError(""); setNotice("");
    try {
      await api(`${path}/${id}`, "DELETE", undefined, token);
      client.setQueryData<History>(key, old => old ? { ...old, sets: old.sets.filter(item => item.id !== id) } : old);
      if (selected === id) setSelected("");
      setConfirmDelete("");
      setNotice("Saved recommendations deleted. Your prompt is unchanged. No inference or search was run.");
      // Reveal older entries if the previous history response reached its 20-entry limit.
      await client.invalidateQueries({ queryKey: key });
    } catch (failure) { setError((failure as Error).message); }
    finally { setDeleting(false); }
  }
  return <div className="city-ideas">
    <button type="button" className="leg-action" disabled={!tripId || !token} onClick={() => { setShowSaved(false); setSelected(""); setConfirmDelete(""); setOpen(true); }}>Things to do in {name}</button>
    {!tripId && <small>Create a trip first to save city ideas.</small>}
    <Modal open={open} onClose={() => setOpen(false)} title={`Things to do in ${name}`}>
      <p>The same selected local model first plans a targeted query, then reads fresh web search excerpts and answers your question. Planned visit dates help tailor ideas to the month and season when available. Every request is saved as a new version. Opening this dialog only loads saved ideas.</p>
      <label>What would you like to do?<textarea rows={3} maxLength={600} value={question} disabled={pending || history.isPending} onChange={event => setQuestion(event.target.value)} /></label>
      <details><summary>Model & web research</summary>
        <label>Ollama model for city ideas<input value={model} disabled={pending} onChange={event => setModel(event.target.value)} placeholder={history.data?.default_model || "Use AI settings or server default"} /></label>
        <small>Blank uses the model saved in AI settings, then the server default.</small>
        <small>Every Generate or Regenerate plans a query and runs a fresh web search, even for the same prompt. Opening saved results never searches. Only the generated query goes to search engines; it can include interests and, when relevant, a planned month, season or year. Exact visit dates stay local. Keep private details out of your request. Full trip records and edit tokens are not given to the query planner. Inference stays local.</small>
        <label>Research focus · sent to search engines<input maxLength={120} value={researchFocus} disabled={pending} placeholder="Let the model plan from your question, or give public search keywords" onChange={event => setResearchFocus(event.target.value)} /></label><small>Optional public keywords only—no personal information. Blank lets the selected model create a query from your question, without fixed topic rules.</small>
      </details>
      {history.data && !history.data.web_available && <p role="status">City recommendations require SearXNG. Start the search service to generate new ideas. Your saved versions are still available below.</p>}
      <div className="modal-actions"><button type="button" className="primary city-generate" aria-busy={busy} disabled={pending || !tripId || !token || question.trim().length < 3 || history.isPending || !!history.error || !history.data?.web_available} onClick={() => generate(false)}>{!busy && <span aria-hidden="true">✦ </span>}{busy ? "Planning, researching & saving…" : "Generate & save ideas"}</button>
        {!!history.data?.sets.length && <button type="button" disabled={pending || question.trim().length < 3 || !!history.error || !history.data?.web_available} onClick={() => generate(true)}>Regenerate & save new version</button>}
      </div>
      {notice && <p role="status">{notice}</p>}{error && <p role="alert">{error}</p>}
      {history.isPending && <p>Loading saved city ideas…</p>}
      {history.error && <p role="alert">{history.error.message} <button type="button" onClick={() => history.refetch()}>Retry saved ideas</button></p>}
      {history.data && !history.data.sets.length && <p>No saved ideas for {name} yet. Nothing is generated until you ask.</p>}
      {!!history.data?.sets.length && <>
        <button type="button" className="saved-recommendations-toggle" aria-expanded={showSaved} onClick={() => setShowSaved(value => !value)}>Saved recommendations ({history.data.sets.length})</button>
        {showSaved && <div className="saved-recommendations-list" aria-label={`Saved recommendation versions for ${name}`}>
          {history.data.sets.map(item => <div className="saved-recommendation" key={item.id}>
            <button type="button" className="saved-recommendation-title" aria-expanded={selected === item.id} onClick={() => setSelected(current => current === item.id ? "" : item.id)}>{item.request.question.length > 100 ? `${item.request.question.slice(0, 100)}…` : item.request.question}<small>{new Date(item.saved_at).toLocaleString()} · {item.model || (item.source === "web_research" ? "Saved search leads" : "Curated fallback")}</small></button>
            <div className="modal-actions">
              <button type="button" disabled={pending} onClick={() => { restoreRequest(item); setNotice("Saved prompt copied into the editor. Nothing was generated."); }}>Use this prompt</button>
              <button type="button" disabled={pending} onClick={() => setConfirmDelete(item.id)}>Delete saved recommendations</button>
            </div>
            {confirmDelete === item.id && <div role="group" aria-label="Confirm deletion">
              <p>Permanently delete this saved version? Other versions and your current prompt will be kept.</p>
              <div className="modal-actions"><button type="button" disabled={pending} onClick={() => setConfirmDelete("")}>Keep saved version</button><button type="button" className="danger-action" disabled={pending} onClick={() => remove(item.id)}>{deleting ? "Deleting…" : "Permanently delete version"}</button></div>
            </div>}
            {selected === item.id && <SavedRecommendation ideas={item} name={name} />}
          </div>)}
        </div>}
      </>}
    </Modal>
  </div>;
}

function SavedRecommendation({ ideas, name }: { ideas: SavedIdeas; name: string }) {
  return <section className="saved-city-ideas" aria-label={`Saved ideas for ${name}`}>
        <p className="caption">Saved {new Date(ideas.saved_at).toLocaleString()} · {ideas.source === "ollama" ? `Local AI · ${ideas.model}` : ideas.source === "web_research" ? "Saved search leads · not AI recommendations" : "Curated fallback · local AI unavailable"}{ideas.web_used ? " · includes web excerpts" : " · no web evidence used"}</p>
        {ideas.source !== "ollama" && ideas.generation_status && <p className="caption">{ideas.generation_status === "invalid_response" ? "The model answer failed format or citation checks; this does not mean the search found nothing." : ideas.generation_status === "timeout" ? "Local AI timed out." : "Local AI could not be reached."}</p>}
        <p className="caption">Saved request: {ideas.request.question}</p><p>{ideas.introduction}</p>
        {ideas.request.travel_context && <p className="caption">Timing used: {ideas.request.travel_context.periods.map(period => `${period.month} ${period.year} (${period.season})`).join(" · ")} · {ideas.request.travel_context.scope === "city_visit" ? "planned city visit" : "overall trip window; city visit dates not set"}. Recheck seasonal opening and event dates.</p>}
        {!ideas.ideas.length && <p className="empty-city-ideas">No concrete recommendations this time. Try refining your question or generating again—we won’t fill the list with generic activities.</p>}
        {ideas.ideas.map((idea, index) => <article key={index}><h3>{idea.title}</h3><small>{ideas.source === "web_research" ? "Search result · confirm relevance and details before planning" : `Allow ~${idea.time_minutes} min · ${idea.best_time} · unverified idea`}</small><p>{idea.description}</p><p className="booking-hint">{idea.why_for_you}</p>
          {!!idea.source_ids.length && <div className="booking-links">{idea.source_ids.map(id => { const source = ideas.sources.find(item => item.id === id); return source ? <a key={id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a> : null; })}</div>}
          {!!idea.evidence?.length && <details><summary>Supporting search excerpts · not full-page verification</summary>{idea.evidence.map((evidence, i) => <blockquote key={i}>{evidence.quote}</blockquote>)}</details>}
        </article>)}
        {ideas.web_status === "unavailable" && <p>The web search failed. These saved ideas have no web evidence; regenerate explicitly to retry.</p>}
        <p className="booking-hint">{ideas.warning} References are for follow-up, not proof of the model’s claims.</p>
        {ideas.web_query && <p className="caption">Saved search query: {ideas.web_query}</p>}
        {ideas.query_plan && <p className="caption">{ideas.query_plan.source === "local_model" ? `Query planned locally by ${ideas.query_plan.model}.` : `Query planning ${ideas.query_plan.status === "timeout" ? "timed out" : "was unavailable or invalid"}; a generic city-only search was used, not a targeted query.`}</p>}
        {!!ideas.sources.length && <details><summary>Saved references & research dates</summary>{ideas.sources.map(source => <p key={source.id}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a><small>{source.retrieved_at ? `Search excerpt retrieved ${new Date(source.retrieved_at).toLocaleString()}` : "Curated reference · not fetched for this request"}</small></p>)}</details>}
      </section>;
}
