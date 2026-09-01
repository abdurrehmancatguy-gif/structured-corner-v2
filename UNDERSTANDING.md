# BGS Corner — project instructions and current understanding

BGS Corner General Trading LLC, Dubai. A fragrance-only UAE ecommerce store:
house-blended attars, ouds, EDP sprays and bakhoor. UAE-only delivery,
Dubai-first with a same-day option.

**This is a standalone project.** It does not continue, fork or inherit from
any earlier BGS website. Nothing is carried across — no code, no catalogue, no
design. The build brief is the only source.

**Status: design phase.** No application code exists yet, by instruction. This
file is the standing record of what has been decided and what is understood,
so the next session starts where this one stopped.

Source specification: the owner's build brief. Section numbers below
(§4, §6.1, §15…) refer to it.

---

## 1. Standing rules

These constrain everything else in this file.

1. **Never push without explicit consent.** Commit locally; leave it there.
   This repository is public, and a push is the step that cannot be quietly
   undone. Creating a remote counts as publishing too.
2. **Never pull information from other websites without consent.** No
   competitor research, no reference material, no fetching. Ask first.
3. **Never pull anything from another repository.** Not code, not data, not
   design, not copy, not context. The other BGS repositories in `~/github`
   (`bgscorner-final`, `bgscorner-v2`, and the older static prototypes) are
   off limits entirely &mdash; they are not reference material for this project and
   are not to be read, surveyed or cited. This project starts empty and stays
   that way until the owner supplies what goes in it.
4. **Never invent anything to fill a gap.** No placeholder statistics, no
   fictional products, no invented prices or turnaround promises. Where a real
   figure is missing, the space stays empty until someone supplies it.

---

## 2. Design direction

Owner decisions, layered on top of the brief.

### Light theme
The site is light-themed. Light is the ground, not a mode bolted on after —
contrast, shadow and metallics are designed against a pale surface from the
first screen rather than inverted from a dark one.

### A wide palette, earned from the taxonomy
The site uses a broad range of colour, against the single-accent convention
most fragrance houses follow. The palette is driven by §4's `scent_family`, so
colour carries information rather than decorating: seven families, seven
identities, and a bottle keeps its colour from the collection grid through the
PDP into the cart line and onto the gift-box preview.

Ground: `#FAF8F4`, a warm off-white.

Each family ships two stops: an **ink** that carries text, and a **wash** for
fills that never carries text. Measured contrast below — AA needs 4.5:1:

| Scent family | Ink | on ground | Wash | ink on wash |
|---|---|---|---|---|
| Oud & Woods | `#3E4A33` | 8.87 | `#EDEFE6` | 8.10 |
| Amber & Spice | `#94480F` | 6.20 | `#F8EADC` | 5.57 |
| Musk & Clean | `#44555F` | 7.30 | `#E9EEF1` | 6.63 |
| Floral Veil | `#9B3A5B` | 6.29 | `#F9E7EC` | 5.61 |
| Fresh & Citrus | `#4B6B1C` | 5.79 | `#EFF3E2` | 5.44 |
| Sweet & Gourmand | `#6D2F5C` | 8.95 | `#F3E6F0` | 7.86 |
| Reserve | `#26221D` | 14.90 | `#E8E4DC` | 12.46 |

Every ink passes AA on the ground *and* on its own wash, so a label may sit on
either without a per-family exception. The narrowest is Fresh & Citrus at 5.44,
which still leaves room to darken a tint later without breaking a check.

**Gold is not a text colour.** `#A07C3C` reaches 3.64 against the ground and
4.10 against Reserve ink — both short of AA. Gold is for rules, borders and
foil; the halo tier's gold is drawn, never written. A darker `#8A6A2E` passes
on the ground (4.73) but then fails on Reserve (3.15), so there is no single
gold that works as text everywhere, and pretending otherwise would put an
unreadable price on the most expensive product in the shop.

Values are measured, but **not yet approved** — the hues themselves are still
the owner's call.

### Scarcity cues must be true
Low-stock messaging ("3 left") is wanted, driven by **real inventory**:

- The number shown is the number in stock. Read, not chosen.
- A threshold decides when the cue appears, set in admin, not in code.
- Above the threshold, nothing is shown. Silence is the default.
- Quote-flow products show no cue — there is no count to be honest about.

A fabricated "3 left" is a false statement to a customer about a material fact
in a purchase decision, and the easiest claim in the build to disprove.

