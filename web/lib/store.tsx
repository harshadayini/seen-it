/**
 * Shared app state for all five screens: the current run, which items are in the cart,
 * and per-merchant checkout links.
 * Use cases: Results toggles items, See it here adds one, Cart groups by merchant and asks the
 * backend (POST /cart) for one cart per merchant.
 * Invariants: never fabricates a continue_url; with no backend it says so instead of faking carts.
 */
"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { API_URL } from "./config";
import { bestCandidate } from "./format";
import type { Candidate, Item, Run } from "./types";
import { useRun } from "./useRun";

export interface CartLine {
  item: Item;
  candidate: Candidate;
}

interface Store {
  run: Run | null;
  error: string | null;
  /** True when a backend is connected but nothing has been scanned yet (no sample is shown). */
  idle: boolean;
  /** Start a run on the backend for a video link; resolves true if it started. */
  startRun: (video: string, mode?: "video" | "desk") => Promise<boolean>;
  starting: boolean;
  startError: string | null;
  /** Items that have a purchasable match (exact or similar with a variant id). */
  purchasable: Item[];
  selectedIds: string[];
  toggle: (id: string) => void;
  /** Make exactly these items the cart contents. */
  setOnly: (ids: string[]) => void;
  /** Add one item without removing others. */
  add: (id: string) => void;
  lines: CartLine[];
  byMerchant: Map<string, CartLine[]>;
  total: number;
  urls: Record<string, string | null>;
  buildCarts: () => Promise<void>;
  busy: boolean;
  cartError: string | null;
}

const Ctx = createContext<Store | null>(null);

/** @returns the shared store. Throws if used outside RunProvider. */
export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore must be used inside RunProvider");
  return s;
}

/** Provides run data and cart state to every screen. @param children app content */
export function RunProvider({ children }: { children: React.ReactNode }) {
  const [runId, setRunId] = useState<string | null>(null);
  const { run, error, idle } = useRun(runId);

  // Keep the current run across page reloads (the backend keeps runs in memory).
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem("scene-it-run");
      if (saved) setRunId(saved);
    } catch {}
  }, []);
  useEffect(() => {
    try {
      if (runId) sessionStorage.setItem("scene-it-run", runId);
    } catch {}
  }, [runId]);
  // A saved run the backend no longer knows (it restarted): forget it and start fresh.
  useEffect(() => {
    if (runId && error?.includes("(404)")) {
      try { sessionStorage.removeItem("scene-it-run"); } catch {}
      setRunId(null);
    }
  }, [runId, error]);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[] | null>(null);
  const [urls, setUrls] = useState<Record<string, string | null>>({});
  const [busy, setBusy] = useState(false);
  const [cartError, setCartError] = useState<string | null>(null);

  const purchasable = useMemo(
    () =>
      (run?.items ?? []).filter((i) => {
        const c = bestCandidate(i);
        return (i.status === "exact" || i.status === "similar") && !!c?.variant_id;
      }),
    [run]
  );
  const selectedIds = picked ?? purchasable.map((i) => i.item_id);

  const lines: CartLine[] = useMemo(
    () =>
      purchasable
        .filter((i) => selectedIds.includes(i.item_id))
        .map((item) => ({ item, candidate: bestCandidate(item)! })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [purchasable, picked]
  );
  const byMerchant = useMemo(() => {
    const m = new Map<string, CartLine[]>();
    for (const l of lines) {
      const d = l.candidate.merchant_domain ?? "unknown";
      m.set(d, [...(m.get(d) ?? []), l]);
    }
    return m;
  }, [lines]);
  const total = lines.reduce((a, l) => a + (l.candidate.price ?? 0), 0);

  const toggle = useCallback(
    (id: string) => setPicked((p) => {
      const cur = p ?? purchasable.map((i) => i.item_id);
      return cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
    }),
    [purchasable]
  );
  const setOnly = useCallback((ids: string[]) => setPicked(ids), []);
  const add = useCallback(
    (id: string) => setPicked((p) => {
      const cur = p ?? purchasable.map((i) => i.item_id);
      return cur.includes(id) ? cur : [...cur, id];
    }),
    [purchasable]
  );

  /**
   * Starts a real run on the backend (POST /run) for a video link or path, then follows it.
   * Side effects: network call; resets the cart selection. Sets startError on failure.
   */
  const startRun = useCallback(async (video: string, mode: "video" | "desk" = "video") => {
    setStartError(null);
    if (!API_URL) {
      setStartError("The backend isn't connected yet, so this is still showing the sample run.");
      return false;
    }
    // Windows "Copy as path" wraps the path in quotes; strip them.
    const source = video.trim().replace(/^["']|["']$/g, "");
    if (!source) {
      setStartError("Paste a video link or file path first.");
      return false;
    }
    setStarting(true);
    try {
      const res = await fetch(`${API_URL}/run`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ video: source, mode }),
      });
      if (!res.ok) throw new Error(`Starting the run failed (${res.status})`);
      const data: Run = await res.json();
      setPicked(null);
      setUrls({});
      setRunId(data.run_id);
      return true;
    } catch (e) {
      setStartError(e instanceof Error ? e.message : "Could not start the run");
      return false;
    } finally {
      setStarting(false);
    }
  }, []);

  /** Asks the backend for one cart per merchant. Side effect: POST /cart. */
  const buildCarts = useCallback(async () => {
    setCartError(null);
    if (!API_URL || !run) {
      setCartError("The backend isn't connected yet, so no real carts can be created.");
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${API_URL}/cart`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ run_id: run.run_id, item_ids: lines.map((l) => l.item.item_id) }),
      });
      if (!res.ok) throw new Error(`Cart request failed (${res.status})`);
      const data: { carts: { merchant_domain: string; continue_url: string | null }[] } = await res.json();
      setUrls(Object.fromEntries(data.carts.map((c) => [c.merchant_domain, c.continue_url])));
    } catch (e) {
      setCartError(e instanceof Error ? e.message : "Cart failed");
    } finally {
      setBusy(false);
    }
  }, [run, lines]);

  const value: Store = { run, error, idle, startRun, starting, startError, purchasable, selectedIds, toggle, setOnly, add, lines, byMerchant, total, urls, buildCarts, busy, cartError };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
