/** Small inline SVG icons (stroke style). Decorative: always paired with a text label or aria-label. */
import type { SVGProps } from "react";

const base: SVGProps<SVGSVGElement> = {
  width: 22, height: 22, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
  strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true,
};

export const ScanIcon = () => (<svg {...base}><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2" /><circle cx="12" cy="12" r="3" /></svg>);
export const ListIcon = () => (<svg {...base}><path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01" /></svg>);
export const BagIcon = () => (<svg {...base}><path d="M5 8h14l-1 12H6L5 8z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></svg>);
export const BackIcon = () => (<svg {...base} width={18} height={18}><path d="M19 12H5M11 18l-6-6 6-6" /></svg>);
export const ArrowIcon = () => (<svg {...base}><path d="M5 12h14M13 6l6 6-6 6" /></svg>);
export const ExpandIcon = () => (<svg {...base}><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>);
export const UploadIcon = () => (<svg {...base}><path d="M12 16V4M7 9l5-5 5 5M5 20h14" /></svg>);
export const SearchIcon = () => (<svg {...base}><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5" /></svg>);
export const PlusIcon = () => (<svg {...base}><path d="M12 5v14M5 12h14" /></svg>);
export const CheckIcon = () => (<svg {...base}><path d="M5 12l5 5 9-10" /></svg>);
