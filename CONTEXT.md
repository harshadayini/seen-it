# Seen It: shared project context

Gemini 4 NYC Hackathon (Cerebral Valley x Google DeepMind), Sat Nov 21.
Track: **Element 119** + **Shopify bonus**. Recording starts at **3:30 pm**.

Everyone reads this file first. If you change a contract, a function signature, or the scope, edit this file in the same PR.

---

## 1. What we're building

Drop in a video or photo. The app finds what's **in** it (or what's **missing** from it), matches each item to real Shopify products with honest confidence scores, previews the products in your own scene, and builds the cart.

Pitch line: **"Every video becomes shoppable, with confidence you can trust."**

Why it fits Element 119: a text description throws away the exact color, finish and shape that identify a product. The input is messy by nature (motion blur, quick cuts, half-hidden items). We push it until it breaks, show where, and show how it recovers.

### Rules from the participant guide (do not violate)
- Use **at least two Gemini 4 models** (Argon, Carbon, Neon, Hydrogen), each with a clear job. Carbon is limited to approved cyber testers, so use Argon plus Hydrogen or Neon.
- Must go beyond text: video/images are the core input, and generated media is part of the output.
- Use the **Decisions API** (`gemini-decision-1`).
- **Not allowed:** text-only chatbots, demos that only run on scripted inputs, evaluations made entirely of examples we wrote to pass.
- Must show: a baseline, unseen inputs, where it breaks, what we changed after seeing the failures.
- Shopify bonus: use **shop.dev**, from discovery to cart.

---

## 2. Scope (frozen at 11:15)

