# BGS Corner — front-end build prompt

Everything below is the accumulated instruction set for the BGS Corner storefront
front end. It is written to be handed to a developer or a fresh session and
executed without further context.

---

## 0. Hard rules — these override everything else

1. **Never push to a remote without explicit consent.** Commit locally and stop.
   Creating a remote repository counts as publishing.
2. **Never pull anything from another repository.** Not code, data, design, copy
   or context. `bgscorner-final`, `bgscorner-v2` and the older static prototypes
   are off limits entirely — not reference material, not to be read or surveyed.
3. **Never pull information from any website** without consent in that message.
4. **Use only these three sources for data:**
   - `BGSecommercebuildbrief.md` — catalogue §3, taxonomy §4, all commerce rules
   - `BGS Corner Sheet.xlsx` — product lineup, weights, August selling prices
   - `BGS_Perfume_Ingredients.xlsx` — EDP note profiles and barcodes
   Read the cost and profit columns **only to skip them**. Margin data must never
   reach the front end.
5. **Never invent anything to fill a gap.** No placeholder statistics, fictional
   products, invented prices, ratings or turnaround promises. A field with no
   source renders as a visible placeholder.
6. **No images anywhere.** Every image region is an outlined, labelled, empty
   box. Do not add stock photography, generated imagery, CSS-drawn product art,
   or decorative illustration.

---

## 1. What this is

A fragrance-only UAE storefront for BGS Corner General Trading LLC, Dubai.
House oud oils in 3 ml and 6 ml, Reserve oud, bakhoor and EDP sprays.
UAE-only delivery, Dubai-first with a same-day option.

**It must read as a professional ecommerce store, not a portfolio or brand site.**
Merchandising rails, search, filters, product cards with prices and add-to-bag —
not editorial layouts, full-bleed hero photography or long-form storytelling.

Front end only. No backend, no database, no persistence beyond the tab.

---

## 2. Vocabulary

The word **"attar" is not used anywhere**. Everything is **oud**:

| Never | Always |
|---|---|
| Attars | Oud Oils |
| Attar oil · 3 ml | Oud oil · 3 ml |
| House attars | House ouds |
| alcohol-free attars | alcohol-free ouds |
| mystery attar | mystery oud |
| How to apply attar | How to apply oud |

The Majlis OUD / Platinum Musk OUD line is labelled **Reserve**, so it does not
collide with the renamed oud-oil category.

---

## 3. Stack and layout of files

Static HTML, CSS and vanilla JS. No framework, no build step beyond a generator.

```
flow/
  build.py            generates all 10 pages from one shell + per-page bodies
  index.html          … generated, do not hand-edit
  assets/flow.css     single stylesheet
  assets/shop.js      all behaviour
```

- `build.py` owns the shared chrome (strip, masthead, nav, footer, tab bar) and
  every page body. **Edit `build.py`, never the generated HTML.**
- Run: `python3 build.py` then serve `flow/` on **port 4310**.
- Never run a dev server through a shell; register it in `.claude/launch.json`
  and start it through the preview tooling.

**Cache busting is mandatory.** Both `flow.css` and `shop.js` are linked with a
content-hash token (`?v=<md5[:8]>`) regenerated on every build. Without it CSS
edits silently fail to appear — this cost real debugging time.

---

## 4. Design system

### Palette — light theme, wide colour range

Light is the ground, not a mode. Colour breadth comes from the scent families.

```
--ink   #171310   --body #4a423a   --mut  #7d7266   --faint #a79c8f
--line  #e6e0d6   --hair #f0ece4   --bg   #ffffff   --alt   #faf7f2
--gold  #a8791e   --gold-d #8a5a14 --gold-l #f6efdd
--red   #b3261e   --green #2e6b3e
```

Seven scent families plus bakhoor, used as tile backgrounds with white type:

```
Oud & Woods      --f-oud     #3E4A33
Amber & Spice    --f-amber   #94480F
Musk & Clean     --f-musk    #44555F
Floral Veil      --f-floral  #9B3A5B
Fresh & Citrus   --f-fresh   #4B6B1C
Sweet & Gourmand --f-sweet   #6D2F5C
Reserve          --f-res     #171310
Bakhoor & Home   --f-bak     #6b5a3e
```

