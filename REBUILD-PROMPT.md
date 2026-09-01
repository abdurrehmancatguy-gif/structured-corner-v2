# BGS Corner storefront — complete rebuild prompt

Build a static, front-end-only fragrance storefront for **BGS Corner General
Trading LLC, Dubai**. No backend, no framework, no persistence beyond the tab.
It must read as a working ecommerce store, not a brand site or a portfolio.

---

## 1. Rules that override everything

1. **No images except the eight named in §9.** Every other image region is an
   outlined, labelled, empty placeholder. Never add stock photography, generated
   imagery, CSS-drawn product art or decorative illustration to fill a gap.
2. **Never invent data.** Any field with no source renders as a visible
   placeholder: a bracketed, hatched, dashed-border chip (`[ family ]`,
   `[ no reviews yet ]`). A reader must tell real from pending at a glance.
3. **The word "attar" appears nowhere.** Everything is "oud": Oud Oils, oud oil,
   house ouds, alcohol-free ouds, mystery oud, "How to apply oud". Careful with
   find-and-replace — the bakhoor is named **Mattar** and must not become "Moud".
4. Prices in AED. UAE only. English with an Arabic toggle.

---

## 2. Files and build

```
flow/
  build.py          generates all 11 pages from one shell + per-page bodies
  server.py         static server sending no-store on every response
  assets/flow.css   single stylesheet
  assets/shop.js    all behaviour
  assets/catalogue.js  emitted by build.py — the product data for the client
  assets/cat/*.jpg  eight category photographs
  *.html            generated; never hand-edit
```

- `build.py` owns the shared chrome and every page body. Edit it, not the HTML.
- It writes `assets/catalogue.js` as `window.BGS_CATALOGUE = {...}` so the
  product data has one source, used by both the server-rendered cards and the JS.
- **Cache busting is mandatory.** Link `flow.css` and `shop.js` with a
  content-hash token (`?v=<md5[:8]>`) regenerated on every build. `server.py`
  must send `Cache-Control: no-store` — the default `http.server` sends
  `Last-Modified`, and stale HTML will make correct fixes look broken.
- Serve on port 4310.

---

## 3. Design system

```
--ink #171310   --body #4a423a  --mut #7d7266   --faint #a79c8f
--line #e6e0d6  --hair #f0ece4  --bg #ffffff    --alt #faf7f2
--gold #a8791e  --gold-d #8a5a14 --gold-l #f6efdd
--red #b3261e   --green #2e6b3e
```

Eight family inks, each with a pale wash used as its tile tint:

| Family | Ink | Wash |
|---|---|---|
| Oud & Woods | `#3E4A33` | `#e9ede1` |
| Amber & Spice | `#94480F` | `#f8e9d9` |
| Musk & Clean | `#44555F` | `#e6edf1` |
| Floral Veil | `#9B3A5B` | `#f9e4ea` |
| Fresh & Citrus | `#4B6B1C` | `#edf3e0` |
| Sweet & Gourmand | `#6D2F5C` | `#f3e3ef` |
| Reserve | `#171310` | `#e6e3dd` |
| Bakhoor & Home | `#6b5a3e` | `#f0ebe0` |

Radius 3px. Body type `"Helvetica Neue", Helvetica, Arial` 14px/1.5. Display
serif `"Times New Roman", Times, serif` for the wordmark, hero headlines, the
first line of a product story and quiz questions. Breakpoints 1180 / 1080 /
**900 (the main one)** / 420.

**Every colour pairing must clear WCAG AA (4.5:1) and be verified, not assumed.**
Two bugs were only caught by measuring: gold buttons shipped at white-on-gold
3.88:1 (fix: dark ink on gold, 4.77:1), and category labels dropped to 4.13:1
once photographs sat behind them.

---

## 4. Global chrome

**Utility strip** (dark, 36px): same-day countdown "Order by 2:00 PM for delivery
today in Dubai · 3h 47m" with the time in gold. Right: free delivery over AED
150, cash on delivery, Track order, العربية. Right group hidden under 900px.

