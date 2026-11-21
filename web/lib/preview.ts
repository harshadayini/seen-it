/**
 * Client for the "See it here" backend calls: upload a scene, start a preview, poll its status.
 * Boundary: talks only to our own backend (API_URL, via the /backend proxy in dev). No Gemini or
 * Shopify code and no secrets here. Errors are thrown as plain-language messages for the UI and
 * nothing is ever fabricated: a missing preview is an error, never a placeholder.
 */
import { API_URL } from "./config";

/** Largest upload the backend accepts (bytes). */
export const MAX_UPLOAD_BYTES = 60_000_000;
/** Seconds between status polls. */
export const POLL_SECONDS = 2;
/** Give up waiting after this many seconds (the backend normally takes about 15 to 20). */
export const GIVE_UP_SECONDS = 120;
/** Longest side of a camera still sent to the backend, in pixels. */
export const CAPTURE_MAX_PX = 1024;

export interface SceneUpload {
  scene_id: string;
  kind: "image" | "video";
  /** Relative paths under the backend's /previews, to show at API_URL/<path>. */
  frames: string[];
  /** Index of the frame to highlight first. */
  default: number;
}

export interface PreviewResult {
  image_path: string;
  /** 0..1, or null when the check could not run. */
  fidelity: number | null;
  regenerated?: boolean | null;
}

export interface PreviewStatus {
  status: "none" | "processing" | "done" | "failed";
  preview?: PreviewResult;
  error?: string;
}

export interface PlaceArgs {
  runId: string;
  itemId: string;
  /** An uploaded scene (from uploadScene) ... */
  sceneId?: string;
  frameIndex?: number;
  /** ... or a camera still as a data URL. */
  sceneImage?: string;
  /** Where the user tapped, 0..1 from the left and from the top. */
  anchor?: { x: number; y: number } | null;
}

/** Turns a failed response into a short plain message (FastAPI sends {detail}). */
async function readError(res: Response): Promise<string> {
  try {
    const j = await res.json();
    if (typeof j?.detail === "string") return j.detail;
  } catch {
    /* fall through */
  }
  return `The server answered ${res.status}.`;
}

/** Wraps fetch so a network failure becomes one clear message. */
async function call(url: string, init?: RequestInit): Promise<Response> {
  if (!API_URL) throw new Error("The backend isn't connected, so there is nothing to place the product in.");
  try {
    return await fetch(url, init);
  } catch {
    throw new Error("Couldn't reach the server. Check your connection and try again.");
  }
}

/**
 * Uploads the user's photo or video as the raw request body.
 * @param file an image/* or video/* file, at most MAX_UPLOAD_BYTES
 * @returns the stored scene with the frames to choose from
 */
export async function uploadScene(file: File): Promise<SceneUpload> {
  if (file.size > MAX_UPLOAD_BYTES) throw new Error(`That file is too big. The limit is ${MAX_UPLOAD_BYTES / 1_000_000} MB.`);
  const res = await call(`${API_URL}/scene`, { method: "POST", headers: { "content-type": file.type || "application/octet-stream" }, body: file });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}

/** Starts placing the item's matched product into the scene. Returns once the job has started. */
export async function startPreview(a: PlaceArgs): Promise<void> {
  const body: Record<string, unknown> = { run_id: a.runId, item_id: a.itemId };
  if (a.sceneId) {
    body.scene_id = a.sceneId;
    body.frame_index = a.frameIndex ?? 0;
  } else if (a.sceneImage) {
    body.scene_image = a.sceneImage;
  }
  if (a.anchor) {
    body.anchor_x = a.anchor.x;
    body.anchor_y = a.anchor.y;
  }
  const res = await call(`${API_URL}/preview`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(await readError(res));
}

/** Current status of the preview job for an item. */
export async function getPreview(runId: string, itemId: string): Promise<PreviewStatus> {
  const res = await call(`${API_URL}/preview/${encodeURIComponent(runId)}/${encodeURIComponent(itemId)}`, { cache: "no-store" });
  if (!res.ok) throw new Error(await readError(res));
  return res.json();
}
