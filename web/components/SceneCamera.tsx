/**
 * SceneCamera: a live camera view for "See it here". Opens the rear camera on phones (the laptop
 * webcam otherwise), and "Capture" returns one JPEG still, downscaled to at most CAPTURE_MAX_PX on
 * its longest side, as a data URL. Stops the camera when it closes.
 * Boundary: the picture goes nowhere on its own; the parent decides what to do with it. If the
 * camera cannot start (blocked, missing, or an insecure page) it reports a plain message so the
 * parent can offer the upload instead.
 */
"use client";
import { useEffect, useRef, useState } from "react";
import { CAPTURE_MAX_PX } from "@/lib/preview";

interface Props {
  onCapture: (dataUrl: string) => void;
  onBack: () => void;
  /** Called with a plain message when the camera cannot be used. */
  onUnavailable: (message: string) => void;
}

/** Maps a getUserMedia failure to a message a person can act on. */
function cameraMessage(e: unknown): string {
  const name = e instanceof DOMException ? e.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera access was blocked. Allow it in your browser's site settings, or upload a photo instead.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No camera was found on this device. Upload a photo instead.";
  if (name === "NotReadableError") return "The camera is being used by another app. Close it and try again, or upload a photo instead.";
  return "The camera couldn't start. You can upload a photo instead.";
}

/** @returns the live view with a Capture button. Side effects: opens and stops the camera stream. */
export function SceneCamera({ onCapture, onBack, onUnavailable }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [ready, setReady] = useState(false);
  const unavailable = useRef(onUnavailable);
  unavailable.current = onUnavailable;

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    async function open() {
      if (!navigator.mediaDevices?.getUserMedia) {
        unavailable.current("The camera needs a secure page (https or localhost). Upload a photo instead.");
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        if (video.current) {
          video.current.srcObject = stream;
          await video.current.play().catch(() => {});
        }
      } catch (e) {
        if (!cancelled) unavailable.current(cameraMessage(e));
      }
    }
    void open();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  /** Draws the current frame to a canvas at most CAPTURE_MAX_PX on its longest side. */
  function capture() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const scale = Math.min(1, CAPTURE_MAX_PX / Math.max(v.videoWidth, v.videoHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(v.videoWidth * scale);
    c.height = Math.round(v.videoHeight * scale);
    c.getContext("2d")?.drawImage(v, 0, 0, c.width, c.height);
    onCapture(c.toDataURL("image/jpeg", 0.85));
  }

  return (
    <div className="cam">
      <div className="cam-box">
        <video ref={video} playsInline muted autoPlay onPlaying={() => setReady(true)} aria-label="Live camera" />
        {!ready && <p className="video-empty">Starting the camera…</p>}
      </div>
      <div className="row-actions-inline">
        <button type="button" className="btn primary" onClick={capture} disabled={!ready}>Capture</button>
        <button type="button" className="btn outline" onClick={onBack}>Back</button>
      </div>
    </div>
  );
}
