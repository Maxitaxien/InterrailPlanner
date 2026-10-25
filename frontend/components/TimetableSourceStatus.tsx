"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Source = { provider: string; status: string; message: string; environment?: string };
export default function TimetableSourceStatus() {
  const [sources, setSources] = useState<Source[]>([]);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    api<{ sources: Source[] }>("travel/timetable-sources").then(result => { if (active) setSources(result.sources); }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);
  return <div className="provider-recommendation"><h3>Timetable connections</h3>
    <p>This check reads local configuration. Searches contact a provider only when you request them.</p>
    {failed && <p>Connection status unavailable. Check the backend.</p>}
    {sources.map(source => <p key={source.provider}><strong>{source.provider === "allaboard" ? "All Aboard" : source.provider === "ferryhapi" ? "FerryhAPI" : "Self-hosted MOTIS"} · {source.status.replaceAll("_", " ")}{source.environment ? ` (${source.environment})` : ""}</strong><br />{source.message}</p>)}
  </div>;
}
