# BGS Corner — project instructions and current understanding

BGS Corner General Trading LLC, Dubai. A fragrance-only UAE ecommerce store:
house-blended attars, ouds, EDP sprays and bakhoor.

**Status: design phase.** No application code exists in this repository yet,
by instruction. This file is the standing record of what has been decided and
what is understood, so the next session starts where this one stopped.

Source specification: the owner's build brief, `~/Downloads/BGSecommercebuildbrief.md`.
Section numbers below (§4, §6.1, §15…) refer to it.

---

## 1. Standing rules

These constrain everything else in this file.

1. **Never push without explicit consent.** Commit locally; leave it there.
   This repository is public and a push is the step that cannot be quietly
   undone. Creating a remote counts as publishing too.
2. **Never pull information from other websites without consent.** No
   competitor research, no reference material, no fetching. Ask first.
3. **Never import a database or catalogue from anywhere else.** The workbook
   catalogue, the Firestore data and the seed products in the sibling repos
   stay there. A design-phase repository carries decisions, not inherited data
   nobody has re-checked.
4. **Never invent anything to fill a gap.** No placeholder statistics, no
   fictional products, no invented prices or turnaround promises. Where a real
   figure is missing, the space stays empty until someone supplies it.

---

## 2. Design direction

### Light theme
The site is light-themed. Every earlier BGS build defaulted to obsidian and
brass; this one does not. Light is the ground, not a mode bolted on after —
contrast, shadow and metallics are designed against a pale surface from the
first screen rather than inverted from a dark one.

### A wide palette, earned from the taxonomy
The site uses a broad range of colour, against the single-accent convention.
The palette is driven by §4's `scent_family`, so colour carries information
rather than decorating: seven families, seven identities, and a bottle keeps
its colour from the collection grid through the PDP into the cart line and
onto the gift-box preview.

| Scent family | Reads as |
|---|---|
| Oud & Woods | Deep resinous brown-green |
| Amber & Spice | Burnt amber |
| Musk & Clean | Cool pale slate |
| Floral Veil | Rose |
| Fresh & Citrus | Bright herbal green |
| Sweet & Gourmand | Plum |
| Reserve | Near-black with gold — the halo tier, visibly apart |

Hues are **proposed, not settled**. Each family ships two stops: an *ink* dark
enough for text at WCAG AA on the light ground, and a *wash* for fills that
never carries text — otherwise half of seven colours fail a contrast check the
moment a label is set in them.

Colour is a product attribute, so it also fills the CSS-drawn product
stand-ins: a card shows the kind of thing it sells, tinted by what it smells
like, with no photograph required.

### Scarcity cues must be true
Low-stock messaging ("3 left") is wanted, driven by **real inventory**:

- The number shown is the number in stock. Read, not chosen.
- A threshold decides when the cue appears, set in admin, not in code.
- Above the threshold, nothing is shown. Silence is the default.
- Enquiry-priced products show no cue — there is no count to be honest about.

A fabricated "3 left" is a false statement to a customer about a material fact
in a purchase decision, and the easiest claim in the build to disprove.

### Premium products are never discounted
Products marked `margin_role: halo` (§4) are excluded from every path that
reduces a price: the §6.1 volume ladder, coupon codes, campaign percentages,
loyalty redemption and gift-with-purchase thresholds alike.

Enforced **structurally, not by policy** — one predicate every discount surface
must ask before touching a line, so a mechanism added later cannot forget. A
halo product does not decline a discount; it has no arithmetic path to one.

---

## 3. What the brief requires

### The commercial thesis
A fragrance-only UAE store, Dubai-first with same-day. The basket must average
**AED 160+** against ~AED 50 kiosk items. Three levers do that work: tiered
bundle pricing, gifting as the primary use case, and WhatsApp retention through
GoHighLevel. Contribution is ~AED 56/order at that AOV against ~AED 20
delivery — which is where free delivery ≥ AED 150, AED 12 below, and same-day
Dubai +AED 25 come from. Those are margin arithmetic, not preferences.

### The spine: one scent taxonomy (§4)
A single structured vocabulary on every product, EN + AR, powering filters, the
quiz, review tags, recommendations, rule-driven collections, GHL segments and
SEO landing pages. Get it wrong and six modules are wrong.

- `scent_family`, `tone`, `gender_lean` — **one value each**, deliberately. A
  scent that is woody and floral and fresh is a scent nobody can be
  recommended, and a quiz cannot score against a product claiming every answer.
