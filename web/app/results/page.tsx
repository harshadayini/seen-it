/**
 * Screen 2, Results: your video on the left, the items found on the right (stacked on a phone).
 * While the run is processing it shows real progress ("Found 10 items. Matching 4 of 10.") and
 * each item turns into a card the moment its own state is "done". Every state has a screen:
 * nothing scanned, cannot reach the server, run failed, no items found.
 * Items are grouped by verdict; clicking one opens a slide-over with the details. A footer bar
 * shows what is in the cart and leads to it.
 * Boundary: reads the shared store only; "Try again" restarts the whole run with the same video
 * (no per-item backend endpoint exists).
 */
"use client";
import Link from "next/link";
import { useState } from "react";
import { EmptyRun } from "@/components/EmptyRun";
import { ItemCard } from "@/components/ItemCard";
import { ItemPanel } from "@/components/ItemPanel";
import { SeeItHere } from "@/components/SeeItHere";
import { RunProgress } from "@/components/RunProgress";
import { VideoPane } from "@/components/VideoPane";
import { bestCandidate, fmtPrice } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Item } from "@/lib/types";

/** Groups items so the list reads top to bottom: still checking, then exact, close, none, failed. */
function groupItems(items: Item[]) {
  const failed = (i: Item) => i.state === "failed" || (i.state === "done" && !i.status);
  return [
    { key: "checking", title: "Checking", items: items.filter((i) => i.state === "processing") },
    { key: "exact", title: "Exact matches", items: items.filter((i) => i.state === "done" && i.status === "exact") },
    { key: "similar", title: "Close matches", items: items.filter((i) => i.state === "done" && i.status === "similar") },
    { key: "none", title: "No confident match", items: items.filter((i) => i.state === "done" && i.status === "none") },
    { key: "failed", title: "Couldn't check", items: items.filter(failed) },
  ].filter((g) => g.items.length > 0);
}

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
  const [panelOpen, setPanelOpen] = useState(false);
  const [seeItOpen, setSeeItOpen] = useState(false);

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
        <div className="groups">
          {groupItems(run.items).map((g) => (
            <section key={g.key} aria-labelledby={`g-${g.key}`}>
              <h2 id={`g-${g.key}`} className="grp-h">{g.title} <span className="num">{g.items.length}</span></h2>
              <ul className="items">
                {g.items.map((it) => (
                  <ItemCard
                    key={it.item_id}
                    item={it}
                    selected={it.item_id === selectedId}
                    inCart={selectedIds.includes(it.item_id)}
                    onSelect={() => { setSelectedId(it.item_id); setPanelOpen(true); }}
                    onToggleCart={() => toggle(it.item_id)}
                    onRetry={() => void retryRun()}
                  />
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>

      <div className="cartbar">
        <p className="cartbar-text" role="status">
          {lines.length === 0 ? "Nothing in your cart yet" : <>{lines.length} {lines.length === 1 ? "item" : "items"} in your cart · <span className="num">{fmtPrice(total)}</span></>}
        </p>
        <Link
          href="/cart"
          className={`btn primary ${lines.length === 0 ? "disabled" : ""}`}
          aria-disabled={lines.length === 0}
          tabIndex={lines.length === 0 ? -1 : undefined}
        >
          Review cart
        </Link>
      </div>

      {panelOpen && selected && selected.state === "done" && (
        <ItemPanel
          item={selected}
          inCart={selectedIds.includes(selected.item_id) && !!bestCandidate(selected)}
          onToggleCart={() => toggle(selected.item_id)}
          onClose={() => setPanelOpen(false)}
          onSeeIt={() => setSeeItOpen(true)}
        />
      )}

      {seeItOpen && selected && selected.state === "done" && (
        <SeeItHere
          runId={run.run_id}
          item={selected}
          inCart={selectedIds.includes(selected.item_id)}
          onToggleCart={() => toggle(selected.item_id)}
          onClose={() => setSeeItOpen(false)}
        />
      )}
    </main>
  );
}
