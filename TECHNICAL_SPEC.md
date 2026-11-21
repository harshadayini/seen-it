# Seen It — Technical Architecture & Specification (`TECHNICAL_SPEC.md`)

This document specifies the complete technical architecture for **Seen It**, covering the Gemini 4 tiered escalation pipeline, Decisions API calibrated verification, multi-product scene-swap generation, Shopify Agentic Commerce (UCP) integration, compliance constraints, and breaking-point benchmarking.

---

## 1. High-Level System Architecture

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                         React + Vite Frontend                              │
│  • Omnimodal Intake (Video, Audio/Song, Images, Pinterest/Board URL, Text) │
│  • Interactive Timeline Scrubber, Item Pins & Audio Constraint Callouts    │
│  • Tiered Escalation & Calibrated Confidence Inspector (Stress Lab)        │
│  • Multi-Product "Swap Into Your Frame" Interactive Stage (1..N items)     │
│  • Side-by-Side Per-Merchant UCP Carts + continue_url Handoff              │
│  • Renders merchant product images DIRECTLY from merchant CDN URLs         │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ HTTP / SSE (JSON, Multipart, Stream)
┌────────────────────────────────────▼───────────────────────────────────────┐
│                      Express + TypeScript Backend                          │
│                                                                            │
│  [Centralized Config]   [Structured Logger (strips inline base64/secrets)] │
│                                                                            │
│  ┌───────────────────────────────┐   ┌──────────────────────────────────┐  │
│  │  Gemini 4 + Decisions Engine  │   │     Shopify UCP Typed Client     │  │
│  │  • Tier 1: gemini-4-hydrogen  │   │  • OAuth2 client_credentials     │  │
│  │  • Gate:   gemini-decision-1  │◄─►│    token cache + backoff retry   │  │
│  │  • Tier 2: gemini-4-neon      │   │  • Global Catalog MCP JSON-RPC   │  │
│  │  • Tier 3: gemini-4-carbon    │   │    (search/lookup/get_product)   │  │
│  │  • Swap:   nano-banana-2.1    │   │  • /.well-known/ucp discovery    │  │
│  └──────────────┬────────────────┘   │  • Merchant Cart MCP             │  │
│                 │                    │    (create_cart / update_cart)   │  │
│                 ▼                    └─────────────────┬────────────────┘  │
│   Ephemeral In-Memory Image Buffer                     │                   │
│   (RAM-only during Gemini checks &                     │                   │
│    scene swap; NEVER cached/saved)                     ▼                   │
└──────────────────────────────────────┬─────────────────────────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
  Google GenAI APIs        Shopify Global Catalog MCP        Merchant UCP MCPs
  (v1 + v1beta Decisions)  catalog.shopify.com/api/ucp/mcp   {shop}/api/ucp/mcp
