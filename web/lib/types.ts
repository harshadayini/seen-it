/**
 * Types mirroring contracts/run.schema.json (the shared data contract).
 * Boundary: types only. Changing the contract needs approval from all three teammates.
 */

export type RunState = "processing" | "done" | "failed";
export type MatchStatus = "exact" | "similar" | "none";

export interface Candidate {
  upid?: string | null;
  variant_id?: string | null;
  title: string;
  merchant_domain?: string | null;
  price?: number | null;
  currency?: string | null;
  image_url?: string | null;
  /** The merchant's own product page (added by matching; optional). */
  product_url?: string | null;
  p_same_product?: number | null;
  p_same_variant?: number | null;
}

export interface Item {
  item_id: string;
  state: RunState;
  t_start?: number | null;
  t_end?: number | null;
  crop_path?: string | null;
  /** OPTIONAL contract extension (not in run.schema.json yet): the full source frame the item was found in. */
  frame_path?: string | null;
  /** OPTIONAL contract extension: [ymin, xmin, ymax, xmax] on that frame, each 0..1. */
  bbox?: number[] | null;
  description?: string | null;
  attributes?: Record<string, unknown> | null;
  query?: string | null;
  candidates?: Candidate[];
  status?: MatchStatus | null;
  recovered?: boolean | null;
  preview?: { image_path?: string | null; fidelity?: number | null; regenerated?: boolean | null } | null;
  cart?: { cart_id?: string | null; continue_url?: string | null } | null;
}

export interface Run {
  run_id: string;
  state: RunState;
  mode: "video" | "desk";
  source: { video_id?: string | null; duration_s?: number | null; budget_usd?: number | null };
  items: Item[];
  totals: { price?: number | null; within_budget?: boolean | null };
}