### Premium products are never discounted
Products marked `margin_role: halo` (§4) — Majlis OUD, Platinum Musk OUD — are
excluded from every path that reduces a price: the §6.1 volume ladder, coupon
codes, campaign percentages, loyalty redemption and the gift-with-purchase
threshold alike.

Enforced **structurally, not by policy** — one predicate every discount surface
must ask before touching a line, so a mechanism added later cannot forget it. A
halo product does not decline a discount; it has no arithmetic path to one.

---

## 3. What the brief requires

### The commercial thesis
The basket must average **AED 160+** against ~AED 50 kiosk items. Three levers
do that work: tiered bundle pricing, gifting as the primary use case, and
WhatsApp retention through GoHighLevel. Contribution is ~AED 56/order at that
AOV against ~AED 20 delivery — which is where free delivery ≥ AED 150, AED 12
below, and same-day Dubai +AED 25 come from. Margin arithmetic, not preference.

Languages: English + Arabic at launch, full RTL, hreflang'd. Currency AED, with
a VAT-ready price and invoice architecture (registration expected ~month 9).

### The stack (§2)
Next.js App Router + TypeScript + Tailwind, SSR/ISR on every indexable page.
Node/TypeScript API over **PostgreSQL** (Prisma). Vercel-class hosting, managed
Postgres, media on a Cloudinary/Mux-class CDN. Payments through hosted fields
or official SDKs only, so raw card numbers never touch the server. One repo,
modular: `catalog`, `cart`, `checkout`, `orders`, `gifting`, `loyalty`,
`content`, `admin`, `integrations`.

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
- COD defended: AED 8 fee, disabled above AED 300, on QR-video orders, and for
  customers with a prior refusal; orders enter `cod_pending` and ship only
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
- Referral, even if loyalty tiers slip: friend AED 20 off a first order ≥ 99;
  referrer credited only after the friend's delivery + 3 days.
- Faceted filters: multi-select, URL-persistent, AR + EN, taxonomy-driven.
- Scent quiz: 5 questions under 60s, consent captured unchecked by default.

### Gifting is the differentiator (§7)
Premium box, wrap and handwritten card, a free QR video message that
auto-deletes after 90 days, scheduled delivery dates, same-day Dubai gated on
the cutoff, ship-to-recipient with hidden prices, send-a-gift links for kiosk
QR cards, and a corporate gifting page that opens a GHL pipeline opportunity.

### Division of responsibility (§13)
The **store** owns products, orders, inventory, payments, vouchers and consent
capture. **GHL** owns messaging orchestration, pipelines and campaigns. No
commerce state lives only in GHL. Consent is two-way: one opt-out silences both
systems, and the store's ledger is the legal record.

### Analytics before the first ad dirham (§12)
Meta Pixel + Conversions API fed server-side from the event outbox, GA4
enhanced ecommerce, Google Ads enhanced conversions, an auto-generated Merchant
Center feed, UTM templates on owned links, and a consent-mode banner that
declines non-essential by default.

### SEO and performance are acceptance criteria, not aspirations
- SSR/ISR for every indexable route; no content behind client-only JS.
- Whitelisted single-facet URLs indexable with unique copy; all multi-facet
  combinations `noindex,follow` + canonical to base, preventing crawl explosion.
- Slug 301 history, hreflang en-AE ↔ ar-AE, schema, sitemaps, redirect manager.
- Programmatic landing pages and an editorial module, both admin-creatable.
- **Mobile on throttled 4G: LCP < 2.5s, CLS < 0.1, INP < 200ms** on home,
  collection and PDP. Hero poster ≤ 1.5MB. JS < 300KB gzipped per template.

### The admin portal is part of the build (§16)
Ten modules, role-gated, mobile-usable, because ops happens at the kiosk. The
real acceptance test: a non-technical person can add a taxonomy'd product,
receive stock with a batch, clear a COD queue, publish an occasion landing
page, generate an influencer code and read the dashboard — with no developer.

### Out of scope for launch
Subscriptions, GCC shipping, multi-currency, a native app, full Tagalog and
Spanish locales, engraving. The architecture must not preclude them.

---

## 4. Competitor reference — vperfumes.com

Studied 2026-08-29, UAE English storefront, with the owner's consent (rule 2).
The brief itself names no competitors; this one was supplied separately. Every
observation below was read off the live site.

