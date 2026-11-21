/**
 * Screen 3, See it here: a large rounded image card with a Before / After toggle, a floating
 * expand button, the product's name, merchant and price, and a fidelity readout.
 * Regenerate and Keep it are the two actions.
 * Boundary: the before/after images are placeholders until the backend returns a real preview
 * (preview.image_path); Regenerate only calls the backend when it is connected.
 */
"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Asset } from "@/components/Asset";
import { ExpandIcon } from "@/components/Icons";
import { API_URL, PREVIEW_PASS_FIDELITY } from "@/lib/config";
import { bestCandidate, fmtPrice, merchantName, score } from "@/lib/format";
import { useStore } from "@/lib/store";

/** The screen body (split out so useSearchParams sits under Suspense). */
function SeeIt() {
  const { run, purchasable, add } = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const [after, setAfter] = useState(true);
  const [big, setBig] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const item = run?.items.find((i) => i.item_id === params.get("item")) ?? purchasable[0];
  const best = item ? bestCandidate(item) : undefined;
  if (!item || !best) {
    return (
      <main className="screen">
        <p className="notice">No matched item to preview yet.</p>
        <Link href="/results" className="btn outline">Back to results</Link>
      </main>
    );
  }
  const fidelity = item.preview?.fidelity ?? null;

  /** Asks the backend for a new preview; says so plainly when it isn't connected. */
  function regenerate() {
    setNote(API_URL ? "Regenerating is wired up with the backend next." : "Backend isn't connected yet, so there is nothing to regenerate.");
  }
  /** Adds this item to the cart and goes there. */
  function keep() {
    add(item!.item_id);
    router.push("/cart");
  }

  return (
    <main className="screen seeit">
      <header className="topbar plain">
        <Link href="/results" className="back">Results</Link>
        <span className="wordmark small">See it here</span>
      </header>

      <section className={`card photo ${big ? "big" : ""}`}>
        <Asset name={after ? "roomAfter" : "roomBefore"} className="fill" />
        <div className="toggle" role="group" aria-label="Before and after">
          <button type="button" aria-pressed={!after} className={!after ? "on" : ""} onClick={() => setAfter(false)}>Before</button>
          <button type="button" aria-pressed={after} className={after ? "on" : ""} onClick={() => setAfter(true)}>After</button>
        </div>
        <button type="button" className="round float" aria-label={big ? "Shrink image" : "Expand image"} aria-pressed={big} onClick={() => setBig((b) => !b)}>
          <ExpandIcon />
        </button>
      </section>

      <section className="card info">
        <h1 className="title small">{best.title}</h1>
        <p className="dim">{merchantName(best.merchant_domain)}</p>
        <div className="row">
          <span className="mono price">{fmtPrice(best.price, best.currency)}</span>
          <span className="mono readout">
            {fidelity == null ? "no preview yet" : `fidelity ${score(fidelity)}, ${fidelity >= PREVIEW_PASS_FIDELITY ? "check passed" : "check failed"}`}
          </span>
        </div>
        <div className="row actions">
          <button type="button" className="btn outline" onClick={regenerate}>Regenerate</button>
          <button type="button" className="btn filled" onClick={keep}>Keep it</button>
        </div>
        {note && <p className="muted-note" role="status">{note}</p>}
      </section>
    </main>
  );
}

/** @returns the See it here screen. */
export default function SeeItPage() {
  return (
    <Suspense fallback={<main className="screen"><p className="notice">Loading…</p></main>}>
      <SeeIt />
    </Suspense>
  );
}
