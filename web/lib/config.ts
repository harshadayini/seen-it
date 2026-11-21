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

/**
 * Boxes for the SAMPLE scene art only: [ymin, xmin, ymax, xmax], 0..1. The contract has no
 * bounding boxes yet, so real runs show each item's crop as its own frame instead.
 */
export const SAMPLE_BOXES: readonly (readonly [number, number, number, number])[] = [
  [0.2, 0.07, 0.92, 0.38],
  [0.58, 0.46, 0.9, 0.75],
  [0.47, 0.8, 0.69, 0.96],
  [0.78, 0.1, 0.96, 0.44],
];