- `occasion[]`, `season[]` — genuinely plural.
- `longevity`, `sillage`, `format`, `size`, `notes_pyramid`, `wears_like`,
  `batch_number`, `alcohol_free`, `same_day_eligible`, `margin_role`.
- Per-product SEO fields: meta title/description, slug (EN+AR), alt texts.

### Hard blockers (the brief's MUSTs)
- Halo products structurally undiscountable — not merely un-discounted.
- Fixed sets can never oversell their components.
- COD defended: AED 8 fee, disabled above AED 300 and on QR-video orders and
  for customers with a prior refusal; orders enter `cod_pending` and ship only
  after confirmation.
- Guest checkout works end to end; accounts optional.
- **A typed event outbox.** Every commerce action emits to it
  (`order.created`, `order.cod_pending`, `order.confirmed`, `order.fulfilled`,
  `order.delivered`, `order.refunded`, `cart.abandoned`, `review.requested`,
  `voucher.issued`, `optin.captured`). GHL and analytics both consume it. No
  outbox means no automation — everything downstream depends on this layer.
- Tiered cart pricing: 3+ items −10%, 6+ −15%, automatic, excluding halo,
  Wedding Favours, quotes and fixed sets.
- Build-a-Gift-Box: 3 or 6 slots, live visual, one cart line, itemised.
- Sample credit-back: any 3ml purchase issues a single-use voucher of its own
  value, 60-day expiry, redeemable on any bottle ≥ AED 75.
- Referral, even if loyalty tiers slip: friend AED 20 off first order ≥99;
  referrer credited only after the friend's delivery + 3 days.
- Faceted filters: multi-select, URL-persistent, AR + EN, taxonomy-driven.
- Scent quiz: 5 questions under 60s, consent captured unchecked by default.

### Division of responsibility (§13)
The **store** owns products, orders, inventory, payments, vouchers and consent
capture. **GHL** owns messaging orchestration, pipelines and campaigns. No
commerce state lives only in GHL. Consent is two-way: one opt-out silences
both systems, and the store's ledger is the legal record.

### SEO and performance are acceptance criteria, not aspirations
- SSR/ISR for every indexable route; no content behind client-only JS.
- Whitelisted single-facet URLs indexable with unique copy; all multi-facet
  combinations `noindex,follow` + canonical to base, to prevent crawl explosion.
- Slug 301 history, hreflang en-AE ↔ ar-AE, schema, sitemaps.
- **Mobile on throttled 4G: LCP < 2.5s, CLS < 0.1, INP < 200ms** on home,
  collection and PDP. Hero poster ≤ 1.5MB. JS < 300KB gzipped per template.

### The admin portal is part of the build (§16)
Ten modules, role-gated, mobile-usable. The real acceptance test: a
non-technical person can add a taxonomy'd product, receive stock with a batch,
clear a COD queue, publish an occasion landing page, generate an influencer
code and read the dashboard — with no developer.

---

## 4. Decisions taken

| Question | Decision |
|---|---|
| Which repo | `structured-corner-v2` — this one, fresh. `bgscorner-final` remains the reference build. |
| Catalogue | Real data wins over the brief's §3 price table. Build the *engine* (fixed-price sets with component inventory); do not seed invented SKUs. |
| Analytics | Server-side first, off the §13 event outbox, with a consent banner. First-party remains the source of truth. |
| Loyalty name | The brief says "BGS One"; a later commit in `bgscorner-final` renamed it "BGS X". The rename is the newer decision and wins unless the owner says otherwise. |

---

## 5. Open conflicts between the brief and reality

Unresolved. Each needs an owner decision before the affected module is built.

1. **The catalogue.** The brief specifies a fragrance-only launch set at fixed
   prices (3ml/6ml attars at 45/75, EDP at 89, Discovery Trio 129, Majlis OUD
   650/1,295). The real shop, per `bgscorner-final`'s workbook import, is 76
   products — 44 published — with house perfumes at AED 70 and oud sold *by
   enquiry* because it is priced by weight in conversation. These are
   different stores. The brief's AOV engine assumes fixed prices throughout.
2. **Analytics.** §12 mandates Meta Pixel + Conversions API and GA4 before the
   first ad dirham. `bgscorner-final` is deliberately first-party only, with no
   third-party script. Resolved above in favour of server-side, but the owner
   has not confirmed.
