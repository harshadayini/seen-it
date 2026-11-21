# Interactive Mobile App UI/UX Design Prompt — Seen It (`UI_DESIGN_PROMPT.md`)

Use the prompt below to design the **Seen It** **mobile app** interface (portrait `390×844` / `9:16` screens). It evolves the warm editorial palette of our earlier desktop reference (`/public/assets/aistudio/Screenshot_2026-11-21_at_11.50.05_AM_8796d7ce.png`) **without implementing it as-is**—translating it into an airy, thumb-friendly **mobile app** with minimal copy, cute **Cosmos (`cosmos.so`)** cutout icons, multi-product **Swap in Frame**, and the mobile-exclusive **Virtual Twin** camera mode that generates matched Shopify products directly in the user's real world.

---

## Copy-Paste Mobile Design Prompt

> **Design an interactive MOBILE APP UI (`390×844` portrait iOS/mobile screens) for "Seen It" — an omnimodal visual-commerce, multi-product frame-swap, and real-world Virtual Twin app.**
>
> **Reference Direction (DO NOT implement as-is):** Borrow ONLY the warm alabaster-paper aesthetic (`#FAF8F4`), *Lora* editorial serif headers, and terracotta accent (`#B5533C`) from the reference screenshot. **Reimagine it completely for mobile:** ultra-clean, airy, thumb-first, 70% fewer words, zero dense jargon/telemetry, decorated gently with cute **Cosmos (`cosmos.so`)** cutout icons, and featuring **Virtual Twin**—a mobile-only live camera mode that places/generates matched products straight into your real room or mirror view.
>
> ---
>
> ### 1. Cosmos Cute Icons & Tactile Mobile Charm
> * **Use Cosmos (`cosmos.so`) to source editorial lifestyle imagery AND cute decorative object cutouts** sprinkled lightly across the mobile screens:
>   * Mini **35mm camera / film reel** (Video & Virtual Twin), **vinyl record / cassette** (Song / Voice), **vintage sunglasses / ribbon** (Fashion), **ceramic mug / table lamp** (Home), **Polaroid / paperclip** (Pinterest & Moodboards), **woven tote bag** (Bags).
> * **Mobile Placement Rules:**
>   * Place tiny cutouts delicately around the Drop empty state, modality pills, sheet corners, and Virtual Twin empty/loading states—with subtle organic tilt (`-5deg` to `+5deg`) and generous whitespace.
>   * Keep it playful, warm, and editorial—never crowded or noisy on a small screen.
>
> ---
>
> ### 2. Strict Anti-Clutter & "Less Wordy" Mobile Rules
> * **Zero paragraphs or long subtitles.** Every screen title is 2–4 words max; buttons and chips are 1–3 plain human words (`Drop anything`, `Inspect`, `Swap`, `Virtual Twin`, `Exact · 92%`, `Add to bag`, `Checkout ↗`).
> * **Delete all technical/enterprise bloat:** No `"Omnimodal Engine"`, `"Acoustic Aura Synchronizer"`, `"Protocol Telemetry"`, `"Direct API Handshake"`, `"Scene Anchor"`, `"Diagnostic Spectral Trace"`, session IDs, or fake inventory countdown timers.
> * **Thumb-Friendly Navigation:**
>   * One minimal floating **bottom navigation bar** (4 clean icons + 1-word labels): `Drop` · `Studio` · `Twin` · `Bags (3)`.
>   * Quiet top-right `Lab` icon button to open the Element 119 escalation/breaking-point sheet only when wanted.
> * **Gesture-First Mobile Patterns:**
>   * Edge-to-edge full-bleed vertical media (`9:16` video/photo/live camera) paired with smooth **swipe-up bottom sheets** for matched products, swap trays, and match traces.
>
> ---
>
> ### 3. Palette & Typography
> * **Warm Paper Light Mode (Default):** Ivory canvas (`#FAF8F4`), white cards (`#FFFFFF`) with hairline borders (`#EBE6DE`), espresso ink (`#1F1C18`), warm stone secondary text (`#8A8277`), terracotta primary accent (`#B5533C`). Camera & full-bleed video screens use subtle frosted glass overlays (`rgba(250, 248, 244, 0.86)` with backdrop blur) so controls float cleanly over live footage.
> * **Typography:** *Lora* serif for editorial titles, *Inter* / *Plus Jakarta Sans* for crisp small UI labels, and *JetBrains Mono* strictly for prices (`$148`), timestamps (`0:14`), and match % (`92%`).
>
> ---
>
> ### 4. Core Mobile Screens (`390×844` Portrait)
>
> #### Screen 1 — `Drop` (Omnimodal Mobile Intake)
> * Airy, joyful mobile landing canvas gently framed by 4–5 small floating **Cosmos cutout icons** (mini film camera, vinyl disc, sunglasses, Polaroid, ceramic mug).
> * Minimal *Lora* headline: **`Drop what you saw.`** (no paragraph below it).
> * Clean big tap-to-add surface + compact scrollable row of cute Cosmos-icon modality buttons: `Video` · `Song` · `Voice` · `Photo` · `Pinterest`.
> * One slim bottom note bar: *"Add a note… under $150, not suede"* with a mic button for quick voice constraints.
> * Horizontal peekable carousel of **3 visual-only Cosmos sample cards** (`Dim Street Reel`, `Indie Song Mood`, `Cluttered Desk` — clean vertical photo + tiny cute icon + 2–3 word title only).
>
> #### Screen 2 — `Studio` (Full-Bleed Vertical Media + Swipe-Up Catalog Sheet)
> * Top floating pill toggle over full-bleed `9:16` media: **`Inspect`** | **`Swap (2)`**.
> * **In `Inspect` mode:**
>   * Vertical video/photo/moodboard fills the top ~62% of screen with minimal numbered pins (`1`, `2`, `3`).
>   * Slim touch-scrubbable filmstrip + tiny audio waveform dots for spoken notes.
>   * **Draggable Bottom Sheet** peeking at the bottom with horizontal category filter words (`All` · `Coat` · `Bag` · `Shoes`) and swipeable horizontal product cards:
>     * Crisp merchant photo (direct merchant URL), title, merchant name, price, and tiny match tag (`Exact · 92%` / `Close dupe`).
>     * Three compact icon/text actions: **`Swap`** (multi-select toggle), **`Twin`** (send straight to real-world camera), and **`+ Bag`**.
>     * Quiet `Trace ▾` tap to reveal Gemini tier (`Hydrogen` / `Neon` / `Carbon` + `Decisions API`).
> * **In `Swap` mode (Multi-Product Swap Into Frame):**
>   * Works with **1 or MULTIPLE matched products currently in the catalog at once** (e.g., coat + bag + sunglasses all swapped into the same frame simultaneously).
>   * Full-bleed **Before / After swipe curtain slider**.
>   * Compact floating **Swap Tray** above the bottom nav showing active swapped product thumbnails (`×` to remove, tap to switch variant) + terracotta **`Update`** button.
>
> #### Screen 3 — `Twin` (Mobile-Only **Virtual Twin** — Real-World Camera Placement)
> * **Signature mobile-only experience:** Full-bleed live phone camera viewfinder (`rear camera` for room/furniture/objects, quick flip to `front camera` for outfits/accessories/mirror try-on).
> * **How it looks & feels:**
>   * Clean, uncluttered viewfinder with subtle corner framing brackets and a tiny floating Cosmos camera/lamp charm when no items are placed yet (*"Point at your space"*).
>   * **Tap-to-place & Multi-Product Real-World Generation:** Users can pick **1 or multiple** products from their active catalog tray at the bottom (e.g., floor lamp + ceramic mug + accent chair, or jacket + crossbody bag), tap where they want them in the real-world frame (subtle glowing terracotta floor/surface pins), and tap the centered shutter/generate trigger **`Place in room`** (or **`Try on`** in selfie/mirror mode).
>   * Renders the photorealistic **Virtual Twin** right inside the user's real room/body lighting, shadows, and perspective, with:
>     * Instant **Hold to see real room** (press-and-hold Before/After peek).
>     * Horizontal **Active Catalog Dock** at bottom to toggle/add/remove multiple products in the real-world scene without leaving the camera.
>     * One-tap **`Add placed items to bag`** + **`Save snap`** controls.
>
> #### Screen 4 — `Bags` (Per-Merchant Mobile UCP Carts)
> * Clean vertical stack of crisp merchant cards (one card per Shopify merchant, e.g., `ssense.com`, `studionicholson.com`) with a cute tiny Cosmos tote icon beside **`Your Bags`**.
> * Each card shows: merchant domain, compact item rows (thumbnail, title, variant, `- 1 +` stepper, price), subtotal, and a full-width terracotta button: **`Checkout at {Merchant} ↗`** (links directly to `continue_url`).
> * Zero telemetry boxes, zero session IDs, zero countdown timers.
>
> #### Modal Bottom Sheet — `Lab` (Element 119 Judge & Breaking-Point View)
> * Tucked behind the quiet top-right `Lab` icon so the main mobile app stays calm and uncluttered.
> * Compact mobile sheet displaying: Tier 1 (`Hydrogen`) → `Decisions API` (`0 output tokens`) → Tier 2 (`Neon`) → Tier 3 (`Carbon`) escalation trace, calibrated confidence bars, and breaking-point flags (blur, occlusion, lighting trap, abstention).
>
> ---
>
> ### 5. Deliverables to Generate (All `390×844` Mobile Portrait)
> Design 5 clean, airy, interactive mobile screens side by side:
> 1. **`Drop`** — Airy intake screen framed by cute Cosmos cutout icons + minimal modality bar + 3 visual-only sample cards
> 2. **`Studio — Inspect`** — Full-bleed vertical video with minimal pins + swipe-up matched catalog sheet
> 3. **`Studio — Swap`** — Multi-product Before/After frame swap slider (2+ catalog items active) + floating Swap Tray
> 4. **`Virtual Twin` (Live Camera)** — Full-bleed mobile viewfinder generating/placing 1+ matched Shopify products directly in the user's real room/mirror with press-to-compare & bottom product dock
> 5. **`Bags` (+ `Lab` sheet peek)** — Clean stacked per-merchant UCP cart cards with `Checkout ↗` handoffs
