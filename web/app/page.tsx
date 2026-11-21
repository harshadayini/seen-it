/**
 * Screen 1, Scan (home): the camera-style image with rounded boxes drawn on found items,
 * a maroon top pill bar with the item count, and a bottom sheet to choose Video / Photo / Desk,
 * upload, record, and jump to Results.
 * Boundary: box positions are placeholders (the contract has no bounding boxes yet); record and
 * upload only start a run when the backend is connected, otherwise the screen says so.
 */
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Asset } from "@/components/Asset";
import { ArrowIcon, UploadIcon } from "@/components/Icons";
import { API_URL, BOX_SLOTS } from "@/lib/config";
import { bestCandidate, score } from "@/lib/format";
import { useStore } from "@/lib/store";

type Mode = "Video" | "Photo" | "Desk";

/** @returns the Scan screen. */
export default function ScanPage() {
  const { run, error, startRun, starting, startError } = useStore();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("Video");
  const [link, setLink] = useState("");
  const items = run?.items ?? [];
  const found = items.filter((i) => i.state !== "failed").length;

  /** Starts a real run for the pasted link, then shows the results as they arrive. */
  async function start() {
    if (await startRun(link, "video")) router.push("/results");
  }

  return (
    <main className="screen scan">
      <header className="topbar" role="banner">
        <span className="wordmark">seen it</span>
        <span className="pill-count" aria-live="polite">{run ? `${found} items found` : "Loading"}</span>
      </header>

      <section className="camera" aria-label="Scanned scene">
        <Asset name="scanRoom" className="fill" position="50% 50%" />
        {items.map((it, idx) => {
          const slot = BOX_SLOTS[idx % BOX_SLOTS.length];
          const best = bestCandidate(it);
          const low = it.status === "none";
          const name = String(it.attributes?.category ?? "item");
          return (
            <div
              key={it.item_id}
              className={`box ${low ? "dashed" : ""}`}
              style={{ top: `${slot.top}%`, left: `${slot.left}%`, width: `${slot.w}%`, height: `${slot.h}%` }}
            >
              <span className="box-tag mono">{low ? `${name} ?` : best ? `${name} ${score(best.p_same_product)}` : name}</span>
            </div>
          );
        })}
        <Asset name="stickerCamera" className="sticker" decorative />
        {error && <p className="notice">Couldn&apos;t load the run: {error}</p>}
      </section>

      <section className="sheet" aria-label="Start a scan">
        <div className="segmented" role="group" aria-label="Input type">
          {(["Video", "Photo", "Desk"] as Mode[]).map((m) =>
            m === "Desk" ? (
              <Link key={m} href="/desk" className="seg-btn">{m}</Link>
            ) : (
              <button key={m} type="button" className={`seg-btn ${mode === m ? "on" : ""}`} aria-pressed={mode === m} onClick={() => setMode(m)}>
                {m}
              </button>
            )
          )}
        </div>

        <label className="field">
          <span className="sr-only">Video link</span>
          <input
            type="url"
            inputMode="url"
            placeholder={mode === "Video" ? "Paste a video link" : "Paste a photo link"}
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && start()}
          />
        </label>

        <div className="sheet-row">
          <button type="button" className="btn filled start" onClick={start} disabled={starting}>
            <UploadIcon />
            <span>{starting ? "Finding items…" : "Find items"}</span>
          </button>
          <Link href="/results" className="round filled" aria-label="See results">
            <ArrowIcon />
          </Link>
        </div>
        {!API_URL && <p className="muted-note" role="status">Backend isn&apos;t connected yet, so Results shows the sample run.</p>}
        {startError && <p className="muted-note" role="alert">{startError}</p>}
      </section>
    </main>
  );
}
