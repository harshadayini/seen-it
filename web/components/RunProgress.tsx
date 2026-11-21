/**
 * RunProgress: one line of real progress for the Results screen, derived from the run itself.
 * "Watching the video..." (no items yet) -> "Found 10 items. Matching 4 of 10." -> "Found 10 items."
 * plus elapsed seconds. Boundary: presentational; it only reads the run snapshot and two
 * timestamps from the store. Never shows a made-up number: with no start time it omits the seconds.
 */
"use client";
import { useEffect, useState } from "react";
import { progressCounts } from "@/lib/format";
import type { Run } from "@/lib/types";

interface Props {
  run: Run;
  /** Epoch ms the run was started from this page, or null (page reloaded). */
  startedAt: number | null;
  /** Epoch ms the run was first seen finished, or null while still processing. */
  finishedAt: number | null;
}

/** @returns the status line with a bar once items exist. Side effect: a 1 s timer while processing. */
export function RunProgress({ run, startedAt, finishedAt }: Props) {
  const running = run.state === "processing";
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);

  const { total, finished } = progressCounts(run.items);
  const end = running ? now : finishedAt ?? null;
  const secs = startedAt != null && end != null ? Math.max(0, Math.round((end - startedAt) / 1000)) : null;

  const what = running
    ? total === 0
      ? "Watching the video…"
      : `Found ${total} ${total === 1 ? "item" : "items"}. Matching ${finished} of ${total}.`
    : `Found ${total} ${total === 1 ? "item" : "items"}.`;

  return (
    <div className="runstatus" role="status" aria-live="polite">
      <div className="runline">
        <p className="what">
          {running && <span className="dot" aria-hidden="true" />}
          {what}
        </p>
        {secs != null && <p className="secs num">{running ? `${secs} s` : `Took ${secs} s`}</p>}
      </div>
      {running && total > 0 && (
        <div className="progress" aria-hidden="true">
          <i style={{ width: `${Math.round((finished / total) * 100)}%` }} />
        </div>
      )}
    </div>
  );
}
