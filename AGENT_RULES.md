# Agent and engineering rules

Mandatory for every AI coding agent and human contributor. `CLAUDE.md` is the source of truth for stack, scope, models, ownership and the data contract. This file covers compliance, secrets and code standards. If the two disagree, `CLAUDE.md` wins; fix this file in the same PR.

Stack: Python 3.11+ / FastAPI backend, Next.js in `web/`.

## 1. Secrets
1. Never commit, hardcode, log or paste into docs, prompts or git: `GEMINI_API_KEY`, `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`, bearer tokens, cookies.
2. Secrets live only in server-side environment variables. `.env` stays gitignored. `.env.example` holds placeholders only.
3. Never expose secrets to the browser: no Gemini or Shopify auth code in `web/`, no keys in HTTP responses, and no UI field that asks users for a key. The browser talks only to our FastAPI endpoints.
4. Redact `Authorization` headers, tokens, `client_secret` and API keys in logs, stack traces and error responses.

## 2. Shopify compliance
1. Use only the agentic-commerce stack described in `CLAUDE.md` section 8 (Global Catalog MCP, per-merchant cart endpoints found via `/.well-known/ucp`). No Admin or Storefront GraphQL, no custom store, and never the `/global/v2/` REST endpoints (stopped serving November 2).
2. Do not cache catalog responses on disk or in a database. Do not save or re-host merchant images: the web app renders them from the merchant's own image URL, and the backend holds image bytes in memory only for the length of a Gemini or Decisions check. Persist only UPIDs, variant IDs, merchant domains and scores.
3. Never place a real order. Stop at `create_cart` / `update_cart` and the `continue_url`.
4. Cache the OAuth bearer token in memory until near expiry. Retry 429 and transient 5xx with exponential backoff and jitter. Prefer `update_cart` over Checkout MCP (stricter limits).

## 3. Gemini and Decisions API
1. Take model IDs from one config module (`backend/config.py`), never from scattered strings. Confirm IDs in AI Studio; the ones in `CLAUDE.md` section 3 are the plan. Carbon is limited to approved cyber testers, so do not use it. Never use deprecated models (`gemini-1.5-*`, `gemini-2.0-*`, `gemini-pro`).
2. Decisions API (`gemini-decision-1`): use a dedicated client on API version `v1beta` and call it only through the Decisions endpoint. It is not a Gemini 4 model.
3. Do not send `temperature`, `topP`, `topK`, `candidateCount` or `thinkingBudget` to Gemini 4 models.
4. Cap parallel Gemini calls (about 5) and retry with backoff.
5. When an upstream call fails or credentials are missing, return a clear structured error and mark the item `state: "failed"`. Never fabricate products, probabilities or matches to hide a failure. Saved runs and `fixtures/sample_run.json` are allowed only when clearly labeled as fixtures or recorded fallbacks (see `CLAUDE.md` section 13).

## 4. Code standards
1. One module per responsibility. Respect the ownership table in `CLAUDE.md` section 6: only edit your own directory; `backend/api.py` stays thin.
2. Start each file with a short comment saying what it does and what it must not do. Give each function a docstring covering purpose, arguments, return value and side effects.
3. Put configurable values (model IDs, thresholds, URLs, retry limits, batch sizes) in `backend/config.py`.
4. Log at INFO level the significant calls and every Gemini or Decisions call (model, config, outputs). Replace inline base64 or binary media with `{mime_type, byte_length, stripped: true}`. Redact secrets.
5. Changes to `contracts/run.schema.json` need all three people's approval, and `fixtures/sample_run.json` must still validate.

## 5. Hackathon integrity
1. Keep it an agent that finds, verifies, recovers and checks out, with a video-first UI. No chat box as the main interface and no dashboard as the main feature.
2. Evaluate on real, unscripted media with held-out videos. Report real failures honestly.
3. Demo only what we built today. No code, data or assets we lack rights to: commit URLs and labels, not other people's videos or merchant images.