```

---

## 2. Gemini 4, Decisions API & Media Generation Stack

### 2.1 SDK & Client Initialization Rules
* **SDK Version:** Upgrade `@google/genai` to `>= 3.3.0` (`npm i @google/genai@latest`) so `ai.decisions.create`, `ThinkingLevel.XHIGH`, and all Gemini 4 models are supported.
* **Server-Side Only:** `@google/genai` is imported and invoked exclusively in server-side Express modules using `process.env.GEMINI_API_KEY`.
* **Two Dedicated Clients:**
  1. `genaiClient`: Default client for Gemini 4 (`generateContent` / `generateContentStream`) and image generation, initialized with `httpOptions: { headers: { 'User-Agent': 'aistudio-build' } }`.
  2. `decisionsClient`: Dedicated client initialized with `apiVersion: "v1beta"` and `'User-Agent': 'aistudio-build'` strictly for `ai.decisions.create` (`gemini-decision-1` is `v1beta`-only; calling on `v1` returns `404`).
* **Parameter Discipline on Gemini 4:**
  * NEVER pass deprecated `temperature`, `topP`, `topK`, `candidateCount`, or `thinkingBudget` to `gemini-4-hydrogen`, `gemini-4-neon`, `gemini-4-carbon`, or `gemini-4-argon`.
  * Use `thinkingConfig: { thinkingLevel: ThinkingLevel.* }` where appropriate (`XHIGH` is supported only on `gemini-4-neon` and `gemini-4-hydrogen`; `HIGH`/`MEDIUM`/`LOW` on all four; never `MINIMAL`).

### 2.2 Tiered Escalation Pipeline

| Stage | Model ID | Job & Responsibility | Thinking Level |
| :--- | :--- | :--- | :--- |
| **Tier 1: Fast Scout** | `gemini-4-hydrogen` | Fast first-pass ingestion of video, audio/song, images, board grids, and text. Extracts timestamped Item & Vibe Manifest, bounding boxes, spoken constraints/exclusions, and multi-angle Shopify `search_catalog` queries + filters. | `LOW` / `MEDIUM` |
| **Calibrated Gate** | `gemini-decision-1` | Called via `decisionsClient.decisions.create(...)`. Evaluates all Shopify candidates for an item in a single batched multimodal request (zero output tokens). Computes calibrated `choice` (match tier), `score` (0–4 visual rubric), and `noul` (audio constraint compliance, lighting trap). | N/A (Decisions API) |
| **Tier 2: Forensic Escalation** | `gemini-4-neon` | Fires automatically when Tier 1 candidates fail Decisions API thresholds (`P(match) < threshold` or low confidence). Inspects high-res multi-frame crops + raw audio + exact rubric failure signals to diagnose misses, read subtle details/materials/white-balance, and emit repaired queries. | `HIGH` or `XHIGH` |
| **Tier 3: Deep Reconciliation** | `gemini-4-carbon` | Fires on Tier 2 failure or extreme ambiguity: conflicting audio/visual cues, heavy multi-object occlusion, abstract song/Pinterest vibe-to-catalog synthesis, or deciding honest abstention vs. cross-category dupe strategy. | `HIGH` |
| **Multi-Product Scene Swap** | `gemini-nano-banana-2.1` | Composites **1 to N** selected Shopify catalog variants simultaneously back into the user's source frame/keyframe, preserving scene lighting, perspective, scale, and occlusion while keeping untouched objects intact. | N/A (Image model) |
| **Optional Audio Isolation** | `gemini-3.5-transcribe` | Optional dedicated pass for heavily noisy/overlapping audio tracks when stress-testing speech extraction vs. raw multimodal audio understanding. | N/A |

### 2.3 Decisions API Rubric Design (`gemini-decision-1`)
For each target item `I` and top `K` Shopify candidate variants (e.g., `K = 6..12`):
* **Shared Multimodal Input (tokenized once):**
  1. 1–3 cropped keyframes of item `I` from the user's video/photo (overview + detail crop) at `medium`/`high` resolution.
  2. Structured JSON text summarizing audio constraints, negative exclusions, and vibe metadata.
  3. Candidate `0..K-1` variant images fetched directly into server RAM (`Buffer` → base64) alongside compact candidate metadata (title, price, option values, merchant domain).
* **Batched Questions (up to 1,000 per call, zero output tokens):**
  * `cand_{k}_tier` (`choice`):
    * `exact_match`: Same product/model/colorway and construction.
    * `close_dupe`: Highly similar silhouette, material, and aesthetic within constraints.
    * `vibe_match`: Shares mood/palette/category but clearly a different design.
    * `mismatch`: Wrong item, wrong category, or visually unrelated.
  * `cand_{k}_visual_score` (`score`, 5-level ordered rubric 0→4):
    * `0`: Unrelated item or category
    * `1`: Same broad category only
    * `2`: Similar silhouette, wrong colorway or material
    * `3`: Matches silhouette and colorway/material closely, minor hardware/detail differences
    * `4`: Indistinguishable or near-exact match across silhouette, material, colorway, and details
  * `cand_{k}_constraints_ok` (`noul`): Does candidate `k` satisfy all spoken/text constraints and negative exclusions (price cap, material exclusions, color requests)?
  * `cand_{k}_lighting_trap` (`noul`): Is any apparent color discrepancy likely caused by ambient video lighting/color-grading rather than an actual colorway mismatch?
* **Escalation Decision Rule (configurable in centralized config):**
  * Pass without escalation if at least one candidate achieves `constraints_ok.noul >= 0.75` AND (`tier === 'exact_match'` with `confidence >= 0.72` OR normalized `visual_score >= 0.78`).
  * Escalate to **Tier 2 (`gemini-4-neon`)** if no candidate clears threshold after Tier 1.
  * Escalate to **Tier 3 (`gemini-4-carbon`)** if Tier 2 still fails threshold or `lighting_trap.noul >= 0.65` with conflicting audio/visual cues.
  * If Tier 3 still yields no strong `exact_match`/`close_dupe`, **honestly abstain** from exact matching and surface the highest calibrated `vibe_match` / `close_dupe` items with explicit confidence badges.

### 2.4 Multi-Product "Swap Into Your Frame" Architecture
* Input to `gemini-nano-banana-2.1`:
  * User's source frame (high-res keyframe or uploaded photo).
  * An ordered list of `1..N` active swap directives:
    * Target region / item description & bounding box from the Manifest (e.g., *"Replace the dark blazer on the person at `[ymin, xmin, ymax, xmax]` with Reference Product 1; replace the tan tote bag at `[...]` with Reference Product 2"*).
    * Corresponding `1..N` Shopify variant images fetched fresh into server RAM at request time.
* Supports iterative re-swapping as the user toggles any subset of items in their active catalog or switches between matched variants/merchants.
* Ephemeral merchant image buffers are garbage-collected immediately after the generation request returns; only the user's generated composite preview is returned for the active session.

### 2.5 Mobile-Exclusive "Virtual Twin" (Real-World Camera Placement)
* **Mobile Camera Pipeline:** Captures a live high-resolution portrait frame from the mobile rear (`environment`) or front (`user`) camera via `getUserMedia` (requiring `camera` frame permission in `metadata.json` when implemented).
* **Spatial Placement & Multi-Product Real-World Generation:**
  * User taps `1..N` placement anchors `(x, y)` directly on the live camera preview (e.g., desk corner, floor next to sofa, or mirror body region) and selects `1..N` active products from their matched catalog dock.
  * Optional quick spatial-grounding check via `gemini-4-hydrogen` (low thinking) validates lighting direction, surface plane, and realistic physical scale hints from product dimensions/title.
  * **`gemini-nano-banana-2.1`** generates the photorealistic **Virtual Twin** composite—placing all selected Shopify catalog products simultaneously into the live camera scene with matching ambient lighting, cast shadows, reflections, and perspective.
  * Preserves strict Shopify compliance: merchant variant images are fetched into ephemeral server RAM only for the generation request and discarded immediately afterward.


---

## 3. Shopify Agentic Commerce (UCP) Integration

### 3.1 Hard Constraints & Compliance
1. **UCP Stack Only:** Use ONLY Global Catalog MCP (`https://catalog.shopify.com/api/ucp/mcp`) and Merchant Cart MCP (`https://{shop-domain}/api/ucp/mcp`). Do **NOT** use Shopify Admin GraphQL, Storefront GraphQL, or a custom demo store.
2. **No Deprecated REST:** Ignore any `/global/v2/` endpoints (shut down November 2).
3. **No Caching / No Re-Hosting:**
   * Do **NOT** cache Shopify catalog responses to disk or database.
   * Do **NOT** download, proxy-cache, or re-host merchant product images.
   * Server fetches merchant image bytes strictly into ephemeral RAM only for Gemini Decisions verification and Scene-Swap compositing, then immediately discards them.
   * Frontend renders `<img src={variant.imageUrl} />` directly from the merchant's original URL.
   * Persist ONLY lightweight identifiers & evaluation outputs: **UPIDs, variant IDs, merchant domains, and calibrated decision scores**.
