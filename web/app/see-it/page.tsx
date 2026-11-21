/**
 * Screen 3, See it here: a before/after curtain over the user's own scene, the product's name,
 * store and price, and two actions (Regenerate, Keep it).
 * Boundary: the before/after images are placeholders until the backend returns a real preview
 * (preview.image_path); Regenerate only calls the backend when it is connected.
 */
"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { BackIcon } from "@/components/Icons";
import { CompareSlider } from "@/components/CompareSlider";
import { API_URL, PREVIEW_PASS_FIDELITY } from "@/lib/config";
import { bestCandidate, fmtPrice, merchantName, score } from "@/lib/format";
import { useStore } from "@/lib/store";

/** The screen body (split out so useSearchParams sits under Suspense). */
function SeeIt() {
  const { run, purchasable, add } = useStore();
  const router = useRouter();
  const params = useSearchParams();
  const [note, setNote] = useState<string | null>(null);

  const item = run?.items.find((i) => i.item_id === params.get("item")) ?? purchasable[0];
  const best = item ? bestCandidate(item) : undefined;
  if (!item || !best) {
    return (
      <main id="main" className="screen">
        <p className="note">No matched item to preview yet.</p>
        <Link href="/results" className="btn outline">Back to results</Link>
      </main>
    );
  }
  const fidelity = item.preview?.fidelity ?? null;

  /** Asks the backend for a new preview; says so plainly when it isn't connected. */
  function regenerate() {
    setNote(API_URL ? "Regenerating arrives with the backend." : "Backend not connected, so there is nothing to regenerate.");
  }
  /** Adds this item to the cart and goes there. */
  function keep() {
    add(item!.item_id);
    router.push("/cart");
  }

  return (
    <main id="main" className="screen">
      <Link href="/results" className="back"><BackIcon /> Results</Link>

      <CompareSlider before="roomBefore" after="roomAfter" />

      <section className="detail">
        <h1 className="h1">{best.title}</h1>
        <p className="sub">
          {merchantName(best.merchant_domain)} · <span className="num">{fmtPrice(best.price, best.currency)}</span>
        </p>
        <p className="sub num">
          {fidelity == null ? "No preview yet" : `Fidelity ${score(fidelity)} · ${fidelity >= PREVIEW_PASS_FIDELITY ? "check passed" : "check failed"}`}
        </p>
        <div className="row">
          <button type="button" className="btn outline grow" onClick={regenerate}>Regenerate</button>
          <button type="button" className="btn primary grow" onClick={keep}>Keep it</button>
        </div>
        {note && <p className="note" role="status">{note}</p>}
      </section>
    </main>
  );
}

/** @returns the See it here screen. */
export default function SeeItPage() {
  return (
    <Suspense fallback={<main id="main" className="screen"><p className="note">Loading…</p></main>}>
      <SeeIt />
    </Suspense>
  );
}
