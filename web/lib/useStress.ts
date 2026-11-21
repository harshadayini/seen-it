/**
 * useStress: starts a stress run on the backend (POST /stress) and polls it (GET /stress/<id>)
 * every two seconds until it is done or failed. Remembers the id across reloads.
 * Failure handling: errors are surfaced as `error`; results are never invented.
 */
"use client";
import { useCallback, useEffect, useState } from "react";
import { API_URL } from "./config";

export interface StressItemScore {
  found: string[];
  missed: string[];
  extra: string[];
  recall: number;
  latency_s: number;
  error: string | null;
  frame: string;
}

export interface StressCondition {
  id: string;
  name: string;
  blurb: string;
  damage: string;
  degraded: StressItemScore;
}

export interface StressRun {
  stress_id: string;
  state: "processing" | "done" | "failed";
  severity?: "standard" | "extreme";
  steps: { key: string; label: string; state: "waiting" | "running" | "done" | "failed"; note?: string }[];
  baseline: { items: { label: string; category?: string | null }[]; latency_s: number; frame: string } | null;
  conditions: StressCondition[];
  summary: { baseline_items: number; avg_degraded: number; breaking_point: string | null; weakest: { name: string; recall: number }; threshold: number } | null;
  error: string | null;
}

const KEY = "scene-it-stress";

/** @returns the current stress run, a start function, and any error. */
export function useStress() {
  const [id, setId] = useState<string | null>(null);
  const [run, setRun] = useState<StressRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(KEY);
      if (saved) setId(saved);
    } catch {}
  }, []);

  useEffect(() => {
    if (!id || !API_URL) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    async function tick() {
      try {
        const res = await fetch(`${API_URL}/stress/${id}`, { cache: "no-store" });
        if (res.status === 404) {
          try { sessionStorage.removeItem(KEY); } catch {}
          if (alive) { setId(null); setRun(null); }
          return;
        }
        if (!res.ok) throw new Error(`Stress request failed (${res.status})`);
        const data: StressRun = await res.json();
        if (!alive) return;
        setRun(data);
        setError(null);
        if (data.state === "processing") timer = setTimeout(tick, 2000);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : "Could not load the stress run");
        timer = setTimeout(tick, 4000);
      }
    }
    tick();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);

  /** Start a stress run for a link or an absolute file path. @returns true if it started. */
  const start = useCallback(async (source: string, severity: "standard" | "extreme" = "standard") => {
    setError(null);
    if (!API_URL) {
      setError("The backend isn't connected, so the stress test can't run.");
      return false;
    }
    const video = source.trim().replace(/^["']|["']$/g, "");
    if (!video) {
      setError("Add a video first: drop a file or paste a link.");
      return false;
    }
    setStarting(true);
    try {
      const res = await fetch(`${API_URL}/stress`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ video, severity }) });
      if (!res.ok) throw new Error(`Could not start the stress test (${res.status})`);
      const data: { stress_id: string } = await res.json();
      try { sessionStorage.setItem(KEY, data.stress_id); } catch {}
      setRun(null);
      setId(data.stress_id);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the stress test");
      return false;
    } finally {
      setStarting(false);
    }
  }, []);

  /** Upload a local file, then start a stress run on the saved copy. */
  const startWithFile = useCallback(async (file: File, severity: "standard" | "extreme" = "standard") => {
    setError(null);
    if (!API_URL) { setError("The backend isn't connected, so files can't be uploaded."); return false; }
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await fetch(`${API_URL}/upload`, { method: "POST", body });
      if (!res.ok) throw new Error(`Upload failed (${res.status})`);
      const saved: { path: string } = await res.json();
      return await start(saved.path, severity);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
      return false;
    }
  }, [start]);

  return { run, error, starting, start, startWithFile };
}