4. **Demo Safety:** Never complete real orders during development or demos; stop at live Cart MCP (`create_cart` / `update_cart`) and `continue_url` handoff.

### 3.2 Authentication & Agent Profile
* **OAuth2 Client Credentials Flow (for higher rate limits):**
  * Endpoint: `POST https://api.shopify.com/auth/access_token`
  * Grant: `client_credentials` using `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` from server environment variables.
  * In-memory token caching with safety expiry buffer (refresh proactively before `expires_in` elapses); falls back to unauthenticated profile-only calls only if explicitly configured for local testing.
* **JSON-RPC Envelope & Agent Profile:**
  * Every Catalog MCP call uses JSON-RPC `method: "tools/call"` and includes `meta["ucp-agent"].profile`.
  * Default profile URI: Shopify's hosted example profile URI (configured in centralized config).
  * Fallback: Serve our own static agent profile JSON at `GET /.well-known/ucp-agent-profile.json` using `APP_URL` if Shopify's example profile is ever rejected.

### 3.3 Typed Shopify UCP Client Interface
Planned server module surface (`src/server/shopify/` split by concern):

```ts
// Discovery (Global Catalog MCP: https://catalog.shopify.com/api/ucp/mcp)
searchCatalog(query: string, filters?: CatalogSearchFilters): Promise<CatalogSearchResult>;
lookupCatalog(ids: string[]): Promise<CatalogProduct[]>; // auto-chunked in batches of <= 50
getProduct(upid: string): Promise<CatalogProductDetail>;

// Merchant Discovery & Cart MCP (https://{shop-domain}/.well-known/ucp -> /api/ucp/mcp)
discoverMerchantUcp(merchantDomain: string): Promise<MerchantUcpManifest>;
createCart(merchantDomain: string, variantId: string, qty: number): Promise<MerchantCart>;
updateCart(merchantDomain: string, cartId: string, lineItems: CartLineItemInput[]): Promise<MerchantCart>;
getContinueUrl(cart: MerchantCart): string | null;
```

