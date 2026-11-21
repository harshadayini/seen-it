/**
 * Screen 4, Cart: one block per store (Shopify carts are per store) with its items, a subtotal,
 * and a "Continue at <store>" button that opens that store's own checkout.
 * Invariants: nothing is charged here and no order is placed. A checkout link only appears once
 * the backend has created the cart; before that the button builds the carts.
 */
"use client";
import { ProductImage } from "@/components/Asset";
import { Spline3D } from "@/components/Spline3D";
import { SPLINE_SCENES } from "@/lib/config";
import { fmtPrice, merchantName } from "@/lib/format";
import { useStore } from "@/lib/store";

/** @returns the Cart screen. */
export default function CartPage() {
  const { byMerchant, lines, total, urls, buildCarts, busy, cartError } = useStore();

  return (
    <main id="main" className="screen">
      <header className="head with-orb">
        <span className="ghost" aria-hidden="true">bag</span>
        <h1 className="h1 over">Your carts</h1>
        <Spline3D scene={SPLINE_SCENES.cart} className="orb small" />
      </header>

      {lines.length === 0 && <p className="note">Nothing here yet. Add matches from Results.</p>}

      {[...byMerchant.entries()].map(([domain, ls]) => {
        const url = urls[domain];
        return (
          <section key={domain} className="store" aria-label={merchantName(domain)}>
            <h2 className="store-name">{merchantName(domain)}</h2>
            <ul className="lines">
              {ls.map(({ item, candidate }) => (
                <li key={item.item_id} className="line">
                  <ProductImage url={candidate.image_url} alt={candidate.title} category={String(item.attributes?.category ?? "")} className="thumb" />
                  <span className="line-title">{candidate.title}</span>
                  <span className="num">{fmtPrice(candidate.price, candidate.currency)}</span>
                </li>
              ))}
            </ul>
            <div className="subtotal">
              <span>Subtotal</span>
              <span className="num">{fmtPrice(ls.reduce((a, l) => a + (l.candidate.price ?? 0), 0))}</span>
            </div>
            {url ? (
              <a className="btn primary wide" href={url} target="_blank" rel="noreferrer">Continue at {merchantName(domain)}</a>
            ) : (
              <button type="button" className="btn primary wide" onClick={buildCarts} disabled={busy}>
                {busy ? "Building cart…" : `Continue at ${merchantName(domain)}`}
              </button>
            )}
          </section>
        );
      })}

      {lines.length > 0 && <p className="note">Each store has its own checkout. Nothing is charged here.</p>}
      {cartError && <p className="note strong" role="alert">{cartError}</p>}

      <div className="stickybar">
        <div className="btn total wide" role="status">
          <span>Total</span>
          <span className="num">{fmtPrice(total)}</span>
        </div>
      </div>
    </main>
  );
}
