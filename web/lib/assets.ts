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
  roomBefore: { file: "photos/office-before.webp", alt: "A bare wooden home office with an empty desk", size: "1100x825" },
  roomAfter: { file: "photos/office-after.webp", alt: "The same office styled with plants, art, a lamp and flowers", size: "1100x825" },
  productFloorLamp: { file: "product-floor-lamp.svg", alt: "Black arc floor lamp", size: "800x800" },
  productVase: { file: "product-vase.svg", alt: "Speckled ceramic vase", size: "800x800" },
  productRug: { file: "product-rug.svg", alt: "Textured rug", size: "800x800" },
  productDeskLamp: { file: "product-desk-lamp.svg", alt: "Brass desk lamp", size: "800x800" },
  productChair: { file: "product-chair.svg", alt: "Cream boucle accent chair", size: "800x800" },
  heroObject: { file: "hero-object.svg", alt: "", size: "600x600" },
  // Reference photos (local only; web/public/assets/photos/ is gitignored until rights are cleared).
  heroWoman: { file: "photos/hero-woman.webp", alt: "A shopper walking past a shop window with bags", size: "612x408" },
  tray: { file: "photos/tray.png", alt: "", size: "417x361 transparent" },
  skinSet: { file: "photos/skin-set.webp", alt: "Skincare set beside a glass vase of dried grasses", size: "900x1200" },
  skinShelf: { file: "photos/skin-shelf.webp", alt: "Skincare bottles on a marble shelf", size: "495x619" },
  skinBasket: { file: "photos/skin-basket.webp", alt: "Skincare in a woven basket", size: "399x501" },
  skinCounter: { file: "photos/skin-counter.webp", alt: "Skincare on a bathroom counter", size: "900x1200" },
  fitRackPlant: { file: "photos/fit-rack-plant.webp", alt: "Clothes rack beside a rubber plant", size: "452x678" },
  fitRackHat: { file: "photos/fit-rack-hat.webp", alt: "Neutral clothes and a straw hat on a rail", size: "400x600" },
  fitParis: { file: "photos/fit-paris.webp", alt: "A cream coat and trousers outfit on a Paris street", size: "900x1122" },
  roomChair: { file: "photos/room-chair.webp", alt: "A woven chair in a calm corner with a vase", size: "678x452" },
  roomGreen: { file: "photos/room-green.webp", alt: "A green sofa living room with abstract art", size: "819x1024" },
  roomBrown: { file: "photos/room-brown.webp", alt: "A cozy living room with a brown sofa, candles and a coffee table", size: "900x600" },
  roomColor: { file: "photos/room-color.webp", alt: "A bright living room with a green sofa", size: "627x489" },
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