**What they are:** a GCC fragrance *reseller* — designer and niche brands,
50+ physical stores, a marketplace with third-party sellers, running permanent
deep discounting (74–90% off with struck-through reference prices, a countdown
timer on a three-day "Dubai Super Sale"). That is the opposite of a house brand
with a halo tier. Take their mechanics; leave their strategy.

### Worth implementing

- **`/category/` and `/collection/` as separate URL spaces.** Category is the
  durable taxonomy; collection is curated and campaign-led. That is exactly
  §5's split between rule-driven collections and manual curation, and it keeps
  a seasonal campaign from polluting a permanent facet.
- **Category page shape:** short intro line under the heading, the grid, then
  long-form copy and an FAQ block beneath it. That is §14.5's programmatic
  landing page and §14.3's FAQ schema, already proven on a UAE fragrance term.
- **A result count** — "209 items in Bakhoor" — next to the filter control.
- **A delivery promise on the PDP, not just at checkout.** They show
  "Deliver to UAE, Abu Dhabi, AL Khatam" and "Delivered between Aug 31 – Sep 3"
  against a chosen delivery type. §9 asks for a same-day line with a countdown;
  a resolved date range is the same idea and reads as more concrete.
- **A delivery-speed badge on the product card** — theirs reads "Free 2-Hour
  Delivery" on eligible items. This is what §4's `same_day_eligible` should
  look like in the grid, and what §8.1's "Ready today" filter should match.
- **"Notify me" replacing Add to Cart when out of stock.** A dead button is a
  lost customer; this is also an `optin.captured` event (§13) and a reason to
  message someone later.
- **Two distinct recommendation rails** — "Frequently Purchased" and
  "Customers who bought this item also bought" — kept separate rather than
  merged. §9's "Complete the ritual" is our version, but the lesson is that one
  rail can be behavioural and another editorial.
- **PDP section set:** Key Specifications, About, How to use, Reviews, FAQ.
  Close to §9's accordions; "How to use" earns its place for attar and bakhoor,
  which many buyers genuinely do not know how to use.
- **A trust strip repeated in the footer**, each claim with its qualifier:
  free shipping over AED 200, COD, money-back within 7 days, 24/7 support.

### Confirms the brief

- Their PDP carries **GENDER, SILLAGE and SEASON** as structured attributes —
  three of §4's axes, on a competitor at scale. The taxonomy is not exotic.
- Their COD is qualified **"for selected products only"** — the same defence
  §10.3 requires, stated plainly to the customer rather than hidden.
- Free-delivery threshold at AED 200 against the brief's AED 150.

### Deliberately not taking

- **The discount model.** Struck-through prices at 74–90% off, permanently, on
  most of the catalogue. It trains a customer never to pay the reference price,
  and it is structurally incompatible with a halo tier that is never discounted.
- **The marketplace layer** — "Sold by", seller ratings, seller registration.
- **"Load More" pagination**, which needs care to stay crawlable.
- **The app-download push.** A native app is out of scope for launch.

### Where we can beat them

Their PDP ships **only `Organization` JSON-LD** — no Product schema, no
`offers`, no `aggregateRating`, no Review markup, despite showing a rating on
the page. §14.3 requires all of it. Rich results on product queries are
available to whoever asks for them, and they are not asking.

### Not verified

Their filter drawer would not open under automation, so the facet list is
unknown. Cart, checkout and COD rules were not exercised — that would mean
placing an order on a live commercial site.

---

## 5. Build order

The brief's own sequence (§2.1), which nothing so far gives reason to change:

1. Data model, catalogue and taxonomy (§3–4)
2. Storefront core — collections, PDP, search and filters
3. Cart, checkout, payments, couriers
4. Bundles, gifting, quiz, vouchers
5. Admin portal (§16)
6. SEO and performance hardening (§14–15)
7. GHL and analytics integration (§12–13)
8. QA against the acceptance checklist (§17)

---

## 6. Open questions

1. The seven family hues need real values, contrast-checked on the light ground.
2. The §3 catalogue needs real product data from the owner — names, variants,
   prices and taxonomy values. Nothing is invented to stand in (rule 4).
3. Payment provider: Stripe, or Telr/PayTabs. Plus which BNPL — Tabby, Tamara,
   or both.
4. Courier: the brief names Jeebly plus one backup, which is unnamed.
5. Whether the brief document itself should be amended with the design-phase
   decisions in §2 above, or left as the original spec.
