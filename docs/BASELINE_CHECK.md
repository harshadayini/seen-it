# Baseline check: single-shot vs Seen It

One real, unscripted video (a desk-setup YouTube Short), run both ways on 21 Nov 2026. This is **not** a labeled benchmark: there is no ground-truth file, so each verdict below was judged **by eye** (crop or video frame next to the matched product photo). The two systems also find slightly different item lists, because Gemini's item list varies between runs. Treat it as a worked example, not a statistic.

## The two systems

| | Baseline (`eval/baseline.py`) | Seen It |
|---|---|---|
| Input to the model | **One** middle frame | The whole video, then a still frame per item |
| Gemini calls | 1 (plus one catalog search per item) | 32 in this run: 1 video pass, 4 box passes, 1 query writer, 18 Decisions checks, 8 second looks |
| Search query | The model's label, as is | Rewritten by Gemini 4 Hydrogen; rewritten again by the second look when weak |
| Verification | None. Take the first search result | Decisions API: probability that it is the same product and the same variant |
| Output per item | A product, with no signal of how sure it is | A product with an exact / close / no-match label |
| Time | **10 s**, 9 items | **68 s**, 10 items (first matches at about 28 s) |

## Baseline result (9 items, top search hit, no checking)

| # | Label the model gave | Top result | By eye |
|---|---|---|---|
| B1 | LED desk light bar | Adjustable LED Light Bar for Computer and Desk | Looks right |
| B2 | LG computer monitor | LG 29" UltraWide monitor | Right brand, wrong model (the video monitor is a standard 16:9) |
| B3 | wooden monitor stand riser | Wooden Monitor Stand Riser Organizer | Looks right |
| B4 | smart speaker | Apple HomePod mini (white) | **Wrong**: the video shows a dark Echo-style speaker |
| B5 | mini blue alarm clock | Lamisola travel alarm clock (square, navy and gold) | **Wrong style**: the video has a blue twin-bell clock |
| B6 | compact wireless keyboard | EXKnight M4 mini keyboard | Unclear |
| B7 | desktop phone stand | Aluminum phone dock | Looks right |
| B8 | vertical laptop stand | TECKNET stand with a hub-like base | **Off**: the video has a plain two-slot stand |
| B9 | black computer desk | Garvee 47" desk | Plausible |

**Roughly 4 of 9 look right, 3 look clearly wrong, 2 are unclear. Nothing tells the user which is which.**

## Seen It result (10 items, with second look)

| # | Item (cropped from the video) | Matched product | Label | Second look | By eye |
|---|---|---|---|---|---|
| i1 | monitor light bar | Clip-on LED desk lamp with light bar and gooseneck | Exact | Yes (started as no match) | Looks right |
| i2 | monitor | LG 27" HDR10 **curved** monitor | Exact | | Over-confident: video monitor looks flat |
| i3 | monitor riser | Wooden monitor riser | Close | Yes | Plausible |
| i4 | compact keyboard | Epic Mini Keyboard, black | Exact | Yes | Plausible (crop fell back to the full frame) |
| i5 | smart speaker | Echo Dot, black | **No match** | | The top result looks right; the checker was too cautious (tiny, dark crop) |
| i6 | alarm clock | Vintage twin-bell clock (silver, blue face) | Close | | Right kind, not the same clock, so "close" is fair |
| i7 | figurine | Knight figurine | Close | | Plausible |
| i8 | ergonomic mouse | Logitech M705 | Close | Yes | Plausible (crop fell back to the full frame) |
| i9 | desk mat | PU leather desk pad, light grey | Close | | Looks right |
| i10 | headphones | Sony WH-CH520 | Exact | | Over-confident: shown in beige, the video's are blue |

**Roughly 7 of 10 look right. Two "exact" labels are over-confident on a detail (model shape, color). One correct product was missed by being too cautious. Every item carries a label, so the user knows which three deserve a second glance.**

## What this shows

- The baseline is 7x faster and good at simple, distinctive items (a light bar, a wooden riser).
- Where it is wrong, it is wrong silently. Seen It's checks turn "which of these is wrong?" into a visible label, and its second look rescued items the first pass missed (the light bar went from no match to exact).
- Seen It is not perfect. Its "exact" is too generous on color and model details, and it can be too cautious on small, dark crops. A labeled evaluation would put numbers on both.

## An earlier run, and a bug this check found

The first Seen It run here had **no second look at all**: the 45-second budget counted from the start of the run, extraction was slow that time, and no time was left. We changed the budget to start when matching finishes (`SECOND_LOOK_BUDGET_S`), then re-ran. The table above is the corrected run. Without the second look, that same video produced 2 exact, 4 close and 4 no-match.
