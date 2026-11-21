/**
 * DropZone: drag a video or photo from the file explorer onto the page, or tap to browse.
 * Boundary: presentational. It only hands the chosen File to `onFile`; uploading and starting a
 * run happen in the store. Works with keyboard (the label wraps a real file input).
 */
"use client";
import { useRef, useState } from "react";
import { UploadIcon } from "./Icons";

interface Props {
  onFile: (file: File) => void;
  busy?: boolean;
  /** Accepted kind, from the Video / Photo switch. */
  accept: string;
  fileName?: string | null;
}

/** @returns the drop area. */
export function DropZone({ onFile, busy, accept, fileName }: Props) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  function pick(files: FileList | null) {
    const f = files?.[0];
    if (f && !busy) onFile(f);
  }

  return (
    <label
      className={`dropzone ${over ? "over" : ""} ${busy ? "busy" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
    >
      <span className="dz-icon"><UploadIcon /></span>
      <span className="dz-title">{busy ? "Uploading…" : fileName ? fileName : "Drop a file here"}</span>
      <span className="dz-sub">{busy ? "Then we start looking" : "or tap to browse your files"}</span>
      <input ref={input} type="file" accept={accept} disabled={busy} onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
    </label>
  );
}
