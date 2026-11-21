> **REFERENCE ONLY, NOT AUTHORITATIVE.** Written for an earlier TypeScript/Express plan. `CLAUDE.md` wins on stack (Python/FastAPI backend, Next.js in `web/`), scope, models, file ownership and the data contract. Use this file for ideas only; do not build to it. Rules live in `AGENT_RULES.md`.

# Seen It — Product Design & Features (`Design.md`)

> **One-liner:** Drop a messy video, voice memo, song, Pinterest board, photo, or text prompt—**Seen It** extracts every real-world item and vibe cue, verifies live Shopify catalog matches with calibrated probability scoring, swaps **multiple** matched products straight back into your frame, and builds ready-to-checkout multi-merchant carts via Shopify's Agentic Commerce stack (UCP).

---

## 1. Hackathon Alignment

### Problem Statement Two: Element 119
**Seen It** is designed around a core truth: **text-only descriptions lose the exact visual, temporal, and acoustic cues needed to identify real-world products.**

* **Raw media as core input:** Shaky handheld videos, fast room pans, dimly-lit street clips, overlapping speech over background music, songs that capture an aesthetic mood, photos, and visual moodboards (e.g., Pinterest boards).
* **Generated media as core output:** Multi-product **"Swap Into Your Frame"** visual compositing—placing any combination of currently matched catalog items back into the user's scene for before/after visual verification before checkout.
* **Multi-model Gemini 4 + Decisions API pipeline:** Uses **three Gemini 4 models (`gemini-4-hydrogen`, `gemini-4-neon`, `gemini-4-carbon`)** in a tiered escalation loop plus **`gemini-decision-1` (Decisions API)** for calibrated zero-output-token verification, plus **`gemini-nano-banana-2.1`** for multi-product scene-swap generation.
* **Built to show where it breaks:** Includes a dedicated **Stress Lab & Escalation Trace** that runs on unscripted, real-world footage and exposes exact failure modes, calibrated abstentions, and how tiered escalation recovers cases where naive single-pass visual search fails.

### Bonus Track: Build with Commerce (Shopify)
* Powered exclusively by **Shopify's Agentic Commerce stack** (`shop.dev`, Global Catalog MCP, and Merchant Cart MCP via UCP)—no Admin/Storefront GraphQL APIs and no custom demo store.
* Real cross-merchant product discovery across Shopify's global catalog with live side-by-side merchant carts and real `continue_url` checkout handoffs.

---

## 2. Supported Input Modalities

Users can mix and match any combination of inputs in a single session:

| Modality | Examples | What Seen It Extracts That Text Alone Loses |
| :--- | :--- | :--- |
| **Video (Short & Long)** | TikTok/Reels clips, thrift hauls, GRWM, street-style footage, cluttered 2–10 min apartment/desk tours | Multi-angle temporal stitching (front silhouette at `0:04`, hardware/stitching at `0:11`, fabric drape in motion at `0:18`), deduplication across cuts, white-balance & lighting compensation |
| **Audio & Voice** | Narration inside video, background chatter, standalone voice memos | Spoken constraints (*"under $120"*, *"real pebbled leather, not vegan"*), explicit negative exclusions (*"ignore the hoodie, I want the lamp behind it"*), fit/weight/acoustic cues |
| **Music / Vibe Tracks** | Uploaded song clip, audio snippet, or track reference | Translates sonic mood, era, texture, and subculture energy into concrete visual/material search vectors and aesthetic curation |
| **Images & Bursts** | Camera roll photos, screenshots, multi-angle shots of one outfit or room | Fine material texture, stitching, silhouette geometry, spatial placement for scene swapping |
| **Visual Boards & Links** | Pinterest board URLs / exported board grids, Cosmos moodboards, editorial references | Cross-image recurring aesthetic DNA (palette, silhouette motifs, recurring textures) distilled into shoppable capsules |
| **Text & Constraints** | Freeform prompts, budget ceilings, shipping region, currency, vibe tweaks | Hard filters (`max_price`, `ships_to`, `currency`), style pivots (*"same silhouette, warmer tone"*), multi-item bundle goals |

