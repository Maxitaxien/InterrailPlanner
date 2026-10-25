"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../lib/api";
type Recommendation = { id: string; destination_id: string; name: string; description: string; reason: string; source: string };
type Result = { source: string; model: string | null; cached: boolean; recommendations: Recommendation[]; warning: string };
export default function RecommendationPanel({ itineraryId, token }: { itineraryId: string; token: string }) {
  const [model, setModel] = useState("");
  const mutation = useMutation({ mutationFn: () => api<Result>(`itineraries/${itineraryId}/recommendations`, "POST", { model: model || localStorage.getItem("interrail:llm-model") || null }, token) });
  return <section className="recommendations"><h3>Make time for the good bits.</h3><p>Rank curated ideas around your interests. Local AI is optional; curated suggestions remain available when it is offline.</p><details><summary>Model for this request</summary><label>Ollama model · optional<input value={model} onChange={e => setModel(e.target.value)} placeholder="Use model from settings" /></label></details>
    <button disabled={mutation.isPending || !token} onClick={() => mutation.mutate()}>{mutation.isPending ? "Finding ideas… local inference may take a moment" : "Find ideas for this route"}</button>
    {mutation.error && <p role="alert">{mutation.error.message}</p>}
    {mutation.data && <><p className="caption">{mutation.data.source === "ollama" ? `Ranked by ${mutation.data.model}${mutation.data.cached ? " · cached" : ""}` : "Curated ranking · local AI unavailable"}</p><div className="idea-grid">{mutation.data.recommendations.map(r => <article key={r.id}><small>{r.destination_id.toUpperCase()}</small><h4>{r.name}</h4><p>{r.description}</p><small>{r.reason}</small></article>)}</div><p className="caption">{mutation.data.warning}</p></>}
  </section>;
}
