/**
 * ConfidencePill: Exact (filled ink), Similar (outlined), No match (dashed), with the score.
 * Boundary: presentational. Status is always carried by words, never colour alone, and "No
 * match" is shown honestly rather than styled as a result.
 */
import type { MatchStatus } from "@/lib/types";
import { score, statusLabel } from "@/lib/format";

/** @param status match status @param p best p_same_product */
export function ConfidencePill({ status, p }: { status?: MatchStatus | null; p?: number | null }) {
  const cls = status ?? "pending";
  return (
    <span className={`pill ${cls}`}>
      {statusLabel(status)}
      {status && status !== "none" && p != null && <span className="num"> {score(p)}</span>}
    </span>
  );
}