* **`search_catalog` Defaults:** Uses free-text `catalog.query` plus filters (`max_price`, `ships_to`, `currency`, etc.). Image-input parameter is intentionally disabled by default due to reported upstream service errors.
* **Normalized Domain Model:** Results grouped by Universal Product ID (`upid`) with nested `variants[]`, retaining each variant's `variantId`, `price`, `currency`, `merchantDomain`, `title`, `options`, and `imageUrl`.
* **Merchant Cart Flow:**
  1. Fetch `https://{shop-domain}/.well-known/ucp` to discover the merchant's MCP endpoint (resolves to `https://{shop-domain}/api/ucp/mcp`) and verify Cart MCP capability.
  2. Call `create_cart` with `line_items: [{ quantity: qty, item: { id: variantId } }]`.
  3. Store returned `cartId` and `continue_url` in session state.
  4. Use `update_cart` for all subsequent additions/quantity changes/removals for that merchant (avoiding stricter Checkout MCP rate limits).
  5. Optional / Verify-First: `create_checkout(cart_id)` only if merchant manifest advertises it and live verification confirms availability; Shop MCP (`https://mcp.shop.com`) noted as a future Shop Pay signed-in shopper enhancement.
* **Reliability:** Exponential backoff with jitter on HTTP `429` and transient `5xx` errors, respecting `Retry-After` headers when present.

### 3.4 Smoke-Test Script Spec
A standalone runnable script (e.g., `scripts/smoke-shopify-ucp.ts`) that verifies live end-to-end UCP behavior before UI integration:
1. Acquires bearer token via `client_credentials` (verifying token cache hit on second call).
2. Runs one `searchCatalog(...)` call and parses returned UPIDs + variant IDs + merchant domains.
3. Runs one `lookupCatalog([...])` and `getProduct(upid)` call.
4. Discovers `/.well-known/ucp` for a returned merchant domain and runs one `createCart(merchantDomain, variantId, 1)` call, logging `cartId` and `continue_url` (redacting tokens and secrets).

---

## 4. Multimodal Input Ingestion Details