**Masthead**: burger (mobile) · logo placeholder + BGS CORNER wordmark ·
category-scoped search bar with dark submit · Account, Wishlist, Bag with count.
On mobile the search drops to its own row; Account and Wishlist hide.

**Category strip** — directly below the hero on home, below the masthead
elsewhere. Eight circular tiles, 8 across desktop / 4 across mobile:
Oud Oils · Reserve · Bakhoor · EDP Sprays · Gift Sets · Discovery ·
Shop by Occasion · Corporate Gifting. Each is a **108px circle** (74px mobile)
containing a photograph at full opacity, its family wash as a 30% tint, and a
30px white stroke icon with a drop shadow. **The label sits below the circle**,
in the family ink on the strip's `--alt` ground — that is what lets the
photograph run at full strength while contrast stays fixed at 5.75:1 or better.
Circle shadow: `0 10px 20px -7px rgba(23,19,16,.34)`, a tight contact shadow,
and a 1px inset white ring. Hover lifts 3px and deepens.

**Footer**: four columns — company block with address placeholder and newsletter
field; Shop; Help; BGS Corner. Bottom bar with legal entity and payment methods.

**Bottom tab bar** (mobile, 5 across): Home · Shop · Gifts · Bag · Account.

---

## 5. Pages — eleven, every one with a unique title

| File | `<title>` |
|---|---|
| index.html | Oud Oils, Bakhoor & EDP Sprays — Blended in Dubai |
| collection.html | Oud Oils — Alcohol-Free Perfume Oil in 3 ml and 6 ml |
| product.html | *built from the product*, e.g. "The Writer — EDP spray · 50 ml · Men" |
| gift-box.html | Build a Gift Box — Three or Six Scents, Wrapped |
| cart.html | Your Bag |
| checkout.html | Checkout — Guest Checkout, COD and Tabby |
| confirmed.html | Order Confirmed |
| track-order.html | Track Your Order |
| account.html | Your Account — BGS One, Wallet and Referrals |
| quiz.html | Test Your Scent — Five Questions, One Minute |
| corporate.html | Corporate Gifting — Co-Branded Oud and Bakhoor |

All suffixed ` | BGS Corner`.

### Home, in this exact order

1. **Hero carousel** — inset from the page edges (max-width 1320, 60px margin
   desktop / 16px mobile), bordered, rounded, 340px tall desktop / ~275 mobile.
   Five slides, each with a gold eyebrow, serif headline, one line of copy and
   two CTAs. Prev/next arrows in circles, five dots, a `1/5` counter top-right.
   Auto-advances every 7s, pauses on hover, swipeable. On mobile the arrows sit
   in the bottom corners flanking the dots — never over the copy — and the hero
   content sets its own height rather than being absolutely positioned.
   Slides: *Find your scent* (Test your scent / Shop ouds) · *Delivered today in
   Dubai* · *Discovery Trio — AED 129* · *Three scents, one wrapped box* ·
   *Never discounted*.
2. **Category strip** (§4).
3. **Trust band** — four items, 2×2 on mobile at 44px with sub-lines hidden:
   free delivery over AED 150 · same-day in Dubai · cash on delivery ·
   alcohol-free ouds.
4. **Quiz banner** — deep plum `#58234B` with a soft radial highlight and faint
   diagonal hatch. "Check what scent might be for you", eyebrow "Five questions ·
   under a minute", gold CTA to the quiz. Plum because it is the one hue the page
   does not otherwise use; the page is warm neutral, gold and near-black.
5. **House ouds** — 4 cards, "All 12 →".
6. **Discovery Trio band** — gold-tinted, AED 129, credit-back offer.
7. **Reserve** — 3 cards, feature layout, single column on mobile.
8. **Gift sets** — 6 cards.
9. **Shop by scent family** — 8 coloured tiles on one line, each with its icon,
   linking to `collection.html?family=<slug>`.
10. **Promo row** — 3 banners: Build a gift box · Discovery 3 ml · Corporate
    gifting. Full width stacked on mobile.
11. **Bakhoor & home** — 4 cards. 12. **EDP sprays** — 6 cards.