---

## 3. Core Product Features

### Feature 1: Omnimodal Intake Studio
* Single unified drop-zone and composer accepting **video files, audio/songs, photos, Pinterest/moodboard links, and text constraints** simultaneously.
* Supports compound queries—for example: a 90-second room tour video + a voice note (*"swap the chair and lamp, keep it under $300 total"*) + a song or Pinterest board defining the target aesthetic.

### Feature 2: Temporal Item & Vibe Manifest
* Scans raw video/images/audio to build an interactive **Manifest** of every distinct shoppable object and aesthetic cue:
  * **Timestamped Keyframes & Bounding Boxes:** Links each item to its clearest overview frame, detail close-up frame, and scale reference frame.
  * **Audio-Synced Constraints:** Attaches spoken requirements, exclusions, and budget limits directly to the specific item referenced at that timestamp.
  * **Vibe DNA Extraction:** For songs, moodboards, and Pinterest boards, generates a structured material/silhouette/color palette profile that drives catalog discovery when no single object is literally photographed.

### Feature 3: Tiered Escalation Discovery Engine
Because Shopify Global Catalog `search_catalog` operates on text queries + structured filters (image input is unreliable), **Seen It** bridges the visual-to-text-to-visual gap with a 3-tier escalation loop:
* **Tier 1 — Fast Scout (`gemini-4-hydrogen`):** Rapidly segments items/vibes, fans out multi-angle Shopify text queries (exact query, material/construction query, dupe query), and fetches initial candidates.
* **Calibrated Gate (`gemini-decision-1` via Decisions API):** Evaluates all Shopify candidate variant images (held transiently in server memory) against the user's cropped video frames and spoken constraints in one batched, zero-output-token call. Outputs calibrated probabilities for:
  * Match tier (`exact_match`, `close_dupe`, `vibe_match`, `mismatch`)
  * Visual fidelity rubric score (silhouette, lighting-adjusted color, material, hardware)
  * Spoken constraint compliance & lighting-trap detection
* **Tier 2 — Forensic Repair (`gemini-4-neon`):** Automatically triggers if calibrated confidence falls below threshold or all candidates score as mismatches. Reads micro-details across multiple frames, diagnoses *why* Tier 1 candidates failed the Decisions rubric, repairs the Shopify queries/filters, and re-verifies.
* **Tier 3 — Deep Cross-Modal Reconciliation (`gemini-4-carbon`):** Escalates only for the hardest breaking-point inputs—conflicting audio/visual instructions, severe occlusion/motion blur, lighting illusions, or abstract song/Pinterest-board-to-product synthesis.
* **Honest Abstention:** If an item is vintage, one-of-a-kind, or absent from Shopify's UCP index, the system explicitly abstains from claiming an exact match and presents calibrated `close_dupe` or `vibe_match` alternatives instead of hallucinating.

### Feature 4: Multi-Product "Swap Into Your Frame" Visual Stage
* Works with **any number of currently matched products in the active catalog**—not limited to swapping a single item at a time.
* Users can check/toggle **multiple items at once** (e.g., jacket + crossbody bag + sunglasses from an outfit video, or floor lamp + rug + accent chair from a room video) and swap different Shopify variants into the same source frame simultaneously.
* Powered by **`gemini-nano-banana-2.1`** using the user's selected video keyframe/photo plus the selected Shopify variant images held transiently in memory.
* Includes an interactive **Before / After comparison slider**, per-item swap toggles, and instant re-composition when switching variants (colorway, alternative merchant, or budget dupe).

