/**
 * TabBar: the bottom pill navigation (Scan, Results, Cart). Cart shows how many items are in it.
 * Boundary: navigation only. Highlights the current route and exposes it with aria-current.
 */
"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BagIcon, ListIcon, PulseIcon, ScanIcon } from "./Icons";
import { useStore } from "@/lib/store";

const TABS = [
  { href: "/", label: "Scan", Icon: ScanIcon },
  { href: "/results", label: "Results", Icon: ListIcon },
  { href: "/stress", label: "Stress", Icon: PulseIcon },
  { href: "/cart", label: "Cart", Icon: BagIcon },
] as const;

/** @returns the floating tab bar. */
export function TabBar() {
  const path = usePathname();
  const { lines } = useStore();
  // Only the landing page uses the bottom tab bar; every other page uses the top bar.
  if (path !== "/") return null;
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ href, label, Icon }) => {
        const active = href === "/"; // this bar only appears on the landing page
        return (
          <Link key={href} href={href} className={`tab ${active ? "on" : ""}`} aria-current={active ? "page" : undefined}>
            <Icon />
            <span>{label}</span>
            {href === "/cart" && lines.length > 0 && <b className="count" aria-label={`${lines.length} items`}>{lines.length}</b>}
          </Link>
        );
      })}
    </nav>
  );
}
