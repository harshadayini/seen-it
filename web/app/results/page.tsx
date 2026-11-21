/**
 * Screen 2, Results: a ghost-word header, category filters, then a two-column shelf of found
 * items. Each card is a product on a tinted tile with its real crop as a small badge, a
 * plain-word confidence pill, store and price. "No match" is shown honestly.
 * A sticky bar adds the selected items to the cart.
 * Boundary: reads the shared store only; crops fall back to placeholders until the backend
 * supplies them.
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
import { bestCandidate, fmtPrice, fmtRange, fmtTime, humanize, merchantName } from "@/lib/format";
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

      <ul className="grid">
        {items.map((it, i) => {
          const best = bestCandidate(it);
          const none = it.status === "none";
          const looking = !it.status;
          const buyable = !none && !looking && !!best?.variant_id;
          const inCart = selectedIds.includes(it.item_id);
          const category = String(it.attributes?.category ?? "");
          return (
            <li key={it.item_id} className={`card ${none ? "none" : ""}`}>
              <div className="tile-wrap">
                {none || looking ? (
                  <div className="tile empty"><CropImage path={it.crop_path} className="fillcrop" position={CROP_POSITIONS[i % CROP_POSITIONS.length]} /></div>
                ) : (
                  <ProductImage url={best?.image_url} alt={best?.title ?? ""} category={category} />
                )}
                {!none && !looking && (
                  <CropImage path={it.crop_path} className="crop-badge" position={CROP_POSITIONS[i % CROP_POSITIONS.length]} />
                )}
                {buyable && (
                  <button
                    type="button"
                    className={`round add ${inCart ? "on" : ""}`}
                    aria-pressed={inCart}
                    aria-label={inCart ? `Remove ${best?.title} from cart` : `Add ${best?.title} to cart`}
                    onClick={() => toggle(it.item_id)}
                  >
                    {inCart ? <CheckIcon /> : <PlusIcon />}
                  </button>
                )}
              </div>
              <ConfidencePill status={it.status} p={best?.p_same_product} />
              {none ? (
                <>
                  <h2 className="card-title muted">{it.description}</h2>
                  <p className="sub">Nothing was trusted enough to show.</p>
                </>
              ) : looking ? (
                <>
                  <h2 className="card-title">{it.description}</h2>
                  <p className="sub">Searching the catalog…</p>
                </>
              ) : (
                <>
                  <h2 className="card-title">{best?.title ?? it.description}</h2>
                  <p className="sub">
                    {merchantName(best?.merchant_domain)} · <span className="num">{fmtPrice(best?.price, best?.currency)}</span>
                  </p>
                  {it.recovered && <span className="signal">Found on second look</span>}
                  <Link href={`/see-it?item=${it.item_id}`} className="link">See it here</Link>
                  <StoreLink candidate={best} />
                </>
              )}
              <p className="when num">{fmtRange(it.t_start, it.t_end)}</p>
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