Radius `3px`. Shadow `0 1px 2px rgba(23,19,16,.05)`. Restrained, not rounded.

### Type

Body and UI: `"Helvetica Neue", Helvetica, Arial, sans-serif`, 14px/1.5.

> **Open item:** the wordmark currently renders in Times New Roman, taken from
> `BGS-box-font-style-guide.md`. That file is **not** one of the three permitted
> sources. Either authorise it or drop the rule so the wordmark falls back to the
> sans. Do not leave this undecided.

Scale: h1 34px (26–29 mobile) · h2 21px (18 mobile) · body 14px · meta 12.5px ·
eyebrow 10px uppercase, `.14em` tracking · micro 11.5px.

### Placeholder convention

Any value with no source renders as a `.slot`: bracketed, hatched, dashed
border, muted. `[ family ]`, `[ no reviews yet ]`, `[ TRN — registration
expected ~month 9 ]`. Image regions use the same treatment at box scale with a
label saying what belongs there. **A reader must be able to tell real from
pending at a glance.**

### Breakpoints

`1180px` · `1080px` · **`900px` (the main one)** · `420px`.

---

## 5. Global chrome

**Utility strip** (dark, 36px): same-day countdown left — "Order by 2:00 PM for
delivery today in Dubai · 3h 47m" with the time in gold. Right: free delivery
over AED 150, cash on delivery, Track order, العربية. Right group hides on mobile.

**Masthead:** burger (mobile only) · logo placeholder + BGS CORNER wordmark ·
category-scoped search bar with a dark submit button · Account, Wishlist, Bag
with a count badge. On mobile the search drops to its own row beneath, and
Account and Wishlist icons hide, leaving burger + wordmark + bag.

**Category nav bar** (desktop only, hidden under 900px): Oud Oils · Reserve ·
Bakhoor · EDP Sprays · Gift Sets · Discovery · Shop by Occasion ·
Corporate Gifting · and a gold "Discovery Trio · credit back" link.

**Footer:** four columns — company block with address placeholder and a
newsletter field; Shop; Help; BGS Corner. Bottom bar with the legal entity name
and the payment method list.

**Bottom tab bar** (mobile only, 5 across): Home · Shop · Gifts · Bag · Account.

---

## 6. Pages — ten, all reachable

| Page | Purpose |
|---|---|
| `index.html` | Home |
| `collection.html` | Product listing with facets |
| `product.html` | PDP, renders from `?p=<slug>` |
| `gift-box.html` | Build-a-box |
| `cart.html` | Bag |
| `checkout.html` | Guest checkout |
| `confirmed.html` | Order confirmation and invoice detail |
| `track-order.html` | Order lookup |
| `account.html` | Signed-in account |
| `corporate.html` | Corporate gifting enquiry |

### Home, in order

1. Hero **slideshow** — dashed image region, gold eyebrow, "Find your scent.",
   supporting line, two CTAs (Shop ouds / Build a gift box), **prev and next
   arrows**, five dots, and a "Slide 1 image" tag in the top-right. Slide count
   is not capped; past ~8, replace dots with a "3 / 12" counter beside the arrows.
2. Trust band — four items: free delivery over AED 150 · same-day in Dubai ·
   cash on delivery · alcohol-free ouds. Two rows of two on mobile, 44px tall,
   sub-lines hidden there.
3. Shop by category — **six** circles: Oud oils, Reserve, Bakhoor, EDP sprays,
   Gift sets, Discovery 3 ml. Six because it divides by 2 and 3.
   Each links to `collection.html?cat=<slug>`.
4. House ouds — 4 product cards, "All 12 →".
5. Discovery Trio band — AED 129, credit-back offer, gold CTA.
6. Reserve — 3 cards in a feature layout that stacks to one column on mobile.
7. Gift sets — 6 cards.
8. Shop by scent family — **8 coloured tiles on one line**, each linking to
   `collection.html?family=<slug>`.
