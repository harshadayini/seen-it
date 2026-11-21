/**
 * SeeItHere: the "See it in your space" flow, a full-screen dialog opened from an item's detail panel.
 * Steps: choose a scene (live camera, or upload a photo or video) -> for a video, pick one of its
 * frames -> tap where the product should go (optional) -> place it (honest progress while the
 * backend works, about 15 to 20 s) -> before/after result with a plain-words check -> Try again,
 * Add to cart or Change scene.
 * Boundary: talks to the backend only through lib/preview.ts. Never shows a placeholder as if it
 * were a result: a failure or network error is a message with a retry. The user's photo goes only
 * to our backend (and, to make the preview, to Google's Gemini); nothing goes to Shopify.
 */
"use client";
import { useEffect, useRef, useState } from "react";
import { CheckIcon, PlusIcon } from "@/components/Icons";
import { SceneCamera } from "@/components/SceneCamera";
import { StoreLink } from "@/components/StoreLink";
import { fileUrl } from "@/lib/config";
import { bestCandidate, checkWords, fmtPrice, merchantName } from "@/lib/format";
import { GIVE_UP_SECONDS, getPreview, POLL_SECONDS, startPreview, uploadScene } from "@/lib/preview";
import type { Item } from "@/lib/types";

type Step = "choose" | "camera" | "uploading" | "frames" | "tap" | "placing" | "result" | "error";
type Anchor = { x: number; y: number };

interface Scene {
  kind: "camera" | "image" | "video";
  sceneId?: string;
  /** A camera still as a data URL (no server round trip until Place it). */
  dataUrl?: string;
  /** Image URLs to show: the data URL, or the backend's frames. */
  frames: string[];
  index: number;
}

interface Props {
  runId: string;
  item: Item;
  inCart: boolean;
  onToggleCart: () => void;
  onClose: () => void;
}

const PRIVACY = "Your photo goes to our server and to Google's Gemini to make the preview. It's saved on our server only and isn't shared with Shopify.";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Before/after curtain over two real images; the container takes the scene's own proportions. */
function BeforeAfter({ before, after }: { before: string; after: string }) {
  const [pos, setPos] = useState(50);
  const [ratio, setRatio] = useState<string>("4 / 3");
  return (
    <div className="compare ba" style={{ ["--pos" as string]: `${pos}%`, aspectRatio: ratio }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="ba-img" src={before} alt="Your scene, before" onLoad={(e) => setRatio(`${e.currentTarget.naturalWidth} / ${e.currentTarget.naturalHeight}`)} />
      <div className="after">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="ba-img" src={after} alt="Your scene with the product placed in it" />
      </div>
      <span className="tag tag-l">Before</span>
      <span className="tag tag-r">After</span>
      <span className="handle" aria-hidden="true" />
      <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(Number(e.target.value))} aria-label="Slide to compare before and after" aria-valuetext={`${pos}% of the after image shown`} />
    </div>
  );
}