* **Video & Audio Uploads:** Accepted via multipart upload (stored only in ephemeral request/temp processing scope, never permanently hosted). Keyframe extraction + timestamp indexing paired with native video/audio ingestion into Gemini 4.
* **TikTok / Short-Form Clips:** Primary path is direct video file upload (MP4/MOV/WebM) for zero-flake demo reliability; optional URL ingestion helper where publicly accessible media is resolvable.
* **Pinterest Boards & Moodboards:** Accepts exported board images, multi-image drops, or public board URLs (fetched server-side to extract visible board collage/pins into a multi-image vibe analysis pass; no scraping circumvention or credentialed storage).
* **Songs / Vibe Audio:** Accepts audio clips (MP3/WAV/M4A/WebM) passed natively as multimodal audio to Gemini 4 to infer era, genre texture, color temperature, and subculture styling cues—paired with optional track/artist text cues.

---

## 5. Planned Modular Directory Layout (When Build Begins)

Following the one-file-per-feature architecture and centralized configuration guidelines:

```text
/
├── Design.md
├── TECHNICAL_SPEC.md
├── AGENT_RULES.md
├── UI_DESIGN_PROMPT.md
├── PROJECT_ROADMAP.md
├── .env.example
├── scripts/
│   └── smoke-shopify-ucp.ts        # Live UCP search + lookup + cart smoke test
└── src/
    ├── config/
    │   └── appConfig.ts            # ALL model names, thinking levels, thresholds, UCP URLs, retry limits
    ├── server/
    │   ├── logger.ts               # Structured INFO logger (strips inline base64 data & redacts secrets)
    │   ├── genai/
    │   │   ├── client.ts           # Shared genaiClient + v1beta decisionsClient
    │   │   ├── scoutHydrogen.ts    # Tier 1: gemini-4-hydrogen manifest & query fan-out
    │   │   ├── decisionVerifier.ts # Calibrated Gate: gemini-decision-1 rubric batching
    │   │   ├── escalateNeon.ts     # Tier 2: gemini-4-neon forensic query repair
    │   │   ├── escalateCarbon.ts   # Tier 3: gemini-4-carbon deep cross-modal reconciliation
    │   │   ├── sceneSwapper.ts     # Multi-product Swap Into Frame (gemini-nano-banana-2.1)
    │   │   └── vibeExtractor.ts    # Song / Pinterest board / moodboard vibe synthesis
    │   ├── shopify/
    │   │   ├── auth.ts             # OAuth2 client_credentials token manager + cache
    │   │   ├── rpcClient.ts        # JSON-RPC tools/call wrapper + exponential backoff retry
    │   │   ├── catalogClient.ts    # searchCatalog, lookupCatalog, getProduct
    │   │   ├── merchantDiscovery.ts# /.well-known/ucp resolution
    │   │   └── cartClient.ts       # createCart, updateCart, getContinueUrl
    │   ├── pipeline/
    │   │   ├── orchestration.ts    # End-to-end tiered escalation loop + SSE progress emitter
    │   │   └── stressMetrics.ts    # Element 119 breaking-point telemetry & failure categorization
    │   └── routes/                 # One Express router file per API domain
    └── client/                     # Modular React UI components per feature
```

---

## 6. Breaking-Point Evaluation Protocol (Element 119)

To satisfy Element 119's anti-toy-demo requirement:
* **No Team-Scripted Happy-Path Evals:** Test on unscripted, real-world clips (crowded thrift/street footage, fast-pan room tours, dim neon lighting, overlapping music + speech, real Pinterest boards + tracks).
* **Tracked Breaking-Point Metrics:**
  * Tier 1 acceptance rate vs. Tier 2 (`neon`) recovery rate vs. Tier 3 (`carbon`) recovery rate.
  * Calibrated abstention accuracy (how often `gemini-decision-1` properly rejects false positives when an item does not exist in Shopify's catalog).
  * Stage latency (ms), Decisions API batch size (questions/call, always `0` output tokens), and multi-product swap fidelity across `1, 2, 3+` simultaneous items.
  * Documented residual breaking points (e.g., `< 0.3s` whip-pan blur, `< 12px` obscured hardware, merchants without active Cart MCP endpoints).