### Collection
Left facet rail 250px with the full taxonomy — scent family, tone, gender,
format & size, occasion, longevity, sillage, season, availability, price bands;
counts are placeholders. Toolbar with applied pills, result count, sort.
Grid **4×3 = 12** desktop, 2×6 mobile. Pagination.
**On mobile the rail becomes a slide-in drawer** with a Filters button carrying a
live applied-count badge, a scrim, sticky header, Escape to close and a
"Show N products" action. Without this there is no way to filter on a phone.
`?family=` / `?cat=` rewrite the heading, breadcrumb, applied pill and tick the
matching facet.

### Product
Gallery **main image first, thumbnails below** (four: three stills, one video
still), beside the buy column: taxonomy chips, name, review placeholder, the
**four-line story**, price, size selector, longevity/sillage/batch/availability
table, quantity stepper, Add to bag, Send as a gift, the 3 ml credit-back note,
delivery and payment rows. Below: tab strip, the three-part pyramid, declared
ingredients. **A persistent Add-to-bag bar** sits above the tab bar on mobile.
The page rebuilds itself from `?p=<slug>`; every card everywhere links this way.

### Cart
Three progress bars — free delivery at 150, gift-with-purchase at 300, volume
ladder toward the next rung. Four lines: two oud oils, one Reserve, one
zero-priced gift. Summary: subtotal, volume discount, delivery, VAT, total.

### Checkout
Guest. Contact (name, phone, email, **unticked** WhatsApp opt-in) · delivery
(standard / same-day / scheduled) · payment (card, Apple Pay, Tabby, Tamara, COD
greyed when withheld).

### Account
Signed-in view. Header with name placeholder and BGS One tier badge. Left rail
(horizontal scroll on mobile): Overview, Orders, BGS One & wallet, Referrals,
Addresses, Details & consent, Sign out. Body: three stat cards; the tier ladder
Musk/Amber/Oud at 0/500/1,500 lifetime drops with perks; wallet with the
credit-back voucher; referral code with copy link; orders empty state; details
with **two separate WhatsApp consents** — order updates and marketing differ.

### Quiz
Five questions, one screen each, progress bar and Back. When you'll wear it →
how it should feel → which note draws you → how far it should carry → which half
of the year. Answers map to family/tone/occasion/sillage/season, then score
against the nine real ingredient profiles (§8). Result page shows the profile as
pills, the closest product with its declared facets, barcode and match score,
the Discovery Trio recommendation, and a "WhatsApp me my profile" capture with
name, phone and an **unticked** consent box.

---

## 6. Commerce rules the interface must express

- **Volume ladder** 3+ items −10%, 6+ −15%, automatic.
- **Halo exclusion** — Reserve products sit outside the ladder, coupons,
  campaigns and loyalty redemption. Not withheld: structurally unreachable.
  Cards carry "Never discounted"; the cart states the discount applied to
  eligible items only.
- **Free delivery** at AED 150, AED 12 below. **Same-day Dubai** +AED 25 before a
  2:00 PM cutoff.
- **Gift with purchase** at AED 300 — a zero-priced mystery oud line.
- **Credit-back** — any 3 ml purchase issues a voucher of its own value,
  redeemable on any bottle over AED 75, 60-day expiry, issued on delivery.
- **COD** — AED 8 fee, withheld above AED 300, on QR-video orders, and from
  customers with a prior refusal.
- **VAT 5%, tax-inclusive.** Shelf prices unchanged; the component is extracted
  (`total − total ÷ 1.05`) and shown as "Includes VAT at 5%" in cart, checkout
  and on the invoice, with a TRN placeholder. Rate and on/off in one pair of
  constants. Note: charging VAT before holding a TRN is not permitted in the UAE.
- **Scarcity must be true** — "Only N left" shows the real count from the data,
  and only under a threshold.

---

## 7. Behaviour (`shop.js`, no backend)

- **Quantity steppers**: real buttons, 36–38px, min 1 max 20, disabled at 1,
  visible focus ring.
- **Live cart recalculation** on every change: line totals, subtotal, eligible
  units and subtotal (halo and gift lines excluded), tier % and amount, delivery,
  VAT, total, all three progress bars, COD availability.