/** @returns the dialog. Side effects: uploads, preview requests and polling, all cancelled on close. */
export function SeeItHere({ runId, item, inCart, onToggleCart, onClose }: Props) {
  const best = bestCandidate(item);
  const [step, setStep] = useState<Step>("choose");
  const [scene, setScene] = useState<Scene | null>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<{ path: string; fidelity: number | null; v: number } | null>(null);
  const job = useRef(0);
  const fileInput = useRef<HTMLInputElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const closeFn = useRef(onClose);
  closeFn.current = onClose;

  // Esc closes (without also closing the panel behind); Tab stays inside the dialog; focus returns on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        closeFn.current();
      } else if (e.key === "Tab" && card.current) {
        const f = [...card.current.querySelectorAll<HTMLElement>("button:not([disabled]), input, [href], [tabindex]:not([tabindex='-1'])")].filter((el) => el.offsetParent !== null);
        if (f.length === 0) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    window.addEventListener("keydown", onKey, true);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = "";
      job.current++; // cancels any polling in flight
      opener?.focus?.();
    };
  }, []);

  // Move focus to the step heading whenever the step changes, so screen readers announce it.
  useEffect(() => { title.current?.focus(); }, [step]);

  // Elapsed seconds while placing.
  useEffect(() => {
    if (step !== "placing") return;
    const t0 = Date.now();
    setElapsed(0);
    const t = setInterval(() => setElapsed(Math.round((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(t);
  }, [step]);

  /** Uploads a chosen file; a video leads to the frame picker, a photo straight to the tap step. */
  async function onFile(file: File | undefined) {
    if (!file) return;
    setNotice(null);
    if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) {
      setNotice("Please choose a photo or a video.");
      return;
    }
    setStep("uploading");
    try {
      const up = await uploadScene(file);
      const frames = up.frames.map((p) => fileUrl(p));
      setScene({ kind: up.kind, sceneId: up.scene_id, frames, index: Math.min(Math.max(up.default, 0), frames.length - 1) });
      setAnchor(null);
      setStep(up.kind === "video" && frames.length > 1 ? "frames" : "tap");
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "The upload didn't work.");
      setStep("choose");
    }
  }

  /** A camera still is kept in the browser until Place it. */
  function onCapture(dataUrl: string) {
    setScene({ kind: "camera", dataUrl, frames: [dataUrl], index: 0 });
    setAnchor(null);
    setNotice(null);
    setStep("tap");
  }

  /** Starts the preview and polls every POLL_SECONDS until it is done or has failed. */
  async function place(a: Anchor | null) {
    if (!scene) return;
    const mine = ++job.current;
    setStep("placing");
    setError(null);
    try {
      await startPreview({ runId, itemId: item.item_id, sceneId: scene.sceneId, frameIndex: scene.index, sceneImage: scene.dataUrl, anchor: a });
      const t0 = Date.now();
      let misses = 0;
      while (mine === job.current) {
        await sleep(POLL_SECONDS * 1000);
        if (mine !== job.current) return;
        let s;
        try {
          s = await getPreview(runId, item.item_id);
          misses = 0;
        } catch (e) {
          if (++misses >= 3) throw e; // one dropped poll is fine; three in a row is not
          continue;
        }
        if (s.status === "done" && s.preview?.image_path) {
          setResult({ path: s.preview.image_path, fidelity: s.preview.fidelity ?? null, v: Date.now() });
          setStep("result");
          return;
        }
        if (s.status === "failed") throw new Error(s.error || "The preview couldn't be made.");
        if (s.status === "none") throw new Error("The preview didn't start. Please try again.");
        if ((Date.now() - t0) / 1000 > GIVE_UP_SECONDS) throw new Error("This is taking much longer than usual.");
      }
    } catch (e) {
      if (mine === job.current) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
        setStep("error");
      }
    }
  }

  /** Taps (or arrow keys) set the anchor as fractions of the displayed image. */
  function onTap(e: React.MouseEvent<HTMLDivElement>) {
    const img = e.currentTarget.querySelector("img");
    if (!img) return;
    const r = img.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width;
    const y = (e.clientY - r.top) / r.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    setAnchor({ x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000 });
  }
  function onTapKey(e: React.KeyboardEvent<HTMLDivElement>) {
    const d = e.shiftKey ? 0.1 : 0.03;
    const move: Record<string, [number, number]> = { ArrowLeft: [-d, 0], ArrowRight: [d, 0], ArrowUp: [0, -d], ArrowDown: [0, d] };
    const m = move[e.key];
    if (!m) return;
    e.preventDefault();
    const cur = anchor ?? { x: 0.5, y: 0.5 };
    setAnchor({ x: Math.min(1, Math.max(0, cur.x + m[0])), y: Math.min(1, Math.max(0, cur.y + m[1])) });
  }

  const sceneSrc = scene ? scene.frames[scene.index] : "";
  const check = result ? checkWords(result.fidelity) : null;
  const heading: Record<Step, string> = {
    choose: "See it in your space",
    camera: "Take a photo of your space",
    uploading: "Uploading…",
    frames: "Pick the best frame",
    tap: "Tap where it should go",
    placing: "Placing it in your scene…",
    result: "Here it is in your space",
    error: "That didn't work",
  };

  return (
    <div className="seeit" role="dialog" aria-modal="true" aria-labelledby="seeit-h">
      <div className="seeit-card" ref={card}>
        <div className="seeit-head">
          <div>
            <h2 id="seeit-h" className="seeit-title" tabIndex={-1} ref={title}>{heading[step]}</h2>
            {best && <p className="sub">{best.title}</p>}
          </div>
          <button type="button" className="btn sm outline" onClick={onClose}>Close</button>
        </div>

        {step === "choose" && (
          <div className="seeit-body">
            <p className="body">Put this product in a photo of your own space.</p>
            <div className="row-actions-inline">
              <button type="button" className="btn primary" onClick={() => { setNotice(null); setStep("camera"); }}>Take a photo</button>
              <button type="button" className="btn outline" onClick={() => fileInput.current?.click()}>Upload a photo or video</button>
              <input ref={fileInput} type="file" accept="image/*,video/*" className="sr-only" tabIndex={-1} aria-hidden="true" onChange={(e) => { void onFile(e.target.files?.[0]); e.target.value = ""; }} />
            </div>
            {notice && <p className="note strong" role="alert">{notice}</p>}
            <p className="note">{PRIVACY}</p>
          </div>
        )}

        {step === "camera" && (
          <div className="seeit-body">
            <SceneCamera
              onCapture={onCapture}
              onBack={() => setStep("choose")}
              onUnavailable={(m) => { setNotice(m); setStep("choose"); }}
            />
          </div>
        )}

        {step === "uploading" && (
          <div className="seeit-body" role="status">
            <p className="what"><span className="dot" aria-hidden="true" />Uploading your file. A video takes a little longer.</p>
          </div>
        )}

        {step === "frames" && scene && (
          <div className="seeit-body">
            <p className="body">Choose the frame that shows your space best.</p>
            <ul className="frames" aria-label="Frames from your video">
              {scene.frames.map((f, i) => (
                <li key={f}>
                  <button type="button" className={`frame ${i === scene.index ? "on" : ""}`} aria-pressed={i === scene.index} onClick={() => setScene({ ...scene, index: i })}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={f} alt={`Frame ${i + 1} of ${scene.frames.length}`} />
                  </button>
                </li>
              ))}
            </ul>
            <div className="row-actions-inline">
              <button type="button" className="btn primary" onClick={() => setStep("tap")}>Use this frame</button>
              <button type="button" className="btn outline" onClick={() => setStep("choose")}>Change scene</button>
            </div>
          </div>
        )}

        {step === "tap" && scene && (
          <div className="seeit-body">
            <p className="body">Tap the spot, or use the arrow keys. You can also skip and let us choose.</p>
            <div
              className="tapbox"
              role="application"
              tabIndex={0}
              aria-label="Image: tap or use arrow keys to set where the product should go"
              onClick={onTap}
              onKeyDown={onTapKey}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={sceneSrc} alt="Your scene" draggable={false} />
              {anchor && <span className="marker" style={{ left: `${anchor.x * 100}%`, top: `${anchor.y * 100}%` }} aria-hidden="true" />}
            </div>
            <p className="sr-only" role="status">{anchor ? `Spot set at ${Math.round(anchor.x * 100)} percent across, ${Math.round(anchor.y * 100)} percent down.` : "No spot set."}</p>
            <div className="row-actions-inline">
              <button type="button" className="btn primary" disabled={!anchor} onClick={() => void place(anchor)}>Place it</button>
              <button type="button" className="btn outline" onClick={() => void place(null)}>Skip</button>
              <button type="button" className="btn outline" onClick={() => setStep("choose")}>Change scene</button>
            </div>
            <p className="note">{PRIVACY}</p>
          </div>
        )}

        {step === "placing" && scene && (
          <div className="seeit-body" role="status" aria-live="polite">
            <div className="tapbox working">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={sceneSrc} alt="" />
              {anchor && <span className="marker" style={{ left: `${anchor.x * 100}%`, top: `${anchor.y * 100}%` }} aria-hidden="true" />}
            </div>
            <p className="what"><span className="dot" aria-hidden="true" />Placing it in your scene… about 15 s <span className="num secs">· {elapsed} s</span></p>
            {elapsed > 30 && <p className="note">Taking a little longer than usual. Still working.</p>}
          </div>
        )}

        {step === "result" && scene && result && check && (
          <div className="seeit-body">
            <BeforeAfter before={sceneSrc} after={`${fileUrl(result.path)}?v=${result.v}`} />
            <div className="seeit-meta">
              <div>
                <p className="rname">{best?.title ?? item.description}</p>
                <p className="sub">{merchantName(best?.merchant_domain)} · <span className="num">{fmtPrice(best?.price, best?.currency)}</span> <StoreLink candidate={best} className="alt-link" label="View ↗" /></p>
              </div>
              <p className={`label ${check.tone}`}>{check.text}</p>
            </div>
            <div className="row-actions-inline">
              <button type="button" className="btn outline" onClick={() => void place(anchor)}>Try again</button>
              <button type="button" className="btn outline" onClick={() => setStep("tap")}>Pick a new spot</button>
              {best?.variant_id && (
                <button type="button" className={`btn ${inCart ? "primary" : "outline"}`} aria-pressed={inCart} onClick={onToggleCart}>
                  {inCart ? <CheckIcon /> : <PlusIcon />}
                  {inCart ? "In cart" : "Add to cart"}
                </button>
              )}
              <button type="button" className="btn outline" onClick={() => setStep("choose")}>Change scene</button>
            </div>
          </div>
        )}

        {step === "error" && (
          <div className="seeit-body">
            <p className="note strong" role="alert">{error}</p>
            <div className="row-actions-inline">
              {scene && <button type="button" className="btn primary" onClick={() => void place(anchor)}>Try again</button>}
              <button type="button" className="btn outline" onClick={() => setStep("choose")}>Change scene</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
