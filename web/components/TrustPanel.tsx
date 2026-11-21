/**
 * TrustPanel: four short promises with custom two-tone icons, in a soft rounded panel.
 * Boundary: presentational and static. Every promise matches how the app really behaves
 * (real catalog items, honest scores, previews, merchants' own checkout, nothing charged here).
 */
import type { ReactNode } from "react";

/** Shared SVG frame: 32px grid, 1.7px rounded strokes, soft tinted fills via currentColor. */
function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 32 32" width="34" height="34" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

const ITEMS: { title: string; note: string; tone: string; icon: ReactNode }[] = [
  {
    title: "Real products",
    note: "Live from Shopify stores",
    tone: "sage",
    // A shopping bag with a price tag.
    icon: (
      <Icon>
        <path d="M6.5 11h19l-1.5 15.2a2 2 0 0 1-2 1.8H10a2 2 0 0 1-2-1.8L6.5 11z" fill="currentColor" fillOpacity="0.14" />
        <path d="M11.5 11V9.5a4.5 4.5 0 0 1 9 0V11" />
        <path d="M20.2 16.3h-3.1l-3.9 3.9a1.4 1.4 0 0 0 0 2l1.7 1.7a1.4 1.4 0 0 0 2 0l3.9-3.9z" fill="#f4f3ee" />
        <circle cx="18.6" cy="18" r="0.9" fill="currentColor" stroke="none" />
      </Icon>
    ),
  },
  {
    title: "Honest scores",
    note: "Exact, similar, or none",
    tone: "sand",
    // A dial with a needle and tick marks.
    icon: (
      <Icon>
        <path d="M5 22a11 11 0 0 1 22 0" fill="currentColor" fillOpacity="0.14" />
        <path d="M5 22a11 11 0 0 1 22 0z" />
        <path d="M16 22l5.2-7.2" strokeWidth="2" />
        <circle cx="16" cy="22" r="1.9" fill="currentColor" />
        <path d="M8.2 15.3l1.4 1M16 9.8v1.7M23.8 15.3l-1.4 1" />
        <path d="M11 26.5h10" />
      </Icon>
    ),
  },
  {
    title: "See it first",
    note: "Preview in your room",
    tone: "deep",
    // Corner brackets around an eye: preview before you commit.
    icon: (
      <Icon>
        <path d="M4.5 11V8a3.5 3.5 0 0 1 3.5-3.5h3M21 4.5h3a3.5 3.5 0 0 1 3.5 3.5v3M27.5 21v3a3.5 3.5 0 0 1-3.5 3.5h-3M11 27.5H8A3.5 3.5 0 0 1 4.5 24v-3" />
        <path d="M8.8 16s2.9-4.9 7.2-4.9 7.2 4.9 7.2 4.9-2.9 4.9-7.2 4.9S8.8 16 8.8 16z" fill="currentColor" fillOpacity="0.14" />
        <circle cx="16" cy="16" r="2.5" />
      </Icon>
    ),
  },
  {
    title: "Their checkout",
    note: "Nothing charged here",
    tone: "sand",
    // A storefront with an awning and a door.
    icon: (
      <Icon>
        <path d="M5 13l2.2-6.5h17.6L27 13" />
        <path d="M5 13a3.7 3.7 0 0 0 7.3 0 3.7 3.7 0 0 0 7.4 0 3.7 3.7 0 0 0 7.3 0" />
        <path d="M7 15.2V26h18V15.2" fill="currentColor" fillOpacity="0.14" />
        <rect x="13" y="19" width="6" height="7" rx="1.2" />
        <path d="M10.2 20.5h0M21.8 20.5h0" strokeWidth="2.4" />
      </Icon>
    ),
  },
];

/** @returns the panel. */
export function TrustPanel() {
  return (
    <ul className="trust" aria-label="What to expect">
      {ITEMS.map((it) => (
        <li key={it.title} className="trust-item">
          <span className={`trust-ico ${it.tone}`}>{it.icon}</span>
          <strong>{it.title}</strong>
          <span>{it.note}</span>
        </li>
      ))}
    </ul>
  );
}
