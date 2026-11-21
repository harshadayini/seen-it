# Seen It — Project Context & Build Roadmap (`PROJECT_ROADMAP.md`)

Welcome to the **Seen It** workspace. This base setup contains zero application code files by design—only the authoritative context, architecture, rules, and design prompt needed to execute cleanly.

---

## 1. Document Index

| File | Purpose |
| :--- | :--- |
| [`Design.md`](./Design.md) | Product vision, Element 119 + Shopify Bonus Track alignment, all supported modalities, core features (including multi-product frame swap), and user journeys. |
| [`TECHNICAL_SPEC.md`](./TECHNICAL_SPEC.md) | Full architecture: Gemini 4 tiered escalation (`hydrogen` → `neon` → `carbon`), `gemini-decision-1` calibrated rubric gate, `gemini-nano-banana-2.1` multi-product swap, Shopify UCP typed client spec, and modular layout. |
| [`AGENT_RULES.md`](./AGENT_RULES.md) | Mandatory rules on API key security, Shopify zero-caching/no-rehosting compliance, Gemini SDK usage, one-file-per-feature structure, docstrings, centralized config, and stripped INFO logging. |
| [`UI_DESIGN_PROMPT.md`](./UI_DESIGN_PROMPT.md) | Ready-to-use interactive UI/UX design prompt with Cosmos (`cosmos.so`) asset sourcing instructions and full interactive state specs. |
| [`.env.example`](./.env.example) | Placeholder environment variable template (NEVER commit real keys). |

---

## 2. Recommended Execution Order (When Ready to Build)

### Phase 0 — Environment & Credentials Setup
1. Ensure `@google/genai` is upgraded to `>= 3.3.0` (`npm i @google/genai@latest`) for Decisions API (`v1beta`) and `ThinkingLevel.XHIGH`.
2. Configure server-side secrets (never committed to repo):
   * `GEMINI_API_KEY` (paid key enabled for `gemini-4-neon`, `gemini-4-carbon`, `gemini-nano-banana-2.1`)
   * `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` (from Shopify Dev Dashboard → Agents)
   * `SHOPIFY_UCP_AGENT_PROFILE_URI` (starting with Shopify's hosted example profile, with local `/.well-known/ucp-agent-profile.json` fallback)

### Phase 1 — Core Foundations & Shopify UCP Client + Smoke Test
1. Create centralized config (`src/config/appConfig.ts`) and structured `INFO` logger (`src/server/logger.ts`) that strips inline base64 data and redacts secrets.
2. Build the typed Shopify UCP client split by responsibility (`auth.ts`, `rpcClient.ts`, `catalogClient.ts`, `merchantDiscovery.ts`, `cartClient.ts`) with token caching and exponential backoff retry.
3. Build and run `scripts/smoke-shopify-ucp.ts` to verify live `searchCatalog` → `lookupCatalog` → `getProduct` → `/.well-known/ucp` → `createCart` + `continue_url`.

### Phase 2 — Gemini 4 Tiered Escalation & Decisions API Engine
1. Build server-side Gemini clients (`genaiClient` + `v1beta` `decisionsClient`).
2. Implement **Tier 1 (`gemini-4-hydrogen`)** omnidirectional scout (video, audio/song, images, Pinterest board grids, text) + manifest extraction.
3. Implement **Calibrated Gate (`gemini-decision-1`)** with ephemeral RAM-only merchant image fetching and zero-output-token rubric scoring.
4. Implement **Tier 2 (`gemini-4-neon`)** forensic query repair and **Tier 3 (`gemini-4-carbon`)** deep cross-modal reconciliation + honest abstention logic.
5. Expose SSE streaming endpoints so the UI shows live escalation progress.

### Phase 3 — Multi-Product "Swap Into Your Frame" Engine
1. Implement `sceneSwapper.ts` using `gemini-nano-banana-2.1` accepting `1..N` active catalog variants simultaneously plus the user's target frame/keyframe.
2. Ensure ephemeral RAM-only handling of merchant variant images during compositing.

### Phase 4 — Interactive Frontend Studio
1. Build the modular React + Tailwind frontend following `UI_DESIGN_PROMPT.md` (Omnimodal Intake, Inspect ↔ Multi-Product Swap Stage with Before/After slider, Calibrated Catalog Feed, Side-by-Side Multi-Merchant UCP Carts, and Element 119 Stress Lab Drawer).

### Phase 5 — Unscripted Stress Testing & Breaking-Point Documentation
1. Run real, unscripted hard inputs (long shaky room tour, dim music+speech street clip, song + Pinterest board capsule).
2. Capture real Tier 1 → Tier 2 → Tier 3 recovery metrics and honest residual breaking points for the Element 119 demo.