### Feature 5: Mobile-Exclusive "Virtual Twin" (Real-World Product Placement)
* Built specifically for **mobile devices** using the phone's live rear and front cameras.
* Lets users point their camera at their actual room, desk, table, or mirror, tap surfaces/anchors, and **generate 1 or multiple currently matched Shopify products directly into their real-world environment** with realistic scale, shadows, occlusion, and ambient lighting.
* Supports flipping between **Space Mode** (rear camera for lamps, chairs, mugs, decor) and **Mirror / Try-On Mode** (front camera for jackets, bags, eyewear, accessories), with instant press-and-hold **Before / After** real-world comparison and one-tap **Add placed items to bag**.

### Feature 6: Multi-Merchant Shopify UCP Carts & Checkout Handoff
* Since Shopify's cross-merchant Universal Cart is gated, **Seen It** groups selected variants **per merchant domain** and renders live merchant carts cleanly per store.
* Discovers each merchant's live UCP endpoint via `https://{shop-domain}/.well-known/ucp`, creates carts with `create_cart`, iterates quantities/variants with `update_cart`, and exposes each merchant's real `continue_url` to hand off directly to merchant checkout.
* Gracefully handles merchants that do not yet expose Cart MCP by clearly labeling checkout handoff support.
* Never completes real orders during demos.

### Feature 7: Element 119 Stress Lab & Pipeline Trace
* A toggleable bottom-sheet inspector built for testing and judging (kept hidden during normal shopping):
  * Displays the exact escalation path per item (`Tier 1 Hydrogen` → `Decisions API Gate` → `Tier 2 Neon` → `Tier 3 Carbon`).
  * Shows raw calibrated probabilities, rubric breakdown, rejected false positives, and why an escalation fired.
  * Tracks real-world breaking-point telemetry (frame occlusion, motion blur, audio noise, catalog gaps, latency per stage) on unscripted user footage.

---

## 4. Core User Journeys

1. **The Messy Video Haul / Street-Style Clip:** User drops a 2-minute dimly-lit TikTok/handheld video with loud music and narration (*"not the black boots, find me that olive jacket under $180 and a bag like hers"*). Seen It stitches multiple frames, filters out the boots, escalates the dim-lit jacket through Tier 2/3 to beat the lighting trap, verifies Shopify hits with `gemini-decision-1`, lets the user swap both the matched jacket and bag back into the video frame—or try them on via **Virtual Twin**—and builds per-merchant UCP carts.
2. **The Vibe-First Capsule (Song + Pinterest Board) → Virtual Twin:** User drops a dreamy indie track + a Pinterest board link. Seen It synthesizes the sonic and visual DNA into verified Shopify pieces, and the user opens **Virtual Twin** on their phone camera to place the matched lamp, ceramic vase, and rug together in their real apartment before checking out.
3. **The Cluttered Room Tour Stress Test:** User uploads an unscripted fast-panning room tour with 10+ overlapping items. Seen It tracks recurring objects across timestamps, escalates occluded items, honestly abstains on custom/unlisted items with dupe fallbacks, and lets the user re-style multiple objects in either the original frame or live via **Virtual Twin**.

---

## 5. Mobile Interface & Visual Principles (Anti-Clutter + Cosmos Charm)

* **Mobile-First Ergonomics:** Full-bleed `9:16` vertical media and camera viewports, single floating bottom nav (`Drop` · `Studio` · `Twin` · `Bags`), and thumb-friendly swipe-up sheets.
* **Minimal Copy, Maximum Visuals:** Avoid enterprise jargon, multi-line subtitles, redundant sidebars/steppers, and telemetry sprawl. Labels stay short and human (1–3 words).
* **Warm Editorial Canvas + Cute Cosmos Icons:** Pair a warm gallery-paper palette and editorial serif headers (*Lora*) with playful, tiny **Cosmos (`cosmos.so`)** cutout icons/charms (camera, vinyl record, sunglasses, ceramic mug, tote bag, Polaroid pin) placed gently around empty states, modality tabs, and drop zones.
* **Progressive Technical Disclosure:** Escalation paths (`Hydrogen → Decisions → Neon → Carbon`) and Element 119 breaking-point diagnostics stay neatly tucked inside a quiet `Trace` toggle and the optional `Lab` sheet.


