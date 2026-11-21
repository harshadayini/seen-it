/**
 * Scene page: after a link is pasted, walk through everything found in it, one object at a time.
 * A slider steps through the objects as they are found (new ones appear while the run is still
 * processing). Each step shows its frame with a bounding box, then the item's name, price,
 * store, confidence scores, attributes and alternatives, with a filmstrip and a cart strip.
 * Boundary: reads the shared store only. Items still being matched show "Searching the
 * catalog"; "no match" is shown honestly. Without a backend it shows the labelled sample run.
 */
"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { CropImage, ProductImage } from "@/components/Asset";
import { ConfidencePill } from "@/components/ConfidencePill";
import { EmptyRun } from "@/components/EmptyRun";
import { BackIcon, CheckIcon, PlusIcon } from "@/components/Icons";
import { SceneFrame } from "@/components/SceneFrame";
import { StoreLink } from "@/components/StoreLink";
import { API_URL, CROP_POSITIONS } from "@/lib/config";
import { bestCandidate, fmtPrice, fmtRange, merchantName, pct } from "@/lib/format";
import { useStore } from "@/lib/store";

/** A labelled horizontal meter (a probability shown as a bar and a number). */
function Meter({ label, p }: { label: string; p?: number | null }) {
  const v = Math.max(0, Math.min(1, p ?? 0));
  return (
    <div className="meter">
      <div className="meter-row"><span>{label}</span><span className="num">{pct(p)}</span></div>
      <div className="meter-track" role="img" aria-label={`${label} ${pct(p)}`}><i style={{ width: `${v * 100}%` }} /></div>
    </div>
  );
}

