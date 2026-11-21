/**
 * Screen 1, Scan: a photo hero with an oversized "seen it" wordmark half in, half out of the
 * image; a short intake beside a tilted product tray; a four-promise panel; then editorial
 * sections for skincare, rooms, outfits and previews, in the Sage collage layout.
 * Boundary: "Find items" only starts a run when the backend is connected; otherwise it says so
 * and Results shows the sample run. Photos are local reference images (see lib/assets.ts).
 */
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Asset } from "@/components/Asset";
import { Feature } from "@/components/Feature";
import { ArrowIcon, BagIcon } from "@/components/Icons";
import { Spline3D } from "@/components/Spline3D";
import { TrustPanel } from "@/components/TrustPanel";
import { API_URL, SPLINE_SCENES } from "@/lib/config";
import { useStore } from "@/lib/store";

type Mode = "Video" | "Photo" | "Desk";
const MODES: Mode[] = ["Video", "Photo", "Desk"];

/** @returns the Scan screen. */
export default function ScanPage() {
  const { run, error, startRun, starting, startError, lines } = useStore();
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("Video");
  const [link, setLink] = useState("");

  /** Starts a real run for the pasted link, then shows results as they arrive. */
  async function start() {
    const started = await startRun(link, "video");
    // With a backend, follow the new run; without one, show the labelled sample scene.
    if (started || !API_URL) router.push("/scene");
  }

  return (
    <main id="main" className="scan">
      <header className="nav">
        <span className="nav-logo" aria-hidden="true">s</span>
        <span className="nav-title">{run ? `${run.items.length} items found` : "scene-it"}</span>
        <Link href="/cart" className="nav-cart" aria-label={`Cart, ${lines.length} items`}>
          <BagIcon />
          {lines.length > 0 && <b className="count">{lines.length}</b>}
        </Link>
      </header>

      <section className="hero" aria-label="Welcome">
        <div className="hero-img">
          <Asset name="heroWoman" className="fill" position="60% 30%" />
          {error && <p className="note on-image">Couldn&apos;t load the run: {error}</p>}
        </div>
        <h1 className="wordmark">scene-it</h1>
      </section>

      <section className="intro" aria-label="Start a scan">
        <Spline3D scene={SPLINE_SCENES.hero} fallback="tray" className="object" />
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

      <TrustPanel />

      <Feature
        variant="pair"
        title="Skincare, with receipts."
        text={["Spot a bottle on someone’s shelf. We name it, price it, and say how sure we are.", "Not sure? We’ll admit that too."]}
        tall={["skinSet", "skinShelf"]}
        small="skinBasket"
      />

      <Feature
        variant="collage"
        ghost="room"
        title="Rooms, decoded."
        text={[
          "The lamp in the corner of someone’s tour now has a name, a shop and a price.",
          "Found a cousin, not the twin? We’ll say so.",
        ]}
        wide="roomChair"
        low="roomGreen"
        cta={{ label: "Try a room", href: "/results" }}
      />

      <Feature
        variant="pair"
        title="The coat you can’t stop thinking about."
        text={["Seen on a crosswalk, a reel, a friend. We find the real one, or its closest relative.", "Cut and colour, not just “beige coat”."]}
        tall={["fitParis", "fitRackHat"]}
        small="fitRackPlant"
      />

      <Feature
        variant="collage"
        ghost="try"
        title="Try it before it’s yours."
        text={["See the piece in your own room first.", "Slide to compare. Keep it, or don’t."]}
        wide="roomBrown"
        low="roomColor"
        cta={{ label: "Preview one", href: "/see-it" }}
      />
    </main>
  );
}
