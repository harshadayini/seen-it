/**
 * ItemPanel: the slide-over opened by clicking a card on Results. Shows, only on demand: the
 * crop and the matched product, how sure we are as small bars, other options, the search we ran,
 * the attributes we read and where in the video it was seen. The video stays visible beside it.
 * Boundary: presentational; for "No confident match" it shows no product and no alternatives.
 * Esc or the close button dismisses it and focus returns to the card that opened it.
 */
"use client";
import { useEffect, useRef } from "react";
import { CheckIcon, PlusIcon } from "@/components/Icons";
import { StoreLink } from "@/components/StoreLink";
import { fileUrl } from "@/lib/config";
import { bestCandidate, fmtPrice, fmtRange, matchWords, merchantName, pct } from "@/lib/format";
import type { Item } from "@/lib/types";

interface Props {
  item: Item;
  inCart: boolean;
  onToggleCart: () => void;
  onClose: () => void;
  /** Opens the "See it in your space" flow (shown only for a matched product with an image). */
  onSeeIt?: () => void;
}

/** One labelled bar, 0..1. */
function Meter({ label, p }: { label: string; p?: number | null }) {
  if (p == null) return null;
  return (
    <div>
      <div className="meter-row"><span>{label}</span><span className="num">{pct(p)}</span></div>
      <div className="meter-track" aria-hidden="true"><i style={{ width: pct(p) }} /></div>
    </div>
  );
}

/** @returns the detail panel for one finished item. Side effects: focus handling and an Esc key listener. */
export function ItemPanel({ item, inCart, onToggleCart, onClose, onSeeIt }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const closeFn = useRef(onClose);
  closeFn.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && closeFn.current();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, []);

  const best = bestCandidate(item);
  const none = item.status === "none";
  const buyable = !none && !!best?.variant_id;
  const others = none
    ? []
    : [...(item.candidates ?? [])].sort((a, b) => (b.p_same_product ?? 0) - (a.p_same_product ?? 0)).slice(1, 4);
  const attrs = Object.entries(item.attributes ?? {}).filter(([, v]) => typeof v === "string" || typeof v === "number");

  return (
    <aside className="panel" role="dialog" aria-label="Item details">
      <div className="panel-head">
        <p className={`label ${item.status ?? ""}`}>{matchWords(item.status)}</p>
        <button ref={closeRef} type="button" className="btn sm outline" onClick={onClose}>Close</button>
      </div>

      <div className="panel-body">
        <div className="panel-pics">
          {item.crop_path && (
            <figure>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={fileUrl(item.crop_path)} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />
              <figcaption>In your video</figcaption>
            </figure>
          )}
          {!none && best?.image_url && (
            <figure>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={best.image_url} alt={best.title} className="prod" onError={(e) => { e.currentTarget.style.display = "none"; }} />
              <figcaption>Matched product</figcaption>
            </figure>
          )}
        </div>

        {none ? (
          <>
            <h2 className="panel-title">{item.description}</h2>
            <p className="sub">We&apos;d rather say so than guess. Nothing we found was close enough to show.</p>
          </>
        ) : (
          <>
            <h2 className="panel-title">{best?.title ?? item.description}</h2>
            <p className="sub">{merchantName(best?.merchant_domain)} · <span className="num">{fmtPrice(best?.price, best?.currency)}</span></p>
            {item.recovered && <p className="signal">Second look improved this</p>}
            <div className="meters">
              <Meter label="Same product" p={best?.p_same_product} />
              <Meter label="Same colour and style" p={best?.p_same_variant} />
            </div>
            <div className="row-actions-inline">
              {buyable && (
                <button type="button" className={`btn sm ${inCart ? "primary" : "outline"}`} aria-pressed={inCart} onClick={onToggleCart}>
                  {inCart ? <CheckIcon /> : <PlusIcon />}
                  {inCart ? "In cart" : "Add to cart"}
                </button>
              )}
              <StoreLink candidate={best} className="link" />
            </div>
            {onSeeIt && !!best?.image_url && (
              <button type="button" className="btn primary" onClick={onSeeIt}>See it in your space</button>
            )}
          </>
        )}

        {others.length > 0 && (
          <section className="panel-sec" aria-label="Other options">
            <h3 className="panel-h">Other options</h3>
            <ul className="alts-list">
              {others.map((c, i) => (
                <li key={c.variant_id ?? c.upid ?? i}>
                  <span className="alt-name">{c.title}</span>
                  <span className="sub">{merchantName(c.merchant_domain)} · <span className="num">{fmtPrice(c.price, c.currency)}</span></span>
                  <StoreLink candidate={c} className="alt-link" label="View ↗" />
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="panel-sec" aria-label="How we found it">
          <h3 className="panel-h">How we found it</h3>
          <dl className="facts">
            <dt>Seen at</dt><dd className="num">{fmtRange(item.t_start, item.t_end)}</dd>
            {item.query && (<><dt>We searched for</dt><dd>{item.query}</dd></>)}
          </dl>
          {attrs.length > 0 && (
            <ul className="chips-static">
              {attrs.map(([k, v]) => (<li key={k}><span>{k}</span> {String(v)}</li>))}
            </ul>
          )}
        </section>
      </div>
    </aside>
  );
}
