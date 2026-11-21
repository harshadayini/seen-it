/**
 * Screen 2, Results: your video on the left, the items found on the right (stacked on a phone).
 * While the run is processing it shows real progress ("Found 10 items. Matching 4 of 10.") and
 * each item turns into a card the moment its own state is "done". Every state has a screen:
 * nothing scanned, cannot reach the server, run failed, no items found.
 * A footer shows what is in the cart and leads to it.
 * Boundary: reads the shared store only; "Try again" restarts the whole run with the same video
 * (no per-item backend endpoint exists).
 */
"use client";
import Link from "next/link";
import { useState } from "react";
import { EmptyRun } from "@/components/EmptyRun";
import { ItemCard } from "@/components/ItemCard";
import { RunProgress } from "@/components/RunProgress";
import { VideoPane } from "@/components/VideoPane";
import { fmtPrice } from "@/lib/format";
import { useStore } from "@/lib/store";

/** Full-screen message with one retry action. @param title headline @param body one plain sentence */
function Problem({ title, body, action, onAction }: { title: string; body: string; action: string; onAction: () => void }) {
  return (
    <main id="main" className="screen results">
      <header className="head"><h1 className="h1">{title}</h1><p className="meta">{body}</p></header>
      <button type="button" className="btn primary" onClick={onAction}>{action}</button>
      <Link href="/" className="link">Use a different video</Link>
    </main>
  );
}

/** @returns the Results screen. */
export default function ResultsPage() {
  const { run, error, idle, selectedIds, toggle, lines, total, startedAt, finishedAt, retryRun } = useStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (idle) return <EmptyRun />;
  if (error && !run) {
    return <Problem title="Can't reach the app right now" body="We'll keep trying. You can also try again yourself." action="Try again" onAction={() => window.location.reload()} />;
  }
  if (!run) return <main id="main" className="screen results"><p className="note" role="status">Loading…</p></main>;
  if (run.state === "failed") {
    return <Problem title="We couldn't finish watching this video" body="Nothing was added to your cart." action="Try again" onAction={() => void retryRun()} />;
  }
  if (run.state === "done" && run.items.length === 0) {
    return <Problem title="We didn't find any products in this video" body="Try a video where the products are clearly in view." action="Try again" onAction={() => void retryRun()} />;
  }

  const selected = run.items.find((i) => i.item_id === selectedId) ?? null;
  const firstDone = run.items.find((i) => i.state === "done" && i.crop_path) ?? null;

  return (
    <main id="main" className="screen results">
      <header className="head">
        <h1 className="h1">What we found</h1>
      </header>
      <RunProgress run={run} startedAt={startedAt} finishedAt={finishedAt} />

      <div className="results-grid">
        <VideoPane source={run.source.video_id} item={selected} fallback={firstDone} />
        <ul className="items" aria-label="Items found in your video">
          {run.items.map((it) => (
            <ItemCard
              key={it.item_id}
              item={it}
              selected={it.item_id === selectedId}
              inCart={selectedIds.includes(it.item_id)}
              onSelect={() => setSelectedId(it.item_id)}
              onToggleCart={() => toggle(it.item_id)}
              onRetry={() => void retryRun()}
            />
          ))}
        </ul>
      </div>

      <div className="stickybar">
        <Link
          href="/cart"
          className={`btn primary wide ${lines.length === 0 ? "disabled" : ""}`}
          aria-disabled={lines.length === 0}
          tabIndex={lines.length === 0 ? -1 : undefined}
        >
          <span>{lines.length === 0 ? "Review cart" : `Review cart · ${lines.length} ${lines.length === 1 ? "item" : "items"}`}</span>
          <span className="num">{fmtPrice(total)}</span>
        </Link>
      </div>
    </main>
  );
}
