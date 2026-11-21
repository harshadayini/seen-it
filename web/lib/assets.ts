/**
 * Asset map: the ONE place that names every image the UI uses.
 * Drop files into web/public/assets/ with these exact names and they replace the labelled
 * placeholder tiles automatically. Nothing else in the app hardcodes an asset path.
 * Boundary: decorative / demo imagery only. Real product results always render the merchant's
 * own image_url (never re-hosted); these product files are only stand-ins when that URL fails.
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
  scanRoom: { file: "scan-room.jpg", alt: "Warm living room with a floor lamp, vase, rug and chair", size: "1170x1900" },
  deskEmpty: { file: "desk-empty.jpg", alt: "Empty wooden desk by a window", size: "1600x1200" },
  roomBefore: { file: "room-before.jpg", alt: "Room corner before adding the product", size: "1600x1200" },
  roomAfter: { file: "room-after.jpg", alt: "The same room corner with the product placed", size: "1600x1200" },
  productFloorLamp: { file: "product-floor-lamp.png", alt: "Black arc floor lamp", size: "800x800" },
  productVase: { file: "product-vase.png", alt: "Speckled ceramic vase", size: "800x800" },
  productRug: { file: "product-rug.png", alt: "Textured rug", size: "800x800" },
  productDeskLamp: { file: "product-desk-lamp.png", alt: "Brass desk lamp", size: "800x800" },
  productChair: { file: "product-chair.png", alt: "Cream boucle accent chair", size: "800x800" },
  stickerCamera: { file: "sticker-camera.png", alt: "", size: "400x400" },
  stickerPlant: { file: "sticker-plant.png", alt: "", size: "400x400" },
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
