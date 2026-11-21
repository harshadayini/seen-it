/**
 * Stress page: shows how the models are stress-tested.
 * We damage a clip on purpose (shake, noise, low light, blur) and ask the real pipeline what it can
 * still find in each, then compare with what it finds in the clean clip. No repair is applied: the
 * models see the damaged clip exactly as it is, so the page shows where they hold and where they break.
 * Boundary: results come only from the backend (POST /stress). Scores are recall against what the
 * model finds on the CLEAN clip, not against human labels, and the page says so.
 */
"use client";
import { useState } from "react";
import { DropZone } from "@/components/DropZone";
import { API_URL, fileUrl } from "@/lib/config";
import { pct } from "@/lib/format";
import { useStore } from "@/lib/store";
import { useStress, type StressCondition } from "@/lib/useStress";

const WHAT = [
  { id: "shaky", name: "Shaky camera", blurb: "Handheld wobble and motion blur" },
  { id: "noisy", name: "Heavy noise", blurb: "Grainy, cheap-sensor footage" },
  { id: "dark", name: "Low light", blurb: "Dim room, underexposed" },
  { id: "blurry", name: "Soft and tiny", blurb: "Low-res upload stretched up" },
];

/** A frame with a caption; the image fills its whole box. */
function Shot({ src, caption }: { src: string; caption: string }) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="shot-mini">
      <div className="shot-frame">
        {failed ? <span className="tile-note">No frame</span> : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={fileUrl(src)} alt={caption} onError={() => setFailed(true)} />
        )}
      </div>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

/** One condition: the clean frame, the damaged frame, and how many items survived. */
function Condition({ c, baselineFrame }: { c: StressCondition; baselineFrame: string }) {
  const d = c.degraded;
  return (
    <li className="scard">
      <div className="scard-head">
        <h3>{c.name}</h3>
        <p className="sub">{c.blurb}</p>
      </div>
      <div className="shots">
        <Shot src={baselineFrame} caption="Clean clip" />
        <Shot src={d.frame} caption="Damaged clip" />
      </div>
      <div className="sbar">
        <div className="sbar-row"><span>Items still found</span><span className="num">{pct(d.recall)}</span></div>
        <div className="sbar-track" role="img" aria-label={`Items still found ${pct(d.recall)}`}><i className="good" style={{ transform: `scaleX(${Math.max(0.02, d.recall)})` }} /></div>
        <p className="sub num">{d.found.length} of {d.found.length + d.missed.length} found</p>
      </div>
      <div className="sgroups">
        {d.found.length > 0 && <div><p className="grp-h">Still found</p><ul className="tags">{d.found.map((l) => <li key={l} className="tag ok">{l}</li>)}</ul></div>}
        {d.missed.length > 0 && <div><p className="grp-h">Missed</p><ul className="tags">{d.missed.map((l) => <li key={l} className="tag miss">{l}</li>)}</ul></div>}
        {d.extra.length > 0 && <div><p className="grp-h">Not in the clean clip</p><ul className="tags">{d.extra.map((l) => <li key={l} className="tag extra">{l}</li>)}</ul></div>}
      </div>
      <p className="sub num">Model time: {d.latency_s}s</p>
      {d.error && <p className="note strong" role="alert">A model call failed: {d.error}</p>}
    </li>
  );
}