9. Bakhoor & home — 4 cards, "All 5 →".
10. EDP sprays — 6 cards.

**No explanatory notes on the home page.** Any callout about data provenance
belongs in this document, not on screen.

### Collection

Left facet rail (250px, hidden on mobile behind a drawer) with the complete §4
taxonomy: scent family, tone, gender, format & size, occasion, longevity,
sillage, season, availability, price bands. Counts are placeholders.
Toolbar: applied-filter pills, result count, sort. Grid **4 × 3 = 12 products**
on desktop, 2 × 6 on mobile. Pagination.

Reading `?family=` or `?cat=` must: rewrite the heading, fix the breadcrumb, add
an applied pill, and tick the matching facet.

### Product

Gallery (4 thumbnails + main region, all placeholders) beside the buy column:
taxonomy chips, name, review placeholder, description placeholder, price, size
selector, longevity / sillage / batch / availability table, quantity stepper,
Add to bag, Send as a gift, the 3 ml credit-back note, delivery and payment rows.
Below: tab strip (pyramid, how to apply, ingredients, delivery, reviews), the
three-part pyramid as placeholders, and a "Complete the ritual" rail of 4.

**Every card everywhere links to its own product** via `?p=<slug>`, and the page
rebuilds name, breadcrumb, price, sizes and title from it.

### Cart

Three progress bars — free delivery at 150, gift-with-purchase at 300, and the
volume ladder toward the next rung. Four lines: two oud oils, one Reserve, one
zero-priced gift. Summary with subtotal, volume discount, delivery, VAT, total,
checkout button, payment methods, COD notice.

### Checkout

Guest, three numbered sections: contact (name, phone, email, WhatsApp opt-in
unticked), delivery (standard / same-day / scheduled), payment (card, Apple Pay,
Tabby, Tamara, COD greyed when withheld). Summary mirrors the cart.

### Account

Signed-in view. Header with name placeholder and a BGS One tier badge. Left rail
(horizontal scroll on mobile): Overview, Orders, BGS One & wallet, Referrals,
Addresses, Details & consent, Sign out. Body: three stat cards; BGS One tier
ladder Musk / Amber / Oud at 0 / 500 / 1,500 lifetime drops with perks; wallet
holding the credit-back voucher; referral code with copy link; orders empty
state; details with **two separate WhatsApp consents** — order updates and
marketing are different permissions.

---

## 7. Commerce rules the interface must express

- **Volume ladder:** 3+ items −10%, 6+ items −15%, automatic.
- **Halo exclusion:** Reserve products (`margin_role: halo`) are outside the
  ladder, coupons, campaigns and loyalty redemption. Not withheld — structurally
  unreachable. Cards carry "Never discounted"; the cart states the discount
  applied to eligible items only.
- **Free delivery** at AED 150, AED 12 below. **Same-day Dubai** +AED 25 before
  a 2:00 PM cutoff.
- **Gift with purchase** at AED 300 — a zero-priced mystery oud line.
- **Credit-back:** any 3 ml purchase issues a voucher of its own value,
  redeemable on any bottle over AED 75, 60-day expiry, single use, issued on
  delivery.
- **COD:** AED 8 fee, **withheld above AED 300**, on QR-video orders, and from
  customers with a prior refusal.
- **VAT: 5%, tax-inclusive.** Shelf prices are unchanged; the VAT component is
  extracted (`total − total ÷ 1.05`) and shown as "Includes VAT at 5%" in cart,
  checkout and on the invoice, with a TRN placeholder. Rate and on/off live in
  one pair of constants so they flip without touching the catalogue.
  Note: charging VAT before holding a TRN is not permitted in the UAE — the
  display is ready, the collection is a switch to throw later.
- **Scarcity must be true.** "3 left" shows the real count, appears only under an
  admin threshold, and shows nothing above it. Never fabricate it.

---

## 8. Behaviour (`shop.js`, no backend)

- **Quantity steppers** are real buttons, 36–38px, min 1 max 20, with a disabled
  state at 1 and a visible focus ring.
