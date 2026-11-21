/**
 * Screen 5, Desk: a photo of an empty desk, one request field, a budget line, and a short list
 * of picks with style and space scores.
 * Boundary: LAYOUT SHELL. The run contract has no desk data yet, so the picks and scores are
 * sample values from lib/config.ts and are labelled "Sample" on screen. They are not real
 * matches, and "Add all" stays disabled until the backend supplies real ones.
 */
"use client";
import Link from "next/link";
import { useState } from "react";
import { Asset, ProductImage } from "@/components/Asset";
import { BackIcon } from "@/components/Icons";
import { DESK_SAMPLE } from "@/lib/config";
import { fmtPrice, score } from "@/lib/format";

/** @returns the Desk screen. */
export default function DeskPage() {
  const [request, setRequest] = useState("Make this warmer, under $150");
  const spent = DESK_SAMPLE.picks.reduce((a, p) => a + p.price, 0);

  return (
    <main id="main" className="screen">
      <div className="between">
        <Link href="/" className="back"><BackIcon /> Scan</Link>
        <span className="tagline">Sample</span>
      </div>

      <div className="photo">
        <Asset name="deskEmpty" className="fill" />
      </div>

      <section className="detail">
        <label className="field">
          <span className="sr-only">What should change?</span>
          <input value={request} onChange={(e) => setRequest(e.target.value)} />
        </label>
        <h1 className="h1">
          {DESK_SAMPLE.picks.length} picks, <span className="num">{fmtPrice(spent)}</span> of <span className="num">{fmtPrice(DESK_SAMPLE.budget)}</span>
        </h1>
        <ul className="lines">
          {DESK_SAMPLE.picks.map((p) => (
            <li key={p.name} className="line">
              <ProductImage alt={p.name} category={p.category} className="thumb" />
              <div className="line-body">
                <span className="line-title">{p.name}</span>
                <span className="sub num">Style {score(p.style)} · Space {score(p.space)}</span>
              </div>
              <span className="num">{fmtPrice(p.price)}</span>
            </li>
          ))}
        </ul>
        <div className="row">
          <Link href="/see-it" className="btn outline grow">See it here</Link>
          <button type="button" className="btn primary grow" disabled>Add all</button>
        </div>
      </section>
    </main>
  );
}
