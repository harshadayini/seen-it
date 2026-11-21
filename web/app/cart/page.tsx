/**
 * Screen 4, Cart: one card per merchant (Shopify carts are per store) with line items, a
 * subtotal, and a "Continue at <merchant>" button that opens that merchant's own checkout.
 * Invariants: nothing is charged in the app and no order is placed. A checkout link only appears
 * once the backend has created the cart; before that the button builds the carts.
 */
"use client";
import { ProductImage } from "@/components/Asset";
import { fmtPrice, merchantName } from "@/lib/format";
import { useStore } from "@/lib/store";

/** @returns the Cart screen. */
export default function CartPage() {
  const { byMerchant, lines, total, urls, buildCarts, busy, cartError } = useStore();

  return (
    <main className="screen cart">
      <header className="topbar plain">
        <h1 className="title small">Your carts</h1>
      </header>

      {lines.length === 0 && <p className="notice">Nothing here yet. Add matches from Results.</p>}

      {[...byMerchant.entries()].map(([domain, ls]) => {
        const url = urls[domain];
        return (
          <section key={domain} className="card merchant">
            <h2 className="merchant-name">{merchantName(domain)}</h2>
            <ul className="lines">
              {ls.map(({ item, candidate }) => (
                <li key={item.item_id} className="line">
                  <ProductImage url={candidate.image_url} alt={candidate.title} category={String(item.attributes?.category ?? "")} className="line-thumb" />
                  <span className="line-title">{candidate.title}</span>
                  <span className="mono">{fmtPrice(candidate.price, candidate.currency)}</span>
                </li>
              ))}
            </ul>
            <div className="row subtotal">
              <span>Subtotal</span>
              <span className="mono">{fmtPrice(ls.reduce((a, l) => a + (l.candidate.price ?? 0), 0))}</span>
            </div>
            {url ? (
              <a className="btn filled wide" href={url} target="_blank" rel="noreferrer">Continue at {merchantName(domain)}</a>
            ) : (
              <button type="button" className="btn filled wide" onClick={buildCarts} disabled={busy}>
                {busy ? "Building cart…" : `Continue at ${merchantName(domain)}`}
              </button>
            )}
          </section>
        );
      })}

      {lines.length > 0 && <p className="muted-note">Each store has its own checkout. Nothing is charged in this app.</p>}
      {cartError && <p className="notice err" role="alert">{cartError}</p>}

      <div className="stickybar">
        <div className="btn total wide" role="status">
          <span>Total</span>
          <span className="mono">{fmtPrice(total)}</span>
        </div>
      </div>
    </main>
  );
}
