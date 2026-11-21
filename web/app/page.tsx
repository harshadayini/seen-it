/**
 * Screen 1, Scan: a full-bleed scene with an oversized "seen it" wordmark straddling its edge,
 * numbered pins on found items, a short intake (Video / Photo / Desk, a link, one button), a
 * floating 3D object, and a quiet editorial band that shows the before/after and the three
 * outcomes.
 * Boundary: pin positions are placeholders (the contract has no bounding boxes yet). "Find items"
 * only starts a run when the backend is connected; otherwise it says so and Results shows the
 * sample run.
 */
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Asset } from "@/components/Asset";
import { ArrowIcon, BagIcon } from "@/components/Icons";
import { Spline3D } from "@/components/Spline3D";
import { API_URL, BOX_SLOTS, SPLINE_SCENES } from "@/lib/config";
import { useStore } from "@/lib/store";

type Mode = "Video" | "Photo" | "Desk";
const MODES: Mode[] = ["Video", "Photo", "Desk"];

/** @returns the Scan screen. */
export default function ScanPage() {
  const { run, error, startRun, starting, startError, lines } = useStore();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("Video");
  const [link, setLink] = useState("");
  const items = run?.items ?? [];

  /** Starts a real run for the pasted link, then shows results as they arrive. */
  async function start() {
    if (await startRun(link, "video")) router.push("/results");
  }

  return (
    <main id="main" className="scan">
      <header className="nav">
        <span className="nav-logo" aria-hidden="true">s</span>
        <span className="nav-title">{run ? `${items.length} items found` : "seen it"}</span>
        <Link href="/cart" className="nav-cart" aria-label={`Cart, ${lines.length} items`}>
          <BagIcon />
          {lines.length > 0 && <b className="count">{lines.length}</b>}
        </Link>
      </header>

      <section className="hero" aria-label="Scanned scene">
        <div className="hero-img">
          <Asset name="scanRoom" className="fill" />
          {items.map((it, idx) => {
            const slot = BOX_SLOTS[idx % BOX_SLOTS.length];
            return (
              <div
                key={it.item_id}
                className={`pin ${it.status === "none" ? "dashed" : ""}`}
                style={{ top: `${slot.top}%`, left: `${slot.left}%`, width: `${slot.w}%`, height: `${slot.h}%` }}
              >
                <span className="pin-n num">{idx + 1}</span>
              </div>
            );
          })}
          {error && <p className="note on-image">Couldn&apos;t load the run: {error}</p>}
        </div>
        <h1 className="wordmark">seen it</h1>
      </section>

      <section className="intro" aria-label="Start a scan">
        <Spline3D scene={SPLINE_SCENES.hero} className="object" />
        <h2 className="h1">Every video becomes shoppable.</h2>
        <p className="body">Paste a link. We find each item and match it to real products.</p>

        <div className="segmented" role="group" aria-label="Input type">
          {MODES.map((m) =>
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
          <span className="sr-only">{mode} link</span>
          <input
            type="url"
            inputMode="url"
            placeholder={`Paste a ${mode.toLowerCase()} link`}
            value={link}
            onChange={(e) => setLink(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && start()}
          />
        </label>

        <div className="row">
          <button type="button" className="btn primary grow" onClick={start} disabled={starting}>
            {starting ? "Finding items…" : "Find items"}
          </button>
          <Link href="/results" className="round" aria-label="See results">
            <ArrowIcon />
          </Link>
        </div>
        {!API_URL && <p className="note">Backend not connected: Results shows a sample run.</p>}
        {startError && <p className="note" role="alert">{startError}</p>}
      </section>

      <section className="gallery" aria-label="Before and after">
        <figure className="shot"><Asset name="roomBefore" className="fill" /></figure>
        <figure className="shot shifted"><Asset name="roomAfter" className="fill" /></figure>
        <div className="gallery-copy">
          <h2 className="h1">Exact, similar, or nothing.</h2>
          <p className="body">We show how sure we are, then place it in your room.</p>
        </div>
      </section>

      <section className="band" aria-label="Found items">
        <span className="ghost" aria-hidden="true">found</span>
        <div className="band-tiles">
          <Asset name="productFloorLamp" className="band-tile" />
          <Asset name="productChair" className="band-tile" />
          <Asset name="productVase" className="band-tile" />
        </div>
      </section>
    </main>
  );
}
