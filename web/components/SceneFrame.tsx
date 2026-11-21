/**
 * SceneFrame: the frame an object was found in, with its bounding box and a label.
 * Frame source, in order: the item's full frame + bbox (optional contract extension), else the
 * item's own crop with a box around all of it (the crop IS the tight box), else the labelled
 * sample scene art with a placeholder box.
 * Boundary: presentational. Never invents a box for a real frame; falls back honestly.
 */
"use client";
import { useState } from "react";
import { Asset } from "./Asset";
import { ConfidencePill } from "./ConfidencePill";
import { SAMPLE_BOXES, fileUrl } from "@/lib/config";
import { fmtRange } from "@/lib/format";
import type { Item } from "@/lib/types";

interface Props {
  item: Item;
  index: number;
  best?: { p_same_product?: number | null };
}

/** @returns the framed image with the box, label and time chip. Remount with a key per item. */
export function SceneFrame({ item, index, best }: Props) {
  const [failed, setFailed] = useState(false);
  const frame = item.frame_path && item.bbox?.length === 4 ? item.frame_path : null;
  const src = frame ?? item.crop_path ?? null;
  const showReal = !!src && !failed;
  const box: readonly number[] = frame && item.bbox ? item.bbox : showReal ? [0.05, 0.05, 0.95, 0.95] : SAMPLE_BOXES[index % SAMPLE_BOXES.length];
  const [y0, x0, y1, x1] = box;
  const label = String(item.attributes?.category ?? "item");

  return (
    <div className="sframe">
      {showReal ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="sframe-img" src={fileUrl(src!)} alt={item.description ?? "Found item"} onError={() => setFailed(true)} />
      ) : (
        <Asset name="scanRoom" className="fill" />
      )}
      <div
        className={`sbox ${item.status === "none" ? "dashed" : ""}`}
        style={{ top: `${y0 * 100}%`, left: `${x0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
      >
        <span className="sbox-tag">
          {label} <ConfidencePill status={item.status} p={best?.p_same_product} />
        </span>
        <span className="corner tl" /><span className="corner tr" /><span className="corner bl" /><span className="corner br" />
      </div>
      <span className="time-chip num">{fmtRange(item.t_start, item.t_end)}</span>
      {!showReal && <span className="sample-chip">Sample frame</span>}
    </div>
  );
}