3. **Stack.** The brief specifies PostgreSQL/Prisma on Vercel. The existing
   build is Firestore on Netlify. Undecided for this repository.

---

## 6. State of play in the sibling repositories

Read-only context. Nothing is copied out without consent (rule 3).

**`bgscorner-final`** — 70 commits, the reference build. Next.js 16 App Router,
TypeScript strict, Tailwind v4, money as integer fils, Firestore, Netlify.
Already carries brief work:

- §4 scent taxonomy, with publishing blocked when it is incomplete
- Halo discount guard through a single `isDiscountable` predicate
- §6.1 tier ladder and §6.5 gift threshold as pure functions shared by cart
  and server, so the preview and the charge cannot disagree
- EN/AR with compile-checked dictionaries; RTL via CSS logical properties
- Admin: products, orders, stock, coupons, loyalty, reviews, analytics, settings
- Payments: Stripe, Tabby, Tamara, COD, bank transfer
- A GHL bridge where a CRM failure never costs an order

**Missing there** (and therefore still unbuilt anywhere): all of §7 gifting —
build-a-box, wrap and card, QR video message, scheduled delivery,
ship-to-recipient, corporate gifting; the §6.4 credit-back voucher; the §8.3
quiz; §10.3 COD rules; §10.4 same-day cutoff gating; §11 referral; the §13
event outbox; §14.4 faceted indexing policy and §14.5 landing pages.

**`bgscorner-v2`** — content CMS, FAQ admin, rotating utility bar, marketplace
chrome. Diverged from `final`; has none of the brief work.

---

## 7. What the nine prototypes are worth

Seven static prototypes exist alongside the two commerce builds. Five are
variations on a scroll-scrubbed canvas film hero.

**The constraint that settles it:** the film packs run from 4.4MB to 22.9MB,
in folders from 22MB to 150MB. A hero that paints only after a multi-megabyte
stream cannot pass §15's LCP gate, and scroll-jacking fights the two things the
brief puts on the home page — a mobile filter drawer and a live countdown.
Keep the footage; discard the delivery mechanism. §5 asks for a poster-first
video hero and §9 for a 15s PDP slot, both ordinary streamed video.

Worth taking:

- **`bgs-corner-web`** (132KB, zero image files) — the CSS-drawn product
  stand-in. Its premise is that there is no photography and the fragrance
  supplies two colour stops. Already ported into `bgscorner-final` and
  improved. Extend it: key the drawing off §4 `format` rather than category,
  and add a box drawing, because build-a-box needs a live visual of slots
  filling and no photograph of that box exists. Its single-variable `--fw`
  scaling is exactly what a slot preview needs at three sizes.
- **`BGS-CORNER`** — the information architecture: collection filtered by
  family and sorted; PDP running formats → notes pyramid → specs → related.
  That is §9's reading order minus the commerce, and its `{top, heart, base}`
  note shape is §4's `notes_pyramid`. Take the order, rebuild the mechanism —
  §8.1 needs nine facets, not two controls.
- **`corner-60-fps`** — one technique: choose an asset tier from viewport × DPR,
  `saveData`, `effectiveType` and real AVIF decode support, download exactly
  one, and deliberately do not preload, because preloading a runtime decision
  makes every visitor on another tier download twice.
- **`corner-40-fps`** — one principle: its recolour runs offline so the browser
  does no work. Every media transform happens at upload time, never at request
  time.
- **`cornersiteaccordingtoshakirunc`** — headline and wordmark as live text
  tinted through `background-clip`, not images of text: an SEO and
  accessibility win, and necessary for Arabic, where an image of a headline
  cannot reflow RTL. Its `archive/` pattern is the instinct behind §14.7's
  redirect manager and slug 301 history.

**Deliberately left behind:** the scroll-scrubbed hero in all five variants,
and both fictional catalogues — `bgs-corner-web` sells "Ambre Nocturne" at AED
1,450 in an edition of 240 bottles; `BGS-CORNER` sells "Nuit d'Or" at the same
price. None of it exists. See rule 4.

---

## 8. Open questions

1. The seven family hues need real values, contrast-checked on the light ground.
2. Conflict 1 (catalogue) needs an owner decision before pricing, bundles or
   the quiz can be built on top of it.
3. Stack for this repository: Firestore, or Postgres as the brief specifies.
4. Whether the brief document itself should be amended with the design-phase
   decisions in §2 above, or left as the original spec.