| Tier | Feature | Cut rule |
|---|---|---|
| **MUST** | Video to items to catalog match to Decisions check to cart handoff | Never cut |
| **MUST** | Evaluation vs baseline on held-out videos, plus failure gallery | Never cut |
| **SHOULD** | `relook` recovery loop for low-confidence items | Cut only if not working at 2:15 |
| **COULD** | "See it here" preview (product placed in the user's frame) with fidelity check | Cut at the 2:15 freeze if unstable |
| **COULD** | Desk mode: photo of an empty desk + "make this warmer, under $150" | Cut first |

Explicitly out: 3D models, video generation, voice input, accounts, real order placement. Do not add anything else today.

---

## 3. Model responsibilities

| Model | Job |
|---|---|
| **Gemini 4 Argon** (`gemini-4-argon`) | Watches the video, lists items with timestamps and attributes. Does the second look (`relook`). |
| **Gemini 4 Hydrogen or Neon** (confirm exact ID in AI Studio) | Turns each item into catalog search queries, normalizes attributes. In desk mode, lists what to add. |
| **Decisions API** (`gemini-decision-1`, `client.decisions.create`, v1beta) | Scores every candidate: "same product?", "same color/variant?". In desk mode: "fits this style?", "fits this space?". Returns a probability per question. Not a Gemini 4 model, so it does not count toward the two-model rule. |
| **Image-edit model** (Nano Banana, or the current one in AI Studio) | Makes the "See it here" previews. |

The Decisions API takes one multimodal input (up to about 256K tokens) and up to 1,000 independent questions, and returns a confidence from 0 to 1 for each. **Check early whether it accepts multiple images in one input.** If not, put candidate titles and attributes into the questions and send only the crop as the input.

---

## 4. Status logic

Per item, take the best candidate's `p_same_product` and `p_same_variant`:

- `exact`: confident match
- `similar`: right kind of thing, not the same product
- `none`: no confident match, shown honestly in the UI

**Do not hardcode thresholds.** Pick them from the 12 build videos, then freeze them before running the held-out set. (Starting guess: exact at 0.8 or higher, similar at 0.5 or higher.)

`relook`: when an item is `similar` or `none`, Argon re-samples frames in a +/-2 second window at a higher rate, writes a sharper description and query, and the item is re-checked once. Set `recovered: true` if the status improved.

---

## 5. Data contract (the thing we all agree on)

Lives in `contracts/run.schema.json`, with a hand-written example in `fixtures/sample_run.json`. Person 3 builds the UI against the fixture from minute one. **Changing the contract needs a PR that all three approve.**

```json
{
  "run_id": "r_001",
  "mode": "video | desk",
  "source": { "video_id": "abc", "duration_s": 94.0, "budget_usd": null },
  "items": [
    {
      "item_id": "i1",
      "t_start": 12.4,
      "t_end": 15.0,
      "crop_path": "frames/r_001/i1.jpg",
      "description": "matte black arc floor lamp, brass base",
      "attributes": { "color": "black", "material": "metal", "category": "lighting" },
      "query": "black arc floor lamp brass",
      "candidates": [
        {
          "upid": "gid://shopify/p/...",
          "variant_id": "gid://shopify/ProductVariant/...",
          "title": "Arc Floor Lamp",
          "merchant_domain": "example.myshopify.com",
          "price": 129.0,
          "currency": "USD",
          "image_url": "https://...",
          "p_same_product": 0.91,
          "p_same_variant": 0.84
        }
      ],
      "status": "exact | similar | none",
      "recovered": false,
      "preview": { "image_path": "previews/r_001/i1.png", "fidelity": 0.88, "regenerated": false },
      "cart": { "cart_id": null, "continue_url": null }
    }
  ],
  "totals": { "price": 129.0, "within_budget": true }
}
```

---

## 6. Repo layout and ownership

```
seen-it/
  CONTEXT.md              # this file
  .env.example
  contracts/              # run.schema.json (shared, PR-reviewed by all)
  fixtures/               # sample_run.json, test frames
  data/                   # eval videos + ground truth (gitignored large files)
  backend/                # FastAPI
    video/                # P1: extract.py, relook.py, preview.py, desk.py
    matching/             # P2: catalog.py, checker.py, status.py, budget.py
    shopify/              # P2: client wrapper (see section 8)
    api.py                # shared glue (small, touch carefully)
  eval/                   # P2: run_eval.py, baseline.py, metrics.py, results/
  web/                    # P3: Next.js app
    components/ app/ lib/
  scripts/                # smoke tests, ffmpeg helpers
```

**Rule: only edit files in your own directory.** If you need something in someone else's area, ask in chat or open a small PR for them.

| Person | Owns | Main deliverables |
|---|---|---|
| **P1** | `backend/video/`, `scripts/` | `extract(video) -> items[]`, `relook(item)`, `preview(frame, product)`, desk prompt |
| **P2** | `backend/matching/`, `backend/shopify/`, `eval/` | catalog wrapper, Decisions checker, status logic, budget picker, evaluation harness |
| **P3** | `web/`, demo | player with timed labels, card panel, confidence badges, cart handoff, preview slider, desk tab, recording |

`backend/api.py` is the only shared file. Keep it to thin endpoints that call each person's functions.

### Function signatures (agree now, implement later)

```python
# P1
extract(video_path: str) -> list[Item]               # fills time, crop, description, attributes, query
relook(item: Item, video_path: str) -> Item          # sharper query from denser frames
preview(frame_path: str, product_image_url: str) -> str   # returns image path
desk_items(photo_path: str, request: str) -> list[Item]   # "what to add" items

# P2
search(query: str, filters: dict) -> list[Candidate]
check(item: Item, candidates: list[Candidate]) -> list[Candidate]   # fills p_same_*
resolve(item: Item) -> Item                          # search + check + status (+ relook trigger)
pick_within_budget(items: list[Item], budget: float) -> list[Item]
create_cart(merchant_domain: str, variant_id: str, qty: int = 1) -> dict

# API endpoints (api.py)
POST /run         {video | photo, mode, budget?}  ->  run.json
POST /preview     {run_id, item_id}               ->  preview path + fidelity
POST /cart        {run_id, item_ids[]}            ->  continue_urls per merchant
```

Until a real function exists, stub it to return data from `fixtures/sample_run.json`, so everyone can integrate from the start.

---

## 7. Git workflow

Short-lived branches, trunk-based. `main` must always run.

1. Branch from `main`: `p1/extract`, `p2/checker`, `p3/player`.
2. Commit small and often. Open a PR into `main` when something works end to end in your area.
3. Before opening a PR: `git fetch && git rebase origin/main`, then run `scripts/smoke.sh` (it hits the stubs and the fixture).
4. **Merge at least once per hour.** Fixed integration windows: **12:15, 1:00 (Checkpoint 1), 1:45, 2:15 (freeze)**. At each window everyone merges, pulls, and runs the full flow before going back to their own work.
5. One reviewer is enough, except for `contracts/` and `CONTEXT.md`, which need all three. Skim-review and merge fast; it's a hackathon.
6. Never force-push `main`. Never commit `.env`, API keys, large videos, or merchant images (see section 8).
7. If `main` breaks, whoever merged last fixes it immediately. Nobody else merges until it's green.
8. After 2:15 only bug fixes and eval-driven fixes go in. No new features.

Add to `.gitignore`: `.env`, `data/`, `frames/`, `previews/`, `eval/results/raw/`, `node_modules/`, `.venv/`.

---

## 8. Shopify: how we use it

We use Shopify only through its agentic-commerce stack (UCP, Shopify Catalog, shop.dev). We do **not** use the Admin or Storefront GraphQL APIs, and we don't run our own store.

**Discovery.** Global Catalog MCP at `https://catalog.shopify.com/api/ucp/mcp`. It searches across all eligible Shopify merchants ("eligible" does not mean literally every store). It works without a key at the lowest rate limits; **create a key now** in the Dev Dashboard (Agents) for higher limits. Exchange the client ID and secret at `POST https://api.shopify.com/auth/access_token` with `grant_type: client_credentials` to get a bearer token. Requests are JSON-RPC `tools/call`, and every one must include `meta.ucp-agent.profile` (the URI of our agent profile; start with Shopify's hosted example profile, host our own only if it's rejected).

Tools:
- `search_catalog`: free-text `catalog.query` plus filters (max price, ships-to, currency). Image input exists but has been **reported failing with a service error**. Test it once; **text queries are our default.**
- `lookup_catalog`: look up products or variants by ID, up to 50 per request.
- `get_product`: full variant and option data.

Results are grouped by Universal Product ID (UPID) with variants underneath. Keep each variant's ID, price, merchant domain and image URL.

**Cart.** Per merchant: find the merchant's endpoint from `/.well-known/ucp` (resolves to `https://{shop-domain}/api/ucp/mcp`), then `create_cart` with `line_items: [{ quantity: 1, item: { id: <VARIANT_ID> } }]`. It returns a cart ID and a `continue_url` that hands the buyer to the merchant's checkout. Use `update_cart` to iterate. Checkout MCP (`create_checkout` with a `cart_id`) is rate-limited more strictly, and one tutorial page says those tools are "coming soon," so **verify before relying on it**.

Cross-merchant Universal Cart is behind a "Request access" gate, so assume **one cart and one `continue_url` per merchant** and show them side by side. Alternative: Shop MCP at `https://mcp.shop.com` adds Shop Pay checkout for a signed-in shopper.

**We do not place real orders during the demo.** Show the cart landing on the merchant's checkout.

**Constraints:**
- Do **not** cache catalog results or re-host merchant images. Fetch images at request time and hold them in memory only for the Gemini checks. Persist only UPIDs, variant IDs and scores.
- The old REST endpoint under `/global/v2/` **stopped serving traffic on November 2**. Ignore any tutorial that uses it.

**Client (`backend/shopify/`):** typed wrapper with `searchCatalog(query, filters)`, `lookupCatalog(ids)`, `getProduct(upid)`, `createCart(merchantDomain, variantId, qty)`, `updateCart(...)`, `getContinueUrl(...)`; token caching; retry with backoff on rate limits; credentials from env vars; plus `scripts/shopify_smoke.py` that runs one search, one lookup and one cart creation.

Docs: https://shopify.dev/docs/agents, https://shopify.dev/docs/agents/catalog, https://shopify.dev/docs/agents/carts-and-checkout, https://www.shopify.com/catalog/agents.md

---

## 9. Environment

`.env.example` (copy to `.env`, never commit):

```
GEMINI_API_KEY=
GEMINI_ARGON_MODEL=gemini-4-argon
GEMINI_FAST_MODEL=            # Hydrogen or Neon: confirm ID in AI Studio
GEMINI_DECISION_MODEL=gemini-decision-1
GEMINI_IMAGE_MODEL=           # current image-edit model ID
SHOPIFY_CLIENT_ID=
SHOPIFY_CLIENT_SECRET=
SHOPIFY_AGENT_PROFILE_URL=https://shopify.dev/ucp/agent-profiles/examples/2026-04-08/cart-and-checkout.json
```

Tools needed: Python 3.11+, Node 20+, `ffmpeg`, `yt-dlp` (for downloading videos if Argon rejects YouTube links), the Shop CLI (`npm install --global @shopify/shop`).

---

## 10. Evaluation

- **Test set:** 18 videos (room tours or clothing hauls from brands that sell direct on Shopify). Ground truth comes from the product links in each creator's description. Check every link with `shop catalog lookup '<link>'` and keep only those that resolve to a catalog product. **12 build set, 6 held out.** Do not look at the held-out videos until after thresholds are frozen. Mention on the slide that the labels did not come from us. Each person collects 6 videos in the first 25 minutes.
- **Baseline:** one middle frame, one Gemini call, take the top search result, no checking.
- **Metrics:** items found, exact-product match, color/variant accuracy, invented items (judged by hand), and a 3-row calibration table (does 0.8 confidence mean about 80% correct?).
- **Recovery before/after:** run with and without `relook`. This is our "what we changed" result.
- **Stress curve:** stitch clips with ffmpeg into 30 s, 2 min and 5 min videos. Ground truth is the union of the clips' labels. Plot recall against length.
- **Preview fidelity** (if built): share of previews that pass the check before and after one regeneration, plus agreement between the checker and 20 pairs judged by hand.
- **Failure gallery:** 3 examples with causes (motion blur, look-alike product, item not in catalog).
- Output goes in `eval/results/` as `results.json` plus charts. P3 pulls the chart into the demo.

---

## 11. Timeline

| Time | What |
|---|---|
| **11:15-11:40** | Repo, `.env`, contract, stubs, smoke tests. P2: text search, image search, lookup, create cart. P1: Argon on one video (YouTube link or file?). P3: page on the fixture. Collect eval videos. |
| **11:40-1:00** | P1: extraction on all 12. P2: search plus checker on hand-cropped frames. P3: player, cards, badges. **Merge at 12:15.** |
| **1:00** | **Checkpoint 1:** one real video end to end, rough is fine. If it slips, cut the COULD tier now. |
| **1:00-2:15** | P1: `relook`, then `preview`. P2: harness, baseline, thresholds. P3: cart, polish, desk tab shell. **Merge at 1:45.** |
| **2:15** | **Feature freeze.** Full run on a video nobody has seen. |
| **2:15-3:00** | Run the 6 held-out videos. Fix the single biggest failure type and re-run. Make the chart. |
| **3:00-3:30** | Rehearse twice. Save a finished run of every demo input as a fallback, but record live. |
| **3:30** | Record. |

Check the participant guide for a video length limit (past Gemini events asked for about 3 minutes).

---

## 12. Demo script (about 3 min)

1. **0:00-0:20.** "You see a lamp in a video. A text description loses the exact color and finish, which is what you need."
2. **0:20-1:30.** Live run on a fresh video. Items appear with confidence badges, one gets upgraded by the second look, one stays "no confident match," then the cart.
3. **1:30-1:55.** "See it here": the matched lamp in the original room, then a jacket on a teammate (**use a teammate's photo, never a stranger's**).
4. **1:55-2:15.** Desk mode on our real desk: "make this warmer, under $150." Three picks, total shown.
5. **2:15-2:50.** Results chart, failure gallery, stress curve.
6. **2:50-3:00.** Architecture slide and close.

---

## 13. If something breaks

| Problem | Fallback |
|---|---|
| Catalog image search fails | Text queries plus the Decisions check (already the default) |
| Argon rejects YouTube links | `yt-dlp`, then upload the file |
| Decisions API takes one image only | Put candidate titles and attributes in the questions |
| Too few ground-truth videos | Label 6 ourselves from footage we didn't shoot; say so on the slide |
| Cross-merchant cart unavailable | One cart per merchant, shown side by side |
| Checkout tools don't work | Show the cart's `continue_url` landing on the merchant's checkout |
| Preview unstable at 2:15 | Cut it, demo without |
| Integration slips past 1:00 | Cut stress tests; protect the recovery loop and the results chart |
| `main` broken | Last merger fixes it; nobody else merges until green |

---

## 14. Smoke checklist for the first 25 minutes

- [ ] Repo created, all three can push, `.env` shared out of band (not in git)
- [ ] Gemini key works for Argon, the fast model, Decisions API and the image model (note exact model IDs above)
- [ ] Shopify: one `search_catalog`, one `lookup_catalog`, one `create_cart` succeed
- [ ] Image search tested once (works or not, decided)
- [ ] Example agent profile accepted (or we host our own)
- [ ] Argon accepts a YouTube link (or we use `yt-dlp`)
- [ ] Decisions API: multi-image input works (or fallback chosen)
- [ ] `fixtures/sample_run.json` committed and the UI renders it
- [ ] Each person has 6 eval videos with verified ground-truth links