/**
 * Asset map: the ONE place that names every image the UI uses.
 * Drop files into web/public/assets/ with these exact names and they replace the labelled
 * placeholder tiles automatically. Nothing else in the app hardcodes an asset path.
 * Boundary: decorative / demo imagery only. Real product results always render the merchant's
 * own image_url (never re-hosted); the product files are only stand-ins when that URL fails.
 */

export interface AssetSpec {
  /** File name inside web/public/assets/. */
  file: string;
  /** Accessible description. */
  alt: string;
  /** Intended size and ratio, shown on the placeholder tile. */
  size: string;
}

export const ASSETS = {
  scanRoom: { file: "scan-room.svg", alt: "Calm living room with a floor lamp, vase, rug and chair", size: "1170x1460" },
  deskEmpty: { file: "desk-empty.svg", alt: "Empty wooden desk by a window", size: "1600x1200" },
  roomBefore: { file: "room-before.svg", alt: "Room corner before adding the product", size: "1600x2000" },
  roomAfter: { file: "room-after.svg", alt: "The same room corner with the product placed", size: "1600x2000" },
  productFloorLamp: { file: "product-floor-lamp.svg", alt: "Black arc floor lamp", size: "800x800" },
  productVase: { file: "product-vase.svg", alt: "Speckled ceramic vase", size: "800x800" },
  productRug: { file: "product-rug.svg", alt: "Textured rug", size: "800x800" },
  productDeskLamp: { file: "product-desk-lamp.svg", alt: "Brass desk lamp", size: "800x800" },
  productChair: { file: "product-chair.svg", alt: "Cream boucle accent chair", size: "800x800" },
  heroObject: { file: "hero-object.svg", alt: "", size: "600x600" },
} as const satisfies Record<string, AssetSpec>;

export type AssetKey = keyof typeof ASSETS;

/** Stand-in product image per catalog category, used only when the merchant image fails to load. */
export const PRODUCT_FALLBACK: Record<string, AssetKey> = {
  lighting: "productFloorLamp",
  seating: "productChair",
  decor: "productVase",
  rugs: "productRug",
  desk: "productDeskLamp",
};

/** Public URL for an asset. @param key asset key @returns e.g. /assets/scan-room.jpg */
export function assetUrl(key: AssetKey): string {
  return `/assets/${ASSETS[key].file}`;
}
