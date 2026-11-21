/**
 * Small display helpers (time, money, percent, status labels, names).
 * Pure functions, no side effects, no network.
 */
import type { Item, MatchStatus } from "./types";

/** Formats seconds as m:ss. @param s seconds @returns e.g. "1:04" */
export function fmtTime(s: number | null | undefined): string {
  if (s == null) return "–";
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

/**
 * Time label for an item. Argon returns one best moment (t_start equals t_end), so show a single
 * time then; show a range only when the two differ. @returns e.g. "0:12" or "0:12–0:15"
 */
export function fmtRange(a: number | null | undefined, b: number | null | undefined): string {
  if (a == null) return "–";
  return b == null || b === a ? fmtTime(a) : `${fmtTime(a)}–${fmtTime(b)}`;
}

/** Formats a price. @param n amount @param cur currency code @returns e.g. "$129" */
export function fmtPrice(n: number | null | undefined, cur?: string | null): string {
  if (n == null) return "–";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: cur || "USD", maximumFractionDigits: 0 }).format(n);
}

/** Formats a 0..1 probability as a whole percent. */
export function pct(p: number | null | undefined): string {
  return p == null ? "–" : `${Math.round(p * 100)}%`;
}

/** Formats a 0..1 score with two decimals, e.g. 0.91. */
export function score(p: number | null | undefined): string {
  return p == null ? "–" : p.toFixed(2);
}

/** Human label for a match status (honest wording for "none"). */
export function statusLabel(s: MatchStatus | null | undefined): string {
  return s === "exact" ? "Exact" : s === "similar" ? "Similar" : s === "none" ? "No match" : "Looking";
}

/** Best candidate for an item (highest p_same_product), or undefined. */
export function bestCandidate(item: Item) {
  return [...(item.candidates ?? [])].sort((a, b) => (b.p_same_product ?? 0) - (a.p_same_product ?? 0))[0];
}

/** Shop name from a merchant domain: "lumen-and-oak.myshopify.com" -> "lumen-and-oak". */
export function merchantName(domain: string | null | undefined): string {
  return (domain ?? "unknown").replace(/\.myshopify\.com$/, "");
}

/** Readable title from a video id: "v_roomtour_01" -> "Roomtour 01". */
export function humanize(id: string | null | undefined): string {
  if (/^https?:\/\//i.test(id ?? "")) return "Your video";
  const words = (id ?? "").split("_").filter((w) => w && w !== "v");
  if (words.length === 0) return "Your video";
  const s = words.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}