/** @returns the Scene screen. */
export default function ScenePage() {
  const { run, error, idle, selectedIds, toggle, lines, total } = useStore();
  const items = run?.items ?? [];
  const n = items.length;
  const [step, setStep] = useState(0);
  const followLatest = useRef(true);

  // While the run is still producing objects, keep the newest one in view until the user slides.
  useEffect(() => {
    if (followLatest.current && n > 0) setStep(n - 1);
  }, [n]);

  if (idle) return <EmptyRun title="Nothing to walk through" />;
  if (error && !run) return <main id="main" className="screen"><p className="note">Couldn&apos;t load the run: {error}</p></main>;
  if (!run) return <main id="main" className="screen"><p className="note">Loading…</p></main>;

  const processing = run.state === "processing";
  const done = items.filter((i) => i.state === "done").length;
  const idx = Math.min(step, Math.max(0, n - 1));
  const it = items[idx];
  const best = it ? bestCandidate(it) : undefined;
  const buyable = !!it && (it.status === "exact" || it.status === "similar") && !!best?.variant_id;
  const inCart = !!it && selectedIds.includes(it.item_id);
  const category = String(it?.attributes?.category ?? "");

  /** Moves to an object and stops following new arrivals. @param i index */
  function go(i: number) {
    followLatest.current = false;
    setStep(Math.max(0, Math.min(n - 1, i)));
  }

  return (
    <main id="main" className="screen scene">
      <header className="head">
        <span className="ghost" aria-hidden="true">scene</span>
        <Link href="/" className="back over"><BackIcon /> Scan</Link>
        <h1 className="h1 over">{processing ? "Finding things…" : `${n} things found`}</h1>
        <p className="meta num over">
          {processing ? `${done} of ${n || "…"} matched` : "Slide to walk through the scene"}
          {!API_URL ? " · sample run" : ""}
        </p>
        {processing && <div className="progress" role="progressbar" aria-label="Matching progress" aria-valuemin={0} aria-valuemax={Math.max(n, 1)} aria-valuenow={done}><i style={{ width: `${n ? (done / n) * 100 : 8}%` }} /></div>}
      </header>

      {run.state === "failed" && <p className="note strong" role="alert">This run didn&apos;t finish: {String((run as { error?: string }).error ?? "unknown error")}</p>}

      {n === 0 && !processing && <p className="note">Nothing was found in this one.</p>}
      {n === 0 && processing && (
        <div className="sframe skeleton" aria-busy="true"><span className="sbox-tag">Watching the video…</span></div>
      )}

      {it && (
        <>
          <SceneFrame key={it.item_id} item={it} index={idx} best={best} />

          <div className="stepper">
            <button type="button" className="round small" onClick={() => go(idx - 1)} disabled={idx === 0} aria-label="Previous object"><BackIcon /></button>
            <div className="stepper-track">
              <input
                type="range"
                min={0}
                max={Math.max(0, n - 1)}
                step={1}
                value={idx}
                onChange={(e) => go(Number(e.target.value))}
                aria-label="Slide between found objects"
                aria-valuetext={`Object ${idx + 1} of ${n}: ${it.description ?? "item"}`}
              />
              <div className="ticks" aria-hidden="true">
                {items.map((x, i) => <i key={x.item_id} className={i === idx ? "on" : i < idx ? "past" : ""} style={{ left: `${n > 1 ? (i / (n - 1)) * 100 : 50}%` }} />)}
              </div>
            </div>
            <button type="button" className="round small" onClick={() => go(idx + 1)} disabled={idx >= n - 1} aria-label="Next object"><BackIcon /></button>
          </div>
          <p className="step-label num">Object {idx + 1} of {n}{processing ? " so far" : ""} · {fmtRange(it.t_start, it.t_end)}</p>

          <section key={`d-${it.item_id}`} className="found" aria-label="What was found">
            <p className="new-flag">{processing && idx === n - 1 ? "Just found" : "Found"}</p>
            <div className="found-main">
              {it.status === "none" || !it.status ? (
                <div className="tile empty"><CropImage path={it.crop_path} className="fillcrop" position={CROP_POSITIONS[idx % CROP_POSITIONS.length]} /></div>
              ) : (
                <ProductImage url={best?.image_url} alt={best?.title ?? ""} category={category} />
              )}
              <div className="found-text">
                <ConfidencePill status={it.status} p={best?.p_same_product} />
                <h2 className="found-title">{it.status === "none" ? it.description : best?.title ?? it.description}</h2>
                {it.status === "none" ? (
                  <p className="sub">Nothing was trusted enough to show.</p>
                ) : !it.status ? (
                  <p className="sub">Searching the catalog…</p>
                ) : (
                  <p className="sub">{merchantName(best?.merchant_domain)} · <span className="num found-price">{fmtPrice(best?.price, best?.currency)}</span></p>
                )}
                {it.recovered && <span className="signal">Found on second look</span>}
              </div>
            </div>

            {it.description && <p className="body">Seen as: {it.description}</p>}

            {it.attributes && (
              <ul className="chips-static" aria-label="Attributes">
                {Object.entries(it.attributes).filter(([, v]) => v).map(([k, v]) => <li key={k}><span>{k}</span> {String(v)}</li>)}
              </ul>
            )}

            {best && it.status !== "none" && (
              <div className="meters">
                <Meter label="Same product" p={best.p_same_product} />
                <Meter label="Same variant" p={best.p_same_variant} />
              </div>
            )}

            {(it.candidates?.length ?? 0) > 1 && (
              <div className="alts" aria-label="Other matches">
                <p className="sub">Other matches</p>
                <ul>
                  {it.candidates!.filter((c) => c !== best).slice(0, 3).map((c, i) => (
                    <li key={`${c.variant_id ?? c.title}-${i}`}>
                      <ProductImage url={c.image_url} alt={c.title} category={category} className="alt-tile" />
                      <StoreLink candidate={c} className="alt-link" label="Store ↗" />
                      <span className="alt-price num">{fmtPrice(c.price, c.currency)}</span>
                      <span className="alt-p num">{pct(c.p_same_product)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {buyable && (
              <div className="row">
                <button type="button" className={`btn ${inCart ? "primary" : "outline"} grow`} aria-pressed={inCart} onClick={() => toggle(it.item_id)}>
                  {inCart ? <><CheckIcon /> In your cart</> : <><PlusIcon /> Add to cart</>}
                </button>
                <Link href={`/see-it?item=${it.item_id}`} className="btn outline">See it here</Link>
              </div>
            )}
            {buyable && <StoreLink candidate={best} className="btn outline wide-link" label="View on the store ↗" />}
          </section>

          <div className="film" role="group" aria-label="All found objects">
            {items.map((x, i) => (
              <button key={x.item_id} type="button" className={`film-item ${x.status ?? "pending"} ${i === idx ? "on" : ""}`} aria-pressed={i === idx} aria-label={`Object ${i + 1}: ${x.description ?? "item"}`} onClick={() => go(i)}>
                <CropImage path={x.crop_path} className="film-crop" position={CROP_POSITIONS[i % CROP_POSITIONS.length]} />
                <b className="num">{i + 1}</b>
              </button>
            ))}
          </div>
        </>
      )}

      <div className="stickybar">
        <Link href="/cart" className={`btn primary wide ${lines.length === 0 ? "disabled" : ""}`} aria-disabled={lines.length === 0}>
          <span>{lines.length} in cart</span>
          <span className="num">{fmtPrice(total)}</span>
        </Link>
      </div>
    </main>
  );
}
