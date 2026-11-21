# Seen It: pitch outline (trimmed scope)

Scope matches CLAUDE.md after cuts: no "See it here" preview and no desk mode unless they are solid by 3:00.
Every `[FILL]` is a number from a real run (`eval/results/`). Never type a number we did not measure.

## One-liner
Every video becomes shoppable, with confidence you can trust.

## Problem (20 s)
You see a lamp in a video. A text description throws away the exact color, finish and shape that identify it.
The input is messy: shaky, fast cuts, half-hidden items. We built an agent that finds, verifies, recovers and checks out.

## Live demo (3 min)
| Time | Say / show |
|---|---|
| 0:00-0:20 | The problem above. Paste a link (judge's video if they hand us one; otherwise a fresh one we never ran). |
| 0:20-1:30 | Run starts. Talk over it. Items appear one by one with confidence badges and latency on screen ("[FILL] candidates checked in [FILL] s"). Point at: one exact match, one that the second look upgraded, one that stays "no confident match" (we say so instead of guessing). |
| 1:30-2:00 | Pick items, build the cart. Show the merchant checkout link. We stop before any real order. |
| 2:00-2:40 | Evidence slide (below). |
| 2:40-3:00 | Architecture slide and close. |

If a run is slow or fails: switch to the saved run of the same video (label it "recorded run") and keep going.

## Recorded video (1 min)
- 0:00-0:10 hook (the lamp).
- 0:10-0:40 one run on a fresh video: items, confidence, the upgrade, a "no match", the cart.
- 0:40-0:52 evidence: baseline vs ours on videos we did not tune on, plus one failure and the fix.
- 0:52-1:00 one-line architecture and close.
Only show what we built today.

## Evidence slide (25% of the score)
Left: bar chart, three systems on the held-out videos: single-frame baseline, ours without second look, ours with second look.
Metrics: items found `[FILL]`, exact-product match `[FILL]`, color/variant match `[FILL]`, invented items `[FILL]`.
Right: one failure with its cause (for example motion blur, look-alike product, item not in the catalog) and what the second look did about it.
Footer: how labels were made (state it honestly: own videos with products we know, plus found videos hand-checked; held-out set not used for tuning).
Calibration row: when we say 0.8, how often are we right? `[FILL]`.

## Architecture slide (one picture)
Video -> **Gemini 4 Argon** (watches, lists items, times, boxes on a still) -> **Gemini 4 Hydrogen** (turns each item into catalog queries) -> **Shopify Catalog** (candidates) -> **Decisions API** (calibrated "same product? same color?" scores) -> status exact / similar / none -> second look (Argon, denser frames) when weak -> **Shopify cart** per merchant -> checkout link.
Say which model does what, and that the Decisions API gives a probability per question, not a vibe.

## Likely questions, honest answers
- *Does it find everything?* No. Argon misses items and the list is capped at 10. We measured recall: `[FILL]`. The second look recovers some.
- *Why not Google Lens?* Lens searches the whole web; we verify against Shopify with a confidence score and say "no match" when unsure. (Only claim a Lens comparison if we really ran one.)
- *What breaks it?* Name the real failure from the gallery. Do not invent one.
- *Latency?* `[FILL]` s end to end; items stream in as they finish.
- *Do you store merchant data?* No: no catalog caching, no re-hosted images, only product IDs and scores.
- *Is this an image analyzer or chatbot?* No: it's an agent that acts: finds, verifies, recovers, builds the cart.

## Before we present
- Repo public; all three of us on the submission form.
- One saved run per demo input as a fallback.
- Someone who is not driving watches the clock.