/** @returns the Stress screen. */
export default function StressPage() {
  const { run: lastRun } = useStore();
  const { run, error, starting, start, startWithFile } = useStress();
  const [link, setLink] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  // One level only: the harsh setting, since it is the one that shows where the models start to slip.
  const severity = "extreme";

  const lastSource = lastRun?.source.video_id ?? null;
  const processing = run?.state === "processing";
  const doneCount = run?.steps.filter((s) => s.state === "done" || s.state === "failed").length ?? 0;

  async function onFile(file: File) {
    setFileName(file.name);
    setUploading(true);
    await startWithFile(file, severity);
    setUploading(false);
  }

  return (
    <main id="main" className="screen stress">
      <header className="head">
        <h1 className="h1">Pushed until it breaks</h1>
        <p className="meta">We damage a clip on purpose and see what the models still find. Nothing is repaired: they see the clip exactly as it is.</p>
      </header>

      <div className="stress-grid">
        <aside className="stress-side">
          <section aria-labelledby="what-h">
            <h2 id="what-h" className="grp-h">What we test</h2>
            <ul className="what">
              {WHAT.map((w) => (
                <li key={w.id}><strong>{w.name}</strong><span>{w.blurb}</span></li>
              ))}
            </ul>
          </section>

          <section className="runbox" aria-label="Run a stress test">
            <DropZone onFile={onFile} busy={uploading || starting} fileName={fileName} accept="video/*" />
            <p className="or">or paste a link or file path</p>
            <label className="field">
              <span className="sr-only">Video link</span>
              <input type="text" autoComplete="off" placeholder="Paste a video link or file path" value={link} onChange={(e) => setLink(e.target.value)} onKeyDown={(e) => e.key === "Enter" && start(link, severity)} />
            </label>
            <div className="row">
              <button type="button" className="btn primary grow" disabled={starting || processing} onClick={() => start(link, severity)}>{starting ? "Starting…" : processing ? "Testing…" : "Run stress test"}</button>
              {lastSource && <button type="button" className="btn outline" disabled={starting || processing} onClick={() => start(lastSource, severity)}>Use my last video</button>}
            </div>
            <p className="note">Takes a few minutes. Every version is a real model call, so nothing here is staged.{!API_URL ? " Backend not connected." : ""}</p>
            {error && <p className="note strong" role="alert">{error}</p>}
          </section>
        </aside>

        <div className="stress-main">
          {!run && <div className="ev-card"><p className="body wide">Run a test and the results appear here: the clean frame next to the damaged one, and how many of the items the models still found.</p></div>}

          {run && processing && (
            <section className="steps" aria-label="Progress" aria-live="polite">
              <div className="progress"><i style={{ transform: `scaleX(${Math.max(0.03, doneCount / run.steps.length)})` }} /></div>
              <ul>
                {run.steps.map((s) => (
                  <li key={s.key} className={s.state}>
                    <span className="dot2" aria-hidden="true" />
                    <span>{s.label}</span>
                    <span className="state">{s.state === "running" ? "Testing…" : s.state === "done" ? "Done" : s.state === "failed" ? "Failed" : "Waiting"}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {run?.state === "failed" && <p className="note strong" role="alert">The stress test stopped: {run.error}</p>}

          {run?.state === "done" && run.summary && run.baseline && (
            <>
              <section className="summary" aria-label="Summary">
                <h2 className="grp-h">The short version</h2>
                <div className="stats">
                  <div><b className="num">{run.summary.baseline_items}</b><span>items in the clean clip</span></div>
                  <div><b className="num">{pct(run.summary.avg_degraded)}</b><span>still found on average when damaged</span></div>
                  <div><b className="num">{pct(run.summary.weakest.recall)}</b><span>on the hardest: {run.summary.weakest.name}</span></div>
                </div>
                <p className="body wide">
                  {run.summary.breaking_point
                    ? `It first broke on “${run.summary.breaking_point}”, where fewer than ${pct(run.summary.threshold)} of the items survived.`
                    : `It held up on every condition. The hardest was “${run.summary.weakest.name}”, where it still found ${pct(run.summary.weakest.recall)} of the items.`}
                </p>
              </section>

              <ul className="slist">
                {run.conditions.map((c) => <Condition key={c.id} c={c} baselineFrame={run.baseline!.frame} />)}
              </ul>

              <p className="note">Scores compare each damaged clip with what the model finds on the clean clip, not with human labels.</p>
            </>
          )}
        </div>
      </div>
    </main>
  );
}
