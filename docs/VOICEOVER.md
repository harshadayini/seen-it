# Voice-over scripts

Written for: judges and viewers watching the demo. Speak at a calm, steady pace (about 150 words a minute). Everything said here is something the product does today; check the "never say" list before improvising.

## A. The 1-minute recorded video (about 150 words)

| Time | On screen | Say |
|---|---|---|
| 0:00 to 0:08 | A video playing, paused on a lamp | "You see a lamp in a video and you want it. Searching 'black lamp' throws away the exact finish. Seen It starts from the video itself." |
| 0:08 to 0:22 | Paste the link, press Find products; cards appear one by one | "Paste a link. Gemini 4 Argon watches it and finds every product. Cards appear live, each matched to real Shopify listings, with a confidence from the Decisions API: exact, close, or, honestly, no confident match." |
| 0:22 to 0:32 | A card gets the "Second look improved this" badge | "When it isn't sure, it looks again at denser frames, rewrites the search, and only upgrades a match if it truly improves." |
| 0:32 to 0:44 | Open a matched item, upload a room photo, tap a spot, the before/after slider | "Pick one and see it in your own space. Upload your room, tap where it goes. The Gemini image model places it, and Decisions checks the result." |
| 0:44 to 0:52 | Add to cart, open the merchant checkout page | "Add to cart and you land on the merchant's real checkout. We stop there. No orders are placed." |
| 0:52 to 1:00 | The architecture slide or the results screen | "Argon watches. Hydrogen writes the searches. Decisions verifies. Seen It: every video becomes shoppable, with confidence you can trust." |

Tip: record the screen first without sound, then read the script over it. Cut the preview step if it isn't smooth; the script still works without lines 0:32 to 0:44 (add one sentence about the evidence instead).

## B. The 3-minute live talk track

**0:00 to 0:20, the hook (before the run starts)**
"You see a lamp in a video. A text description loses the exact color and finish, which is the whole point of buying that lamp. And video is messy: shaky, fast cuts, half-hidden things. We built an agent that finds the products, checks its own work, recovers when it's wrong, and gets you to checkout."

**0:20 to 1:30, the live run (paste any link a judge gives you; start it, then talk)**
- While it works (first 15 seconds): "Argon is watching the whole video right now, listing every product it can see, with when it appears."
- When cards appear: "Each card is a real product on a real store, with its price. The label is not our guess. It comes from the Decisions API, which scores 'is this the same product?' and 'is it the same color?' and we turn that into exact, close, or no confident match."
- Point at the latency on screen: "Items stream in as each one finishes, so you're never waiting on the slowest."
- Point at a weak card getting upgraded: "This one started as a close match. Argon took a second look at the frames around it, found a clearer view, and wrote a better search. It only says 'second look improved this' when the status really went up."
- Point at a no-match card: "And this one stays 'no confident match'. We would rather say so than show you something wrong."

**1:30 to 2:00, see it in your space**
"Now the part that matters before you spend money: how does it look in my room? Upload a photo of your space, tap where it should go. The Gemini image model places it, and the Decisions API checks the result against the real product photo and your original scene. It scores honestly; if it looks off, it says so and lets you try again."

**2:00 to 2:20, the cart**
"One tap adds it to a cart, one cart per merchant, and this link is the merchant's real checkout. We stop here. We never place orders."

**2:20 to 2:50, the evidence (only say what you measured)**
"Honestly, here's what we saw. On a real, unscripted desk video, items appear in about fifteen seconds and a full run takes about a minute. The second look upgraded between none and six of ten items across our runs. Where it breaks: Argon's item list changes between runs, tiny or half-hidden items can lose their crop, and our room-preview check is strict, so believable images can score modestly. We show all of that instead of hiding it."

**2:50 to 3:00, the close**
"Argon watches. Hydrogen writes the searches. Decisions verifies, and the image model shows it in your space. Seen It: every video becomes shoppable, with confidence you can trust."

## C. If something goes wrong (say these calmly)
- **Run is slow:** "While that finishes, here's what's happening under the hood..." then describe the pipeline. Never apologize twice.
- **A step fails:** "Our system tells you plainly when it can't do something instead of inventing an answer. Here's the same run from earlier." Switch to the saved run and say it is recorded.
- **A match looks wrong:** "That's exactly why the label says close, not exact. The score is lower, and this is what the second look is for."

## D. Likely questions, short honest answers
- **Is it accurate?** "We haven't published a labeled accuracy number. We show a calibrated confidence per match and say 'no confident match' when it isn't sure."
- **Why not Google Lens?** "Lens searches the whole web. We verify against stores that can actually sell it, with a probability, and we check out." (Only mention a head-to-head if you ran one.)
- **What models?** "Argon watches and does the second look, Hydrogen writes the search queries, the Decisions API scores matches and checks previews, and the Gemini image model draws the preview."
- **Does it store data?** "No catalog caching, no re-hosted merchant images, no real orders. Your photo is kept locally and is not shared with Shopify."
- **Is it 3D?** "No. It's a generated 2D picture of the product in your photo."

## Never say
- "3D", "AR", or "scans in real time".
- Any accuracy percentage, "better than Google Lens", or "beats a baseline" unless the evaluation really produced it.
- "Always" or "100%" anything. The item list varies between runs.
- That the preview is a video. It's one image.
