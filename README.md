# structured-corner-v2

BGS Corner General Trading LLC — Dubai. A fragrance-only UAE storefront:
house-blended attars, ouds, EDP sprays and bakhoor.

**Status: design phase.** There is no application code in this repository yet,
and that is deliberate. What follows is what has been decided, so that when
code arrives it arrives already pointed somewhere.

Source specification: the BGS Corner ecommerce build brief. Section numbers
below (§4, §6.1, §15…) refer to it.

---

## Working agreement

Four rules govern how this repository is worked on. They are listed first
because they constrain everything after them.

1. **Nothing is pushed without consent.** Work is committed locally and stays
   there until the owner says it may go to the remote. This repository is
   public; a push is the step that cannot be quietly undone.
2. **No information is pulled from other websites without consent.** No
   competitor research, no reference material, no fetching. If a question
   needs an outside source, it gets asked first.
3. **No database or catalogue is imported from anywhere else.** The workbook
   catalogue, the Firestore data and the seed products in the sibling repos
   stay in the sibling repos. A design-phase repository carries decisions, not
   inherited data nobody has re-checked.
4. **Nothing is invented to fill a gap.** No placeholder statistics, no
   fictional products, no turnaround promises. Earlier prototypes in this
   family shipped invented bottles at invented prices; none of that comes
   here. Where a real figure is missing, the space stays empty until someone
   supplies it.

---

## Design direction

### Light theme

The site is **light-themed**. Every earlier BGS build defaulted to obsidian
and brass; this one does not. Light is the ground, not an alternative mode
bolted on afterwards, which means contrast, shadow and the metallics are all
designed against a pale surface from the first screen rather than inverted
from a dark one.

### A wide palette, earned from the taxonomy

The site uses a **broad range of colour**, against the single-accent
convention most fragrance houses follow. The palette is not decorative and
not arbitrary: it is driven by §4's `scent_family`, so colour carries
information. Seven families, seven identities — a bottle keeps its colour
from the collection grid, through the PDP, into the cart line and onto the
gift box preview.

Proposed, **not yet settled**:

| Scent family | Reads as |
|---|---|
| Oud & Woods | Deep resinous brown-green |
| Amber & Spice | Burnt amber |
| Musk & Clean | Cool pale slate |
| Floral Veil | Rose |
| Fresh & Citrus | Bright herbal green |
| Sweet & Gourmand | Plum |
| Reserve | Near-black with gold — the halo tier, visibly apart |

Each family ships **two stops, not one**: an *ink* dark enough to carry text
at WCAG AA against the light ground, and a *wash* for fills and washes that
never carries text. This is the honest way to have seven colours on a light
site without half of them failing a contrast check the moment someone sets a
label in them.

Colour is a product attribute, so it also gives the CSS-drawn product
stand-ins their fill — a card shows the kind of thing it sells, tinted by what
the thing smells like, with no photograph required.

---

## Merchandising rules

### Scarcity cues must be true

Low-stock messaging — "3 left" — is wanted, and it is driven by **real
inventory**, never fabricated. The rules:

- The number shown is the number in stock. It is read, not chosen.
- A threshold decides when the cue appears at all, set in admin, not in code.
- Above the threshold, nothing is shown. Silence is the default state.
- Products sold by enquiry rather than by basket show no stock cue, because
  there is no count to be honest about.

A fabricated "3 left" is a false statement to a customer about a material fact
in a purchase decision. It is also the easiest thing in the build to disprove.

### Premium products are never discounted

Products marked `margin_role: halo` (§4) are excluded from **every** path that
reduces a price: the §6.1 volume ladder, coupon codes, campaign percentages,
loyalty redemption and gift-with-purchase thresholds alike.

This is enforced **structurally, not by policy** — one predicate that every
discount surface must ask before it touches a line, so a discount mechanism
added later cannot forget the rule. A halo product does not decline a discount;
it has no arithmetic path to one.

---

## Related repositories

Read-only context. Nothing is copied out of them without consent (rule 3).

- `bgscorner-final` — the current build. Carries the brief work: the §4 scent
  taxonomy with publish validation, the halo discount guard, the §6.1 tier
  ladder and the §6.5 gift threshold.
- `bgscorner-v2` — content CMS and storefront chrome.
- Seven older static prototypes — presentation experiments, mostly variations
  on a scroll-scrubbed film hero, carrying fictional catalogues.