- **`?p=`** rebuilds the PDP; **`?family=` / `?cat=`** reshape the collection.
- **Hero carousel**: arrows, dots, 7s auto-advance, hover pause, touch swipe.
- **Mobile filter drawer** with live applied count.
- **Language toggle** flips `dir="rtl"`, swaps `lang`, translates UI chrome from
  a dictionary. Product copy is not translated; the Arabic needs a native
  speaker's review.

---

## 8. Data — all of it real, from three sources

**Nine EDP sprays, AED 85 each**, from `BGS_Perfume_Product_Details.xlsx`. Each
has a barcode, gender, real stock, top/heart/base notes, a declared ingredient
list, and a **four-line story** composed from that sheet's own description and
note columns — no facts added:

| SKU | Name | Gender | Stock |
|---|---|---|---|
| 6297000197739 | Be Mine | Women | 8 |
| 6297000197777 | Vibe | Unisex | 10 |
| 6297000197814 | Pride of Arabia | Unisex | 8 |
| 6297000197784 | Suit Up | Men | 4 |
| 6297000197807 | The Writer | Men | 1 |
| 6297000197760 | Edward the Black Prince | Men | 6 |
| 6297000197753 | Amore | Women | 13 |
| 6297000197746 | Soleil Frais | Unisex | 3 |
| 6297000197791 | Barcelona | Unisex | 5 |

Example story (The Writer): *"A fragrance for stories that linger after the last
page. / Luminous lemon opens, then rose and clove spice. / Warm balsamic amber
settles in and stays. / Thoughtful, unhurried, quietly magnetic."*

**Twelve oud oils, 3 ml AED 45 / 6 ml AED 75**: Imperial Crown, Dark Leather,
Royal Amber, Golden Bloom, Majestic Musk, Musk Bloom, Belle Aura, Magnolia Veil,
Parisian Muse, Velvet Spell, Desert Breeze, + one seasonal slot.

**Reserve**: Majlis OUD 6 ml AED 650 / 12 ml AED 1,295 · Platinum Musk OUD 6 ml
AED 399. Halo.

**Bakhoor**: Shay 50 g · Compodi 50 g · Mattar 25 g · Falah 40 g · Philippine
20 g, AED 35–50.

**Gift sets**: Discovery Trio 129 · His & Hers Duo 149 · Majlis Ritual Set 129 ·
Oud Lover's Flight 199 · Eid Royal Hamper 299 · Dubai in a Bottle 79.

34 products total. **Placeholders, because no source exists**: scent family and
tone per product, ratings and review counts, longevity, sillage, batch numbers,
oud-oil and bakhoor stock counts, facet counts, corporate tier prices, TRN,
customer name/phone/email, loyalty balances, referral code, the logo.

---

## 9. The eight category photographs

Sourced from Pexels (free for commercial use). Only these eight images exist:

`oud` 7797738 · `res` 6638269 · `bak` 34470639 · `musk` 6915310 ·
`floral` 1303087 · `fresh` 7269476 · `amber` 9127154 · `sweet` 29873585

Fetch at 320×320 crop. **Reject any image showing another brand's label** — the
top results for perfume searches repeatedly return branded bottles — and note
that searching "oud" returns the musical instrument as often as the wood.

---

## 10. Responsive and symmetry

Every grid divides evenly at both widths:

| Block | Desktop | Mobile |
|---|---|---|
| Category circles | 8 | 4 × 2 |
| Scent families | 8, one line | 2 × 4 |
| Trust band | 4 | 2 × 2 |
| House ouds / Bakhoor | 4 | 2 × 2 |
| Gift sets / EDP | 3 × 2 | 2 × 3 |
| Collection | 4 × 3 | 2 × 6 |
| Reserve | 3 | 1 column |
| Promos | 3 | 1 column |

The collection carries a twelfth "seasonal slot" card so the grid closes.
**No horizontal scroll on any page at any width. 44px minimum hit targets.**

---

## 11. Deploy

The site is generated into `flow/`, not the repository root, so a
`netlify.toml` at the root must set `publish = "flow"` or every path 404s.
Assets immutable for a year (their URLs carry a hash); HTML `no-cache`.
