# Agent & Engineering Rules (`AGENT_RULES.md`)

All AI coding agents and human contributors working on **Seen It** MUST strictly enforce every rule in this file. No rule here may be bypassed for speed or demo convenience.

---

## 1. Secrets, Credentials & API Key Security (NON-NEGOTIABLE)

1. **NEVER upload, commit, hardcode, or expose API keys or secrets anywhere.**
   * Prohibited secrets include: `GEMINI_API_KEY`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, OAuth bearer tokens, session cookies, or private credentials.
2. **No secrets in code, docs, prompts, git, or client bundles:**
   * All secrets live strictly in server-side runtime environment variables (`process.env.*`).
   * `.env` and `.env.local` MUST stay gitignored and never be committed or pasted into documentation or logs.
   * `.env.example` may contain ONLY placeholder values (e.g., `"MY_SHOPIFY_CLIENT_SECRET"`).
3. **Zero browser/client exposure:**
   * Never import `@google/genai` or Shopify auth logic in frontend code.
   * Never expose `GEMINI_API_KEY` or Shopify bearer tokens in `vite.config.ts` `define` blocks, HTTP responses, SSE payloads, or browser console output.
   * Never build UI input fields, modals, or forms asking users to paste API keys.
4. **Mandatory log redaction:**
   * Redact `Authorization` headers, bearer tokens, `client_secret`, and `apiKey` in all logs, stack traces, and error payloads before printing or returning errors.

---

## 2. Shopify Agentic Commerce (UCP) Compliance Rules

1. **UCP Stack Only:**
   * Use ONLY Shopify Global Catalog MCP (`https://catalog.shopify.com/api/ucp/mcp`) and per-merchant Cart MCP (`https://{shop-domain}/api/ucp/mcp`, discovered via `/.well-known/ucp`).
   * **NEVER** use Shopify Admin GraphQL, Storefront GraphQL, or a custom Shopify store.
   * **NEVER** call deprecated `/global/v2/` REST endpoints (decommissioned November 2).
2. **Zero Caching & Zero Image Re-Hosting:**
   * **NEVER** cache Shopify catalog search/lookup/product responses to disk, database, or persistent storage.
   * **NEVER** save, persist, or re-host merchant product images.
   * Server-side code may fetch merchant image bytes into ephemeral RAM (`Buffer`) **only** for the duration of a Gemini Decisions API verification or multi-product Scene-Swap call, then immediately release the reference.
   * Frontend MUST render merchant images directly from the merchant's original image URL.
   * Only **UPIDs, variant IDs, merchant domains, and calibrated decision scores** may be persisted in session/eval records.
3. **No Real Orders:**
   * Never complete or simulate a real purchase order during tests or demos. Stop at `create_cart` / `update_cart` and `continue_url` handoff.
4. **Rate-Limit Etiquette:**
   * Cache Shopify OAuth2 bearer tokens in memory until near expiry.
   * Use exponential backoff with jitter on `429` / transient `5xx` responses.
   * Prefer `update_cart` over Checkout MCP (`create_checkout`) due to stricter Checkout MCP rate limits.

---

## 3. Gemini 4 & Decisions API Engineering Rules

1. **Approved Models Only (Centralized Config):**
   * Use ONLY valid active models configured in the centralized config file:
     * Tier 1 Scout: `gemini-4-hydrogen`
     * Calibrated Verifier: `gemini-decision-1` (via `ai.decisions.create` ONLY)
     * Tier 2 Escalation: `gemini-4-neon`
     * Tier 3 Escalation: `gemini-4-carbon`
     * Multi-Product Scene Swap: `gemini-nano-banana-2.1`
   * **NEVER** use deprecated models (`gemini-1.5-*`, `gemini-2.0-*`, `gemini-pro`).
2. **Strict API Usage:**
   * `gemini-decision-1` MUST use a dedicated `GoogleGenAI` client with `apiVersion: "v1beta"` and bare model ID `"gemini-decision-1"`, called exclusively via `ai.decisions.create(...)`.
   * NEVER pass `temperature`, `topP`, `topK`, `candidateCount`, or `thinkingBudget` to Gemini 4 models (`gemini-4-hydrogen`, `gemini-4-neon`, `gemini-4-carbon`, `gemini-4-argon`).
   * Always set `'User-Agent': 'aistudio-build'` in `httpOptions.headers` on server-side `GoogleGenAI` clients.
3. **No Fake / Mock / Heuristic Fallbacks:**
   * If a Gemini API, Decisions API, or Shopify UCP call fails (or credentials are missing), propagate a clean, structured error to the caller/UI.
   * **NEVER** fabricate fake product results, simulated decision probabilities, or hardcoded demo matches to hide upstream errors.

---

## 4. Code Architecture, Documentation & Logging Standards

1. **One File Per Feature / Responsibility:**
   * Split functionality cleanly across dedicated modules (e.g., separate files for Shopify auth, RPC transport, catalog tools, cart tools, each Gemini tier, scene swapping, logging, and each UI feature). Avoid monolithic files.
2. **Mandatory File Header Comments:**
   * Start EVERY code file with a detailed block comment explaining:
     * What the feature/module does.
     * Its distinct use cases and boundaries.
     * Any compliance or failure-handling invariants it upholds.
3. **Docstrings on Every Function:**
   * Every exported and internal function MUST have a clear JSDoc/docstring explaining its purpose, parameters, return value, and side effects.
4. **Centralized Configuration:**
   * Group ALL configurable values (model IDs, thinking levels, Decisions API thresholds, Shopify UCP URLs, profile URI, batch sizes, retry/backoff ceilings, swap limits) in a single centralized config file (`src/config/appConfig.ts`). No magic strings or scattered constants.
5. **Structured `INFO` Logging (Inline Data Stripped):**
   * Log at `INFO` level:
     * Every significant function call along with its sanitized parameters.
     * Every GenAI / Decisions API call with full metadata: model used, prompt/instructions, config, and outputs.
   * **ALWAYS strip inline binary/base64 media payloads** (replace with `{ mimeType, byteLength, stripped: true }`) before logging so logs remain readable and leak-free.
   * **ALWAYS redact secrets, tokens, and API keys.**
6. **Keep `Design.md` Live:**
   * Update `/Design.md` whenever any product feature, input modality, or user flow is added or modified.

---

## 5. Hackathon Integrity Rules (Element 119)

1. **No Text-Only Chatbot Framing:** Visual, video, audio, and generated-media workflows must remain the core interface—never reduce the app to a chat box.
2. **No Scripted-Only Demos or Self-Written Toy Evals:** Benchmarks and stress tests must run on real, messy, unscripted media and report real breaking points honestly.
3. **Preserve Clean UI:** Keep internal server logs/raw debug dumps out of the consumer shopping canvas; surface user-meaningful confidence, escalation traces, and breaking-point diagnostics cleanly in the dedicated Stress Lab / Inspector view.