- **Live cart recalculation** on every change: line totals, subtotal, eligible
  units and subtotal (halo and gift lines excluded), tier percentage and amount,
  delivery, VAT, total, all three progress bars, and COD availability.
- **`?p=` on the PDP** rebuilds the page from a catalogue map.
- **`?family=` / `?cat=` on collection** rewrite heading, breadcrumb, pill, facet.
- **Language toggle** flips `dir="rtl"`, swaps `lang`, and translates UI chrome
  from a dictionary. Product copy is not translated. **Arabic needs a native
  speaker's review** — the brief lists it as an acceptance criterion.

---

## 9. Responsive and symmetry

Every grid must divide evenly at both widths. This was an explicit instruction:

| Block | Desktop | Mobile |
|---|---|---|
| Category circles | 6 | 2 × 3 |
| Scent families | 8, one line | 2 × 4 |
| Trust band | 4 | 2 × 2 |
| House ouds | 4 | 2 × 2 |
| Gift sets | 3 × 2 | 2 × 3 |
| Bakhoor | 4 | 2 × 2 |
| EDP sprays | 3 × 2 | 2 × 3 |
| Collection | 4 × 3 | 2 × 6 |
| Reserve | 3 | 1 column |

Rules that produced this: prefer even counts in rails; the collection carries a
twelfth "seasonal slot" card (brief §3 says twelve scents) so the grid closes;
Reserve goes full width on mobile rather than leaving a 2 + 1 orphan.

**Mobile requirements:** no horizontal scroll on any page at any width;
44px minimum hit targets; hero content sets its own height rather than being
absolutely positioned over a fixed box; hero arrows sit in the bottom corners
flanking the dots, never over the copy; **all six categories visible in the
first viewport**; grid gaps `min-width: 0` so long text wraps instead of
clipping.

---

## 10. Catalogue — what is real and where it came from

**Oud oils, 3 ml / 6 ml, AED 45 / 75** (names from the sheet, prices from §3):
Imperial Crown, Dark Leather, Royal Amber, Golden Bloom, Majestic Musk,
Musk Bloom, Belle Aura, Magnolia Veil, Parisian Muse, Velvet Spell,
Desert Breeze, + one seasonal slot.

**Reserve:** Majlis OUD 6 ml AED 650 / 12 ml AED 1,295 · Platinum Musk OUD 6 ml
AED 399. Halo.

**Bakhoor** (weights from the sheet, prices from §3): Shay 50 g · Compodi 50 g ·
Mattar 25 g · Falah 40 g · Philippine 20 g, AED 35–50.

**EDP sprays, AED 89:** Amore, Barcelona, Pride of Arabia, Vibe, Suit Up,
Be Mine, Edward the Black Prince, The Writer, Solie Frais. Only **Be Mine** has
a matched note profile and barcode (6297000197739) in the ingredients sheet; the
other nine rows are named "Image 2"–"Image 9" and cannot be matched to a product.

**Gift sets:** Discovery Trio 129 · His & Hers Duo 149 · Majlis Ritual Set 129 ·
Oud Lover's Flight 199 · Eid Royal Hamper 299 · Dubai in a Bottle 79 ·
Wedding Favours 1,099 (quote flow above 20 units).

**EDP sprays are not alcohol-free** — denatured ethyl alcohol is first on every
one. Only the oud oils carry that badge.

---

## 11. Placeholders — no source exists for these

Scent family and tone per product · ratings and review counts · product
descriptions · notes pyramid · longevity · sillage · batch numbers · stock
counts (the sheet's *Available Units* column is empty for all 30 rows) · facet
counts · corporate tier prices · TRN · customer name, phone, email · loyalty
drops, wallet balance, order count, referral code · the logo · every image.

---

## 12. Open questions

1. **Prices disagree.** The August sales tab shows Imperial Crown at AED 50 and
   Amore and Barcelona at AED 70, against the brief's 45 / 75 and 89. The brief's
   numbers are in use. Which is right?
2. **The Times New Roman wordmark** comes from an unauthorised file (§4 above).
3. **Slide count** for the hero.
4. **Arabic** needs a native speaker's pass.
5. Stock cannot be shown truthfully until *Available Units* is populated.
