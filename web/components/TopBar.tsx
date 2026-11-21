/**
 * TopBar: the laptop header. Brand on the left; on the right a small "How good is it?" link
 * (the evidence page, outside the main flow) and the cart with its item count.
 * Boundary: navigation only. Replaces the phone-style bottom TabBar (which is kept, unused).
 */
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BagIcon } from "@/components/Icons";
import { useStore } from "@/lib/store";

/** @returns the sticky top bar. */
export function TopBar() {
  const path = usePathname();
  const { lines } = useStore();
  // The landing page keeps its own look (nav pill and bottom tab bar), so no top bar there.
  if (path === "/") return null;
  return (
    <header className="topbar">
      <div className="topbar-in">
        <Link href="/" className="brand" aria-label="Seen It, start over">
          <span className="brand-mark" aria-hidden="true">s</span>
          Seen It
        </Link>
        <nav aria-label="Main" className="topnav">
          <Link href="/stress" className="navlink" aria-current={path === "/stress" ? "page" : undefined}>Stress test</Link>
          <Link href="/evidence" className="navlink" aria-current={path === "/evidence" ? "page" : undefined}>How good is it?</Link>
          <Link href="/cart" className="cartlink" aria-current={path === "/cart" ? "page" : undefined}>
            <BagIcon />
            <span>Cart</span>
            {lines.length > 0 && <b className="count" aria-label={`${lines.length} items`}>{lines.length}</b>}
          </Link>
        </nav>
      </div>
    </header>
  );
}
