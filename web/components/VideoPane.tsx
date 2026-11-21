/**
 * VideoPane: the left side of Results. Embeds the YouTube player when the source is a YouTube
 * link (jumping to the chosen item's moment). If the video's owner blocks embedding (YouTube
 * reports error 101/150), or the source is not YouTube, it shows the chosen item's crop instead.
 * Boundary: presentational. The embed is YouTube's own player (nothing is downloaded or
 * re-hosted by the UI); a crop is shown only for an item that has finished checking.
 */
"use client";
import { useEffect, useRef, useState } from "react";
import { fileUrl } from "@/lib/config";
import { fmtTime, youtubeId } from "@/lib/format";
import type { Item } from "@/lib/types";

const YT_ORIGIN = "https://www.youtube-nocookie.com";

interface Props {
  /** run.source.video_id: the link or path the user gave. */
  source?: string | null;
  /** The item the user picked, if any; the player jumps to its moment. */
  item?: Item | null;
  /** Item whose crop is shown when nothing is picked and the video cannot play here. */
  fallback?: Item | null;
}

/** @returns the video (or crop fallback) with a one-line caption. Side effect: listens for YouTube error messages. */
export function VideoPane({ source, item, fallback }: Props) {
  const yt = youtubeId(source);
  const frame = useRef<HTMLIFrameElement>(null);
  const [blocked, setBlocked] = useState(false);
  const start = item?.t_start != null ? Math.max(0, Math.floor(item.t_start)) : 0;

  // A new video gets a fresh chance to play.
  useEffect(() => setBlocked(false), [yt?.id]);

  // YouTube tells the page (via postMessage) when the owner disallows embedding: 101 or 150.
  useEffect(() => {
    if (!yt) return;
    function onMessage(e: MessageEvent) {
      if (e.origin !== YT_ORIGIN || e.source !== frame.current?.contentWindow || typeof e.data !== "string") return;
      try {
        const d = JSON.parse(e.data);
        if (d.event === "onError" || (d.event === "infoDelivery" && d.info?.errorCode)) {
          const code = Number(d.info?.errorCode ?? d.info);
          if (code === 101 || code === 150 || code === 100) setBlocked(true);
        }
      } catch {}
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [yt]);

  const shown = item ?? fallback ?? null;
  const cropOk = shown?.state === "done" && !!shown.crop_path;
  const link = source && source.startsWith("https://") ? source : null;
  const showPlayer = !!yt && !blocked;

  return (
    <section className="video-pane" aria-label="Your video">
      <div className={`video-box ${yt?.vertical ? "vertical" : ""} ${showPlayer ? "" : "still"}`}>
        {showPlayer ? (
          <iframe
            ref={frame}
            key={`${yt!.id}-${start}`}
            src={`${YT_ORIGIN}/embed/${yt!.id}?start=${start}&rel=0&playsinline=1&enablejsapi=1`}
            title="Your video"
            allow="encrypted-media; picture-in-picture"
            allowFullScreen
            referrerPolicy="strict-origin-when-cross-origin"
            onLoad={() => frame.current?.contentWindow?.postMessage(JSON.stringify({ event: "listening", id: 1, channel: "widget" }), YT_ORIGIN)}
          />
        ) : cropOk ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={fileUrl(shown!.crop_path!)} alt={shown!.description ?? "Selected item"} />
        ) : (
          <p className="video-empty">Items appear here as we find them.</p>
        )}
      </div>
      {!showPlayer && yt && <p className="video-cap">The video&apos;s owner doesn&apos;t allow playing it here.{link && <> <a className="link tight" href={link} target="_blank" rel="noopener noreferrer">Watch on YouTube ↗</a></>}</p>}
      {shown && shown.t_start != null && (
        <p className="video-cap">{shown.description ?? "Item"} · seen at <span className="num">{fmtTime(shown.t_start)}</span></p>
      )}
    </section>
  );
}
