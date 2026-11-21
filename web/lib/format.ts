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

/**
 * Tidy a marketplace product title for display. Shopify titles often carry SEO text after a
 * separator ("... | Free Shipping"), spec lists in brackets and shouting capitals.
 * @param title raw catalog title @param max visible character budget @returns a short, clean title
 */
const ACRONYMS = new Set(["LG", "IPS", "LED", "LCD", "OLED", "FHD", "UHD", "HD", "HDR", "HDMI", "USB", "RGB", "TV", "PC", "UV", "AI", "4K", "8K", "5G"]);

export function cleanTitle(title: string | null | undefined, max = 54): string {
  let t = (title ?? "").replace(/&amp;/g, "&").replace(/\s+/g, " ").trim();
  if (!t) return "Item";
  const first = t.split(/\s+[|–—]\s+|\s+-\s+/)[0];
  if (first.length >= 8) t = first;
  t = t.replace(/\s*[[(][^\])]*[\])]/g, "").replace(/\s{2,}/g, " ").trim();
  const letters = t.replace(/[^A-Za-z]/g, "");
  if (letters.length > 6 && letters === letters.toUpperCase()) {
    // Shouting capitals: title-case the words but keep well-known acronyms in capitals.
    t = t.split(" ").map((w) => (ACRONYMS.has(w.replace(/[^A-Za-z0-9]/g, "")) ? w : w.charAt(0) + w.slice(1).toLowerCase())).join(" ");
  }
  if (t.length <= max) return t;
  const cut = t.slice(0, max).replace(/\s+\S*$/, "");
  return `${cut.replace(/[,;:\-–]+$/, "")}…`;
}

/** Readable title from a video id: "v_roomtour_01" -> "Roomtour 01". */
export function humanize(id: string | null | undefined): string {
  if (/^https?:\/\//i.test(id ?? "")) return "Your video";
  const words = (id ?? "").split("_").filter((w) => w && w !== "v");
  if (words.length === 0) return "Your video";
  const s = words.join(" ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Parses a YouTube link (watch, youtu.be, shorts or embed) into its video id.
 * @param src the source the user pasted (a link or a local path)
 * @returns { id, vertical } or null when it is not a YouTube link. vertical is true for Shorts.
 */
export function youtubeId(src: string | null | undefined): { id: string; vertical: boolean } | null {
  const m = (src ?? "").match(/^https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/(shorts\/|watch\?(?:.*&)?v=|embed\/)|youtu\.be\/)([A-Za-z0-9_-]{11})/i);
  return m ? { id: m[2], vertical: (m[1] ?? "").toLowerCase() === "shorts/" } : null;
}

/** Plain-word match label: "Exact match", "Close match" or "No confident match" (never a score). */
export function matchWords(s: MatchStatus | null | undefined): string {
  return s === "exact" ? "Exact match" : s === "similar" ? "Close match" : "No confident match";
}

/** How many items have finished (done or failed) out of the total, for "Matching 4 of 10". */
export function progressCounts(items: Item[]): { total: number; finished: number } {
  return { total: items.length, finished: items.filter((i) => i.state !== "processing").length };
}
