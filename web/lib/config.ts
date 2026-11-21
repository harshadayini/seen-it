/**
 * Front-end config: every tunable value for the UI lives here (no magic numbers in components).
 * Boundary: display settings only. Match thresholds belong to the backend (CLAUDE.md section 4).
 */

/** Backend base URL. When unset the UI runs against the shared fixture. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

/**
 * Spline 3D scenes. Paste a published scene URL (ends in .splinecode) to switch a slot on.
 * An empty string keeps the labelled placeholder, so the app works without any scene.
 */
export const SPLINE_SCENES = {
  /** Floating object on the Scan screen. */
  hero: "",
  /** Object above the Cart. */
  cart: "",
} as const;

/**
 * URL for a backend-written file such as an item crop (`frames/<run_id>/<item_id>.jpg`).
 * The backend serves these from /frames (and /previews). Without a backend it resolves to a
 * path that 404s, and the UI falls back to a placeholder.
 */
export function fileUrl(path: string): string {
  return `${API_URL}/${path.replace(/^\/+/, "")}`;
}

/**
 * Preview fidelity at or above which the UI says "check passed".
 * PLACEHOLDER until the backend returns an explicit pass/fail flag with the preview.
 */
export const PREVIEW_PASS_FIDELITY = 0.8;

/**
 * Where item boxes sit on the Scan image (percent of the image). PLACEHOLDER positions:
 * the run contract has no bounding boxes yet, so boxes are laid out by item order.
 */
export const BOX_SLOTS = [
  { top: 22, left: 8, w: 36, h: 70 },
  { top: 60, left: 46, w: 30, h: 28 },
  { top: 50, left: 80, w: 16, h: 17 },
  { top: 64, left: 14, w: 26, h: 18 },
] as const;

/** Object-position values used to fake circular "crops" of the scan image until real crops exist. */
export const CROP_POSITIONS = ["18% 62%", "58% 66%", "68% 32%", "28% 78%"] as const;

/** Sample values for the Desk screen layout (the contract has no desk data yet). */
export const DESK_SAMPLE = {
  budget: 150,
  picks: [
    { name: "Brass desk lamp", price: 58, style: 0.86, space: 0.81, category: "desk" },
    { name: "Speckled bud vase", price: 32, style: 0.79, space: 0.9, category: "decor" },
    { name: "Wool desk rug", price: 34, style: 0.74, space: 0.77, category: "rugs" },
  ],
} as const;
