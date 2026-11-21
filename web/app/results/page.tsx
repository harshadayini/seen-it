/**
 * Screen 2, Results: header card with circular crops, then one card per found item with its
 * best catalog match, time range and confidence pill. "No match" is a dashed grey card that says
 * nothing was trusted enough to show. A sticky bar adds the selected items to the cart.
 * Boundary: reads the shared store only; crops are placeholder views of the scan image.
 */
"use client";
import Link from "next/link";
import { CropImage, ProductImage } from "@/components/Asset";
import { ConfidencePill } from "@/components/ConfidencePill";
import { CheckIcon, PlusIcon } from "@/components/Icons";
import { CROP_POSITIONS } from "@/lib/config";
import { bestCandidate, fmtPrice, fmtRange, fmtTime, humanize, merchantName } from "@/lib/format";
import { useStore } from "@/lib/store";

/** @returns the Results screen. */
export default function ResultsPage() {
  const { run, error, selectedIds, toggle, lines, total } = useStore();
  if (error && !run) return <main className="screen"><p className="notice">Couldn&apos;t load the run: {error}</p></main>;
  if (!run) return <main className="screen"><p className="notice">Loading…</p></main>;

  return (
    <main className="screen results">
      <section className="card head">
        <div className="crops" aria-hidden="true">
          {run.items.slice(0, 3).map((it, i) => (
            <CropImage key={it.item_id} path={it.crop_path} className="crop" position={CROP_POSITIONS[i]} />
          ))}
        </div>
        <h1 className="title">{humanize(run.source.video_id)}</h1>
        <p className="meta mono">
          {run.source.duration_s != null ? `${fmtTime(run.source.duration_s)} · ` : ""}{run.items.length} items{run.state === "processing" ? " so far" : ""}
        </p>
      </section>

      <ul className="list">
        {run.items.map((it, i) => {
          const best = bestCandidate(it);
          const none = it.status === "none";
          const looking = !it.status; // found in the video, catalog match not back yet
          const buyable = !none && !looking && !!best?.variant_id;
          const inCart = selectedIds.includes(it.item_id);
          return (
            <li key={it.item_id} className={`card item ${none ? "dashed" : ""}`}>
              <CropImage path={it.crop_path} className="crop big" position={CROP_POSITIONS[i % CROP_POSITIONS.length]} />
              <div className="item-body">
                <div className="row">
                  <ConfidencePill status={it.status} p={best?.p_same_product} />
                  <span className="mono dim">{fmtRange(it.t_start, it.t_end)}</span>
                </div>
                {none ? (
                  <>
                    <h2 className="item-name grey">{it.description}</h2>
                    <p className="grey">Nothing was trusted enough to show.</p>
                  </>
                ) : looking ? (
                  <>
                    <h2 className="item-name">{it.description}</h2>
                    <p className="dim">Searching the catalog…</p>
                  </>
                ) : (
                  <>
                    <h2 className="item-name">{best?.title ?? it.description}</h2>
                    <p className="dim">{merchantName(best?.merchant_domain)}</p>
                    <div className="row">
                      <span className="mono price">{fmtPrice(best?.price, best?.currency)}</span>
                      {it.recovered && <span className="tag-red">Found on second look</span>}
                    </div>
                  </>
                )}
                {buyable && (
                  <div className="row actions">
                    <Link href={`/see-it?item=${it.item_id}`} className="btn outline small">See it here</Link>
                    <button
                      type="button"
                      className={`round small ${inCart ? "filled" : "outline"}`}
                      aria-pressed={inCart}
                      aria-label={inCart ? `Remove ${best?.title} from cart` : `Add ${best?.title} to cart`}
                      onClick={() => toggle(it.item_id)}
                    >
                      {inCart ? <CheckIcon /> : <PlusIcon />}
                    </button>
                  </div>
                )}
              </div>
              {buyable && best && <ProductImage url={best.image_url} alt={best.title} category={String(it.attributes?.category ?? "")} className="item-thumb" />}
            </li>
          );
        })}
      </ul>

      <div className="stickybar">
        <Link href="/cart" className={`btn filled wide ${lines.length === 0 ? "disabled" : ""}`} aria-disabled={lines.length === 0}>
          <span>Add {lines.length} to cart</span>
          <span className="mono">{fmtPrice(total)}</span>
        </Link>
      </div>
    </main>
  );
}
