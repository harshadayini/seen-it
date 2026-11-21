/**
 * Screen 2, Results: a ghost-word header, category filters, then one card per found item.
 * Each card reads left to right: what was in YOUR video, then the closest product on Shopify,
 * then a few more similar products, each clearly labelled with price, store and a plain-word
 * confidence. "No match" is shown honestly. A sticky bar adds the selected items to the cart.
 * Boundary: reads the shared store only; crops fall back to placeholders until supplied.
 */
"use client";
import Link from "next/link";
import { useMemo, useState } from "react";
import { CropImage, ProductImage } from "@/components/Asset";
import { ConfidencePill } from "@/components/ConfidencePill";
import { EmptyRun } from "@/components/EmptyRun";
import { CheckIcon, PlusIcon } from "@/components/Icons";
import { StoreLink } from "@/components/StoreLink";
import { CROP_POSITIONS } from "@/lib/config";
import { bestCandidate, cleanTitle, fmtPrice, fmtRange, fmtTime, humanize, merchantName, pct } from "@/lib/format";
import { useStore } from "@/lib/store";

/** @returns the Results screen. */
export default function ResultsPage() {
  const { run, error, idle, selectedIds, toggle, lines, total } = useStore();
  const [filter, setFilter] = useState("All");

  const categories = useMemo(() => {
    const set = new Set((run?.items ?? []).map((i) => String(i.attributes?.category ?? "")).filter(Boolean));
    return ["All", ...set];
  }, [run]);

  if (idle) return <EmptyRun />;
  if (error && !run) return <main id="main" className="screen"><p className="note">Couldn&apos;t load the run: {error}</p></main>;
  if (!run) return <main id="main" className="screen"><p className="note">Loading…</p></main>;

  const items = run.items.filter((i) => filter === "All" || String(i.attributes?.category) === filter);

  return (
    <main id="main" className="screen">
      <header className="head">
        <span className="ghost" aria-hidden="true">found</span>
        <h1 className="h1 over">{humanize(run.source.video_id)}</h1>
        <p className="meta num over">
          {run.items.length} items{run.source.duration_s != null ? ` · ${fmtTime(run.source.duration_s)}` : ""}
          {run.state === "processing" ? " · still looking" : ""}
        </p>
      </header>

      <Link href="/scene" className="btn outline small walk">Walk through the scene</Link>

      {categories.length > 2 && (
        <div className="chips" role="group" aria-label="Filter by category">
          {categories.map((c) => (
            <button key={c} type="button" className={`chip ${filter === c ? "on" : ""}`} aria-pressed={filter === c} onClick={() => setFilter(c)}>
              {c}
            </button>
          ))}
        </div>
      )}

      <ul className="rlist">
        {items.map((it, i) => {
          const best = bestCandidate(it);
          const none = it.status === "none";
          const looking = !it.status;
          const buyable = !none && !looking && !!best?.variant_id;
          const inCart = selectedIds.includes(it.item_id);
          const category = String(it.attributes?.category ?? "");
          const others = (it.candidates ?? []).filter((c) => c !== best).slice(0, 3);
          return (
            <li key={it.item_id} className="rcard">
              <div className="rcard-head">
                <span className="idx num">{run.items.indexOf(it) + 1}</span>
                <h2 className="rcard-title">{it.description ?? "Item"}</h2>
                <span className="when num">{fmtRange(it.t_start, it.t_end)}</span>
              </div>

              <div className="duo">
                <figure className="duo-col">
                  <figcaption>In your video</figcaption>
                  <div className="tile"><CropImage path={it.crop_path} className="fillcrop" position={CROP_POSITIONS[i % CROP_POSITIONS.length]} /></div>
                </figure>
                <span className="duo-arrow" aria-hidden="true">→</span>
                <figure className="duo-col">
                  <figcaption>{none ? "On Shopify" : "Closest on Shopify"}</figcaption>
                  {none || looking ? (
                    <div className="tile empty"><span className="tile-note">{looking ? "Searching…" : "No match"}</span></div>
                  ) : (
                    <ProductImage url={best?.image_url} alt={best?.title ?? ""} category={category} />
                  )}
                </figure>
              </div>

              <div className="rcard-body">
                <div className="row">
                  <ConfidencePill status={it.status} p={best?.p_same_product} />
                  {it.recovered && <span className="signal">Found on second look</span>}
                </div>
                {none ? (
                  <p className="sub">Nothing on Shopify was trusted enough to show.</p>
                ) : looking ? (
                  <p className="sub">Searching the catalog…</p>
                ) : (
                  <>
                    <h3 className="card-title" title={best?.title}>{cleanTitle(best?.title)}</h3>
                    <p className="sub">{merchantName(best?.merchant_domain)} · <span className="num price">{fmtPrice(best?.price, best?.currency)}</span></p>
                  </>
                )}
                <div className="row-actions-inline">
                  {buyable && (
                    <button type="button" className={`btn small ${inCart ? "primary" : "outline"}`} aria-pressed={inCart} onClick={() => toggle(it.item_id)}>
                      {inCart ? <><CheckIcon /> In cart</> : <><PlusIcon /> Add to cart</>}
                    </button>
                  )}
                  {buyable && <Link href={`/see-it?item=${it.item_id}`} className="link">See it here</Link>}
                  {buyable && <StoreLink candidate={best} />}
                </div>
              </div>

              {others.length > 0 && (
                <div className="more">
                  <p className="sec-title">More from Shopify</p>
                  <ul>
                    {others.map((c, k) => (
                      <li key={`${c.variant_id ?? c.title}-${k}`}>
                        <ProductImage url={c.image_url} alt={c.title} category={category} className="more-tile" />
                        <span className="more-name" title={c.title}>{cleanTitle(c.title, 26)}</span>
                        <span className="num more-price">{fmtPrice(c.price, c.currency)} · {pct(c.p_same_product)}</span>
                        <StoreLink candidate={c} className="alt-link" label="Store ↗" />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>

      <div className="stickybar">
        <Link href="/cart" className={`btn primary wide ${lines.length === 0 ? "disabled" : ""}`} aria-disabled={lines.length === 0}>
          <span>Add {lines.length} to cart</span>
          <span className="num">{fmtPrice(total)}</span>
        </Link>
      </div>
    </main>
  );
}
