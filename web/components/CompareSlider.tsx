/**
 * CompareSlider: before/after curtain. Drag, swipe, or use the arrow keys to reveal the
 * "after" image over the "before" one.
 * Boundary: presentational. Built on a native range input so it is keyboard and screen-reader
 * accessible; the handle is decoration. Reveal uses clip-path, so there is no layout shift.
 */
"use client";
import { useState } from "react";
import { Asset } from "./Asset";
import type { AssetKey } from "@/lib/assets";

interface Props {
  before: AssetKey;
  after: AssetKey;
}

/** @returns the slider card. */
export function CompareSlider({ before, after }: Props) {
  const [pos, setPos] = useState(50);
  return (
    <div className="compare" style={{ ["--pos" as string]: `${pos}%` }}>
      <Asset name={before} className="fill" />
      <div className="after">
        <Asset name={after} className="fill" />
      </div>
      <span className="tag tag-l">Before</span>
      <span className="tag tag-r">After</span>
      <span className="handle" aria-hidden="true" />
      <input
        type="range"
        min={0}
        max={100}
        value={pos}
        onChange={(e) => setPos(Number(e.target.value))}
        aria-label="Slide to compare before and after"
        aria-valuetext={`${pos}% of the after image shown`}
      />
    </div>
  );
}
