/**
 * Screen 1, Start: one question, one input, one button. Pasting a video link and pressing
 * "Find products" starts a run on the backend and moves straight to Results.
 * Boundary: no options, settings or toggles. Desk mode, photos and the collage sections are out of
 * the flow (their files are kept). If a run already exists, a small link returns to it.
 */
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useStore } from "@/lib/store";

/** @returns the Start screen. */
export default function StartPage() {
  const { run, startRun, starting, startError } = useStore();
  const router = useRouter();
  const [link, setLink] = useState("");

  /** Starts the run for the pasted link, then shows Results (items appear there as they finish). */
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (await startRun(link, "video")) router.push("/results");
  }

  return (
    <main id="main" className="start">
      <h1 className="start-h">Every video becomes shoppable.</h1>
      <form className="start-form" onSubmit={submit}>
        <label className="sr-only" htmlFor="video-link">Video link</label>
        <input
          id="video-link"
          type="text"
          inputMode="url"
          autoComplete="off"
          autoFocus
          placeholder="Paste a video link"
          value={link}
          onChange={(e) => setLink(e.target.value)}
        />
        <button type="submit" className="btn primary" disabled={starting}>
          {starting ? "Starting…" : "Find products"}
        </button>
      </form>
      <p className="start-line">We find the products in your video and match them to real shops.</p>
      {startError && <p className="note strong" role="alert">{startError}</p>}
      {run && !starting && <Link href="/results" className="link">Back to your last video</Link>}
    </main>
  );
}
