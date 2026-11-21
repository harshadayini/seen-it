/**
 * ConfidencePill: Exact (filled maroon), Similar (outlined), No match (dashed), plus the score.
 * Boundary: presentational. "No match" is shown honestly, never styled as a result.
 */
import type { MatchStatus } from "@/lib/types";
import { score, statusLabel } from "@/lib/format";

/** @param status match status @param p best p_same_product */
export function ConfidencePill({ status, p }: { status?: MatchStatus | null; p?: number | null }) {
  const cls = status ?? "pending";
  return (
    <span className={`pill ${cls}`}>
      {statusLabel(status)}
      {status && status !== "none" && p != null && <span className="mono"> {score(p)}</span>}
    </span>
  );
}
