/**
 * useRun: loads a run and keeps polling about once per second while it is "processing" so items
 * appear as they finish (CLAUDE.md 15d).
 * Source: with a backend (NEXT_PUBLIC_API_URL) and a run id, GET {API}/run/<id>; otherwise the
 * shared fixture via /api/run so the UI always has something real-shaped to show.
 * Failure handling: errors surface as `error`, never as fabricated data.
 */
"use client";
import { useEffect, useState } from "react";
import { API_URL } from "./config";
import type { Run } from "./types";

/**
 * @param runId id returned by POST /run, or null to show the fixture
 * @returns { run, error } latest run snapshot and any fetch error
 * Side effects: starts/stops a 1s polling timer.
 */
export function useRun(runId?: string | null) {
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const url = API_URL && runId ? `${API_URL}/run/${runId}` : "/api/run";

    async function tick() {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) throw new Error(`Run request failed (${res.status})`);
        const data: Run = await res.json();
        if (!alive) return;
        setRun(data);
        setError(null);
        if (data.state === "processing") timer = setTimeout(tick, 1000);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "Could not load run");
        timer = setTimeout(tick, 3000);
      }
    }
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [runId]);

  return { run, error };
}
