/**
 * Asset / ProductImage: render an image from lib/assets.ts, or a flat labelled placeholder
 * tile (showing the file name and size) until the real file exists.
 * Boundary: presentational. ProductImage prefers the merchant's own image URL (never re-hosted)
 * and only falls back to the stand-in asset if that URL fails to load.
 */
"use client";
import { useEffect, useRef, useState } from "react";
import { ASSETS, assetUrl, PRODUCT_FALLBACK, type AssetKey } from "@/lib/assets";
import { fileUrl } from "@/lib/config";

interface AssetProps {
  name: AssetKey;
  className?: string;
  /** CSS object-position, used to fake circular crops of a larger scene. */
  position?: string;
  decorative?: boolean;
}

/** @returns the image once it loads, otherwise a labelled placeholder tile. */
export function Asset({ name, className = "", position, decorative }: AssetProps) {
  const spec = ASSETS[name];
  const [ok, setOk] = useState(false);
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (el && el.complete && el.naturalWidth > 0) setOk(true);
  }, []);

  return (
    <div className={`asset ${className}`}>
      {!ok && (
        <div className="ph" role={decorative ? undefined : "img"} aria-label={decorative ? undefined : `${spec.alt} (placeholder)`} aria-hidden={decorative || undefined}>
          <span className="mono">{spec.file}</span>
          <span className="mono ph-size">{spec.size}</span>
        </div>
      )}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={ref}
        src={assetUrl(name)}
        alt={decorative ? "" : spec.alt}
        style={{ objectPosition: position, opacity: ok ? 1 : 0 }}
        onLoad={() => setOk(true)}
        onError={() => setOk(false)}
      />
    </div>
  );
}

interface CropImageProps {
  /** Contract `crop_path`, e.g. "frames/r_001/i1.jpg". */
  path?: string | null;
  /** Placeholder view of the scan image used until a real crop exists. */
  position?: string;
  className?: string;
}

/** @returns the real item crop written by the backend, or a placeholder crop of the scan image. */
export function CropImage({ path, position, className = "" }: CropImageProps) {
  const [failed, setFailed] = useState(!path);
  if (failed || !path) return <Asset name="scanRoom" className={className} position={position} decorative />;
  return (
    <div className={`asset ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={fileUrl(path)} alt="" onError={() => setFailed(true)} />
    </div>
  );
}

interface ProductImageProps {
  url?: string | null;
  alt: string;
  category?: string | null;
  className?: string;
}

/** @returns the merchant's image on a flat tinted tile, or the stand-in asset if it fails. */
export function ProductImage({ url, alt, category, className = "" }: ProductImageProps) {
  const [failed, setFailed] = useState(!url);
  const key = PRODUCT_FALLBACK[category ?? ""] ?? "productVase";
  return (
    <div className={`tile ${className}`}>
      {failed ? (
        <Asset name={key} className="fill" />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url!} alt={alt} onError={() => setFailed(true)} className="merchant-img" />
      )}
    </div>
  );
}
