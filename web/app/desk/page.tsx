/**
 * Screen 5, Desk mode: a photo card of an empty desk, a request field, the budget line, and a
 * list of picks with style-fit and space-fit scores.
 * Boundary: LAYOUT SHELL. The run contract has no desk data yet, so the picks and scores are
 * sample values from lib/config.ts, labelled "Sample layout" on screen. They are not real
 * matches and "Add all" stays disabled until the backend supplies real ones.
 */
"use client";
import Link from "next/link";
import { useState } from "react";
import { Asset, ProductImage } from "@/components/Asset";
import { DESK_SAMPLE } from "@/lib/config";
import { fmtPrice, score } from "@/lib/format";

/** @returns the Desk screen. */
export default function DeskPage() {
  const [request, setRequest] = useState("Make this warmer, under $150");
  const spent = DESK_SAMPLE.picks.reduce((a, p) => a + p.price, 0);

  return (
    <main className="screen desk">
      <header className="topbar plain">
        <Link href="/" className="back">Scan</Link>
        <span className="pill sample">Sample layout</span>
      </header>

      <section className="card photo short">
        <Asset name="deskEmpty" className="fill" />
        <Asset name="stickerPlant" className="sticker" decorative />
      </section>

      <section className="card info">
        <label className="field">
          <span className="sr-only">What should change?</span>
          <input value={request} onChange={(e) => setRequest(e.target.value)} />
        </label>
        <p className="mono budget">
          {DESK_SAMPLE.picks.length} picks, {fmtPrice(spent)} of {fmtPrice(DESK_SAMPLE.budget)}
        </p>
        <ul className="picks">
          {DESK_SAMPLE.picks.map((p) => (
            <li key={p.name} className="pick">
              <ProductImage alt={p.name} category={p.category} className="line-thumb" />
              <div className="pick-body">
                <span className="line-title">{p.name}</span>
                <span className="mono dim">style {score(p.style)} · space {score(p.space)}</span>
              </div>
              <span className="mono">{fmtPrice(p.price)}</span>
            </li>
          ))}
        </ul>
        <div className="row actions">
          <Link href="/see-it" className="btn outline">See it here</Link>
          <button type="button" className="btn filled" disabled>Add all</button>
        </div>
      </section>
    </main>
  );
}
