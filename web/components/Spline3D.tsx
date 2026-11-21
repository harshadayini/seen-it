/**
 * Spline3D: one lazy-loaded Spline scene slot.
 * Use case: a small floating 3D object. The Spline runtime (large) is only downloaded when a
 * scene URL is configured, the slot is on screen, and the user has not asked for reduced motion;
 * otherwise a still fallback image or a labelled placeholder is shown.
 * Invariants: client-only (the runtime is imported inside an effect), cleans up the WebGL
 * context on unmount, and is decorative so it is hidden from screen readers.
 */
"use client";
import { useEffect, useRef, useState } from "react";
import { Asset } from "./Asset";
import type { AssetKey } from "@/lib/assets";

interface Props {
  /** Published Spline scene URL (.splinecode), or empty to show the fallback. */
  scene: string;
  className?: string;
  /** Still image shown until (or instead of) the live scene. */
  fallback?: AssetKey;
}

/** @returns the live 3D scene when allowed, else the still fallback. */
export function Spline3D({ scene, className = "", fallback = "heroObject" }: Props) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [ready, setReady] = useState(false);

  // Wait until the slot is on screen (and motion is allowed) before loading anything.
  useEffect(() => {
    if (!scene || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && (setVisible(true), io.disconnect()), { rootMargin: "120px" });
    io.observe(el);
    return () => io.disconnect();
  }, [scene]);

  // Load the runtime and the scene, then dispose on unmount.
  useEffect(() => {
    if (!visible || !scene) return;
    let cancelled = false;
    let app: { dispose?: () => void } | null = null;
    (async () => {
      try {
        const { Application } = await import("@splinetool/runtime");
        if (cancelled || !canvas.current) return;
        const a = new Application(canvas.current);
        app = a as unknown as { dispose?: () => void };
        await a.load(scene);
        if (!cancelled) setReady(true);
      } catch {
        // Keep the still fallback if the scene fails to load.
      }
    })();
    return () => {
      cancelled = true;
      app?.dispose?.();
    };
  }, [visible, scene]);

  return (
    <div ref={box} className={`spline ${className}`} aria-hidden="true">
      {!ready && <Asset name={fallback} className="fill" decorative />}
      {visible && <canvas ref={canvas} className="spline-canvas" style={{ opacity: ready ? 1 : 0 }} />}
    </div>
  );
}
