/**
 * ItemCard: one found item in the Results list. Always visible on a finished item: crop, product
 * name, store, price, ONE match label (words plus colour plus a mark, never a score) and an
 * "Add to cart" button. Also covers the other honest states: still checking (a quiet placeholder,
 * no crop and no match), failed ("Couldn't check this one" + Try again), and "No confident match"
 * ("We'd rather say so than guess", no product shown).
 * Boundary: presentational; selection, cart and retry are callbacks from the page.
 */
"use client";
import { CheckIcon, PlusIcon } from "@/components/Icons";
import { fileUrl } from "@/lib/config";
import { bestCandidate, cleanTitle, fmtPrice, matchWords, merchantName } from "@/lib/format";
import type { Item } from "@/lib/types";

interface Props {
  item: Item;
  selected: boolean;
  inCart: boolean;
  onSelect: () => void;
  onToggleCart: () => void;
  onRetry: () => void;
}

const MARK: Record<string, string> = { exact: "✓", similar: "≈", none: "–" };

/** Small image that hides itself if it fails to load (no placeholder art pretending to be a result). */
function Thumb({ src, alt, product }: { src: string; alt: string; product?: boolean }) {
  return (
    <span className={`thumb2 ${product ? "prod" : ""}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} onError={(e) => { e.currentTarget.style.display = "none"; }} />
    </span>
  );
}

/** @returns one list row for the item, in whichever state it is in. */
export function ItemCard({ item, selected, inCart, onSelect, onToggleCart, onRetry }: Props) {
  // Still working on it: say so quietly. No crop, no match until the item is done.
  if (item.state === "processing") {
    return (
      <li className="rcard checking" aria-busy="true">
        <div className="rcard-main static">
          <span className="thumb2 skel" aria-hidden="true" />
          <span className="rtext">
            <span className="rname muted">Checking…</span>
            <span className="sub">{item.description}</span>
          </span>
        </div>
      </li>
    );
  }

  // Failed, or finished without a verdict: never guess.
  if (item.state === "failed" || !item.status) {
    return (
      <li className="rcard failed">
        <div className="rcard-main static">
          <span className="rtext">
            <span className="rname">Couldn&apos;t check this one</span>
            <span className="sub">{item.description}</span>
          </span>
        </div>
        <div className="rcard-actions">
          <button type="button" className="btn sm outline" onClick={onRetry}>Try again</button>
        </div>
      </li>
    );
  }

  const best = bestCandidate(item);
  const none = item.status === "none";
  const buyable = !none && !!best?.variant_id;
  const cropSrc = item.crop_path ? fileUrl(item.crop_path) : null;

  return (
    <li className={`rcard ${none ? "none" : ""} ${selected ? "sel" : ""}`}>
      <button type="button" className="rcard-main" aria-pressed={selected} onClick={onSelect}>
        <span className="thumbs">
          {cropSrc && <Thumb src={cropSrc} alt="" />}
          {!none && best?.image_url && <Thumb src={best.image_url} alt="" product />}
        </span>
        <span className="rtext">
          {none ? (
            <>
              <span className="rname muted">{item.description}</span>
              <span className={`label ${item.status}`}><span aria-hidden="true">{MARK.none}</span> {matchWords("none")}</span>
              <span className="sub">We&apos;d rather say so than guess.</span>
            </>
          ) : (
            <>
              <span className="rname" title={best?.title}>{best ? cleanTitle(best.title) : item.description}</span>
              <span className="sub">
                {merchantName(best?.merchant_domain)} · <span className="num">{fmtPrice(best?.price, best?.currency)}</span>
              </span>
              <span className={`label ${item.status}`}><span aria-hidden="true">{MARK[item.status]}</span> {matchWords(item.status)}</span>
              {item.recovered && <span className="signal">Second look improved this</span>}
            </>
          )}
        </span>
      </button>
      {buyable && (
        <div className="rcard-actions">
          <button
            type="button"
            className={`btn sm ${inCart ? "primary" : "outline"}`}
            aria-pressed={inCart}
            aria-label={inCart ? `Remove ${best?.title} from cart` : `Add ${best?.title} to cart`}
            onClick={onToggleCart}
          >
            {inCart ? <CheckIcon /> : <PlusIcon />}
            {inCart ? "In cart" : "Add to cart"}
          </button>
        </div>
      )}
    </li>
  );
}
