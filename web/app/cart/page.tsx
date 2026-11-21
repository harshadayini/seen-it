/**
 * Screen 3, Cart: one block per store side by side (Shopify carts are per store): its items with
 * one-click removal, a subtotal and "Go to checkout" using that store's continue_url.
 * Invariants: we stop at checkout and no order is placed. A checkout link only appears once the
 * backend has built the carts for exactly the items shown (carts are rebuilt after a removal), so
 * a link never points at a cart that still holds a removed item. Never fabricates a link.
 */
"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { fileUrl } from "@/lib/config";
import { cleanTitle, fmtPrice, merchantName } from "@/lib/format";
import { useStore } from "@/lib/store";

/** @returns the Cart screen. */
export default function CartPage() {
  const { byMerchant, lines, total, urls, buildCarts, busy, cartError, toggle } = useStore();
  const key = lines.map((l) => l.item.item_id).sort().join(",");
  const [builtFor, setBuiltFor] = useState<string | null>(null);
  const lastKey = useRef<string | null>(null);

  // Build the carts for the items shown (after a short pause, so rapid removals build once).
  useEffect(() => {
    if (!key || key === lastKey.current) return;
    const t = setTimeout(() => {
      lastKey.current = key;
      buildCarts().then(() => setBuiltFor(key));
    }, 500);
    return () => clearTimeout(t);
  }, [key, buildCarts]);

  const ready = builtFor === key && !busy;

  if (lines.length === 0) {
    return (
      <main id="main" className="screen cart">
        <header className="head"><h1 className="h1">Your cart is empty</h1><p className="meta">Add matched products from your results.</p></header>
        <Link href="/results" className="btn primary">Back to results</Link>
      </main>
    );
  }

  return (
    <main id="main" className="screen cart">
      <header className="head">
        <h1 className="h1">Your cart</h1>
        <p className="meta">{lines.length} {lines.length === 1 ? "item" : "items"} from {byMerchant.size} {byMerchant.size === 1 ? "shop" : "shops"} · <span className="num">{fmtPrice(total)}</span> in total</p>
      </header>

      <div className="stores">
        {[...byMerchant.entries()].map(([domain, ls]) => {
          const url = ready ? urls[domain] : null;
          return (
            <section key={domain} className="store" aria-label={merchantName(domain)}>
              <h2 className="store-name">{merchantName(domain)}</h2>
              <ul className="lines">
                {ls.map(({ item, candidate }) => (
                  <li key={item.item_id} className="cline">
                    <span className="thumb2 prod">
                      {candidate.image_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={candidate.image_url} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                      )}
                    </span>
                    <span className="line-body">
                      <span className="line-title" title={candidate.title}>{cleanTitle(candidate.title)}</span>
                      <span className="num sub">{fmtPrice(candidate.price, candidate.currency)}</span>
                    </span>
                    <button type="button" className="btn sm outline" aria-label={`Remove ${candidate.title}`} onClick={() => toggle(item.item_id)}>Remove</button>
                  </li>
                ))}
              </ul>
              <div className="subtotal">
                <span>Subtotal</span>
                <span className="num">{fmtPrice(ls.reduce((a, l) => a + (l.candidate.price ?? 0), 0))}</span>
              </div>
              {url ? (
                <a className="btn primary" href={url} target="_blank" rel="noopener noreferrer">Go to checkout</a>
              ) : cartError && !busy ? (
                <button type="button" className="btn primary" onClick={() => void buildCarts().then(() => setBuiltFor(key))}>Try again</button>
              ) : (
                <button type="button" className="btn primary" disabled>Getting your checkout ready…</button>
              )}
            </section>
          );
        })}
      </div>

      <p className="note" role="status">We stop at checkout. No real orders are placed.</p>
      {cartError && <p className="note strong" role="alert">Couldn&apos;t build the cart: {cartError}</p>}
    </main>
  );
}
