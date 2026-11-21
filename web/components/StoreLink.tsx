/**
 * StoreLink: opens a matched product on the merchant's own Shopify storefront (new tab).
 * Boundary: presentational. Renders nothing unless the backend supplied an https `product_url`,
 * so it never links to a made-up address.
 */
import type { Candidate } from "@/lib/types";

/** @param candidate the matched product @param className link style @param label visible text */
export function StoreLink({ candidate, className = "link", label = "View on store ↗" }: { candidate?: Candidate | null; className?: string; label?: string }) {
  const href = candidate?.product_url;
  if (!href || !href.startsWith("https://")) return null;
  return (
    <a href={href} className={className} target="_blank" rel="noopener noreferrer" aria-label={`${label.replace(" ↗", "")}: ${candidate?.title ?? "product"} (opens in a new tab)`} onClick={(e) => e.stopPropagation()}>
      {label}
    </a>
  );
}
