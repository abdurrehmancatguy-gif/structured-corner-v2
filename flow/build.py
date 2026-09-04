# BGS Corner storefront — built ONLY from:
#   A) BGSecommercebuildbrief.md      (catalogue §3, taxonomy §4, rules §5-§11)
#   B) BGS Corner Sheet.xlsx          (product lineup, weights, August selling prices)
#   C) BGS_Perfume_Ingredients.xlsx   (EDP note profiles + barcodes)
# No images. No data from any other source. Unsourced fields render as placeholders.
import pathlib, hashlib, json, html

def esc(t):
    """Escape admin-authored free text so a typed & or < cannot break markup."""
    return html.escape(str(t), quote=True)
CSSV = hashlib.md5(pathlib.Path("assets/flow.css").read_bytes()).hexdigest()[:8]

def I(d, w=18, s=1.6):
    return '<svg width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="%s" stroke-linecap="round">%s</svg>' % (w, w, s, d)
P = {
 "search":'<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
 "user":'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
 "heart":'<path d="M12 20s-7-4.5-7-9.5A4 4 0 0 1 12 8a4 4 0 0 1 7 2.5C19 15.5 12 20 12 20z"/>',
 "bag":'<path d="M6 8h12l-1.2 12H7.2z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
 "menu":'<path d="M4 7h16M4 12h16M4 17h16"/>',
 "truck":'<path d="M3 7h11v9H3z"/><path d="M14 10h4l3 3v3h-7z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
 "clock":'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
 "cash":'<rect x="3" y="7" width="18" height="11" rx="1"/><circle cx="12" cy="12.5" r="2.5"/>',
 "leaf":'<path d="M20 4C10 4 4 9 4 16c0 2 1 4 1 4s6-1 10-5 5-11 5-11z"/><path d="M5 20L14 11"/>',
 "chev":'<path d="M6 9l6 6 6-6"/>', "filter":'<path d="M3 6h18M7 12h10M11 18h2"/>',
 "c_oil":'<rect x="9" y="2.5" width="6" height="3.5" rx="1"/><path d="M8 9.5C8 7.5 9.5 6 9.5 6h5S16 7.5 16 9.5V19a2.5 2.5 0 0 1-2.5 2.5h-3A2.5 2.5 0 0 1 8 19z"/><path d="M8 14h8"/>',
 "c_res":'<path d="M4 8l4 3 4-6 4 6 4-3-2 11H6z"/><path d="M6 19h12"/>',
 "c_bak":'<path d="M6 14h12l-1.5 6h-9z"/><path d="M4 14h16"/><path d="M11 10c0-2 2-3 2-5 2 2 2 3.5 1.5 5"/>',
 "c_edp":'<rect x="9" y="8" width="6" height="13" rx="1.5"/><path d="M10.5 8V5h3v3M15 4h2M15 6.5h2M17 4v2.5"/>',
 "c_gift":'<rect x="3.5" y="9" width="17" height="11" rx="1"/><path d="M3.5 13h17M12 9v11"/><path d="M12 9S9.5 4 7.5 5.5 10 9 12 9zm0 0s2.5-5 4.5-3.5S14 9 12 9z"/>',
 "c_disc":'<circle cx="12" cy="12" r="8.5"/><path d="M14.5 9.5L10 11l-1.5 4.5L13 14z"/>',
 "c_occ":'<rect x="3.5" y="5" width="17" height="16" rx="1.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/>',
 "c_corp":'<rect x="3" y="8" width="18" height="12" rx="1.5"/><path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M3 13h18"/>', "left":'<path d="M15 5l-7 7 7 7"/>', "right":'<path d="M9 5l7 7-7 7"/>', "check":'<path d="M5 12l5 5L19 7"/>',
}
def sv(k, w=18, s=1.6): return I(P[k], w, s)

# ---------------------------------------------------------------- content
# Everything editable lives in content/ as collections of documents, shaped so
# a Firestore collection can replace the file later without touching anything
# downstream: load_content() is the only thing that knows where they come from.
CONTENT_DIR = pathlib.Path("content")

def load_content():
    out = {}
    for f in ("settings", "navigation", "copy", "home", "products"):
        out[f] = json.loads((CONTENT_DIR / (f + ".json")).read_text())
    return out

C = load_content()
SETTINGS = C["settings"]["store"]
SEO = C["settings"].get("seo", {})
SITE_URL = (C["settings"].get("site_url") or "").rstrip("/")

# One-line description per page for <meta name=description> and OG.
PAGE_DESC = {
    "index.html": "Alcohol-free oud oils, bakhoor and EDP sprays, blended in Dubai. Same-day delivery in Dubai, free over AED 150.",
    "collection.html": "Shop BGS Corner: oud oils, Reserve, bakhoor, EDP sprays and gift sets. Filter by category, price and gender.",
    "product.html": "House-blended, alcohol-free fragrance from BGS Corner, Dubai. Oud oils, Reserve, bakhoor and EDP sprays.",
    "gift-box.html": "Build a gift box of three or six house scents, wrapped, with a handwritten card. BGS Corner, Dubai.",
    "cart.html": "Your BGS Corner bag.",
    "checkout.html": "Guest checkout with card, Apple Pay, Tabby, Tamara or cash on delivery. BGS Corner, Dubai.",
    "confirmed.html": "Order confirmed. BGS Corner, Dubai.",
    "track-order.html": "Track your BGS Corner order by number or phone.",
    "account.html": "Your BGS Corner account: BGS One rewards, wallet and referrals.",
    "quiz.html": "Answer five questions and we will point you at the closest blend we make.",
    "corporate.html": "Co-branded oud and bakhoor for corporate gifting. Above 20 units becomes a quote. BGS Corner, Dubai.",
}
NAVC     = C["navigation"]
COPY     = C["copy"]
HOME     = C["home"]
PRODUCTS = C["products"]

def published(cat=None):
    """Documents in display order, optionally one category."""
    rows = [dict(p, id=k) for k, p in PRODUCTS.items() if p.get("published", True)]
    if cat:
        rows = [r for r in rows if r.get("category") == cat]
    return sorted(rows, key=lambda r: r.get("order") or 0)

ON = ' class="on"'
def A(l, h, on):
    return '<a href="%s"%s>%s</a>' % (h, ON if l == on else "", l)
def slug(t):
    import re as _r
    t = t.replace("&amp;","and").replace("&middot;"," ").replace("&rsquo;","")
    return _r.sub(r"[^a-z0-9]+","-",t.lower()).strip("-")

def slot(label):
    """A field with no value in any of the three sources."""
    return '<span class="slot">%s</span>' % label

NAV = [(n["label"], n["href"]) for n in NAVC["main"]]
TABS = [(n["label"], n["href"]) for n in NAVC["tabs"]]

CATS = [(c["label"], c["href"], c["swatch"], c["photo"]) for c in NAVC["categories"]]
def catstrip():
    return ('<div class="catstrip"><div class="wrap"><div class="cs">' + "".join(
        '<a class="c-{3}" href="{0}"><span class="circle">{1}</span><span>{2}</span></a>'.format(h, sv(ic, 30, 1.5), n, k)
        for n, h, ic, k in CATS) + '</div></div></div>')

def shell(title, body, nav_on="", tab="Home", strip_here=True, page="", desc="", canon=""):
    strip = catstrip()
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s | BGS Corner</title>
<meta name="description" content="%(desc)s">
<link rel="canonical" href="%(canon)s">
<meta property="og:type" content="website">
<meta property="og:title" content="%(title)s | BGS Corner">
<meta property="og:description" content="%(desc)s">
<meta property="og:image" content="%(ogimg)s">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="assets/flow.css?v=%(cssv)s"></head><body class="%(page)s">
<div class="strip"><div class="wrap">
  <span>%(clock)s Order by 2:00 PM for delivery today in Dubai &middot; <b>3h 47m</b></span>
  <span class="r"><span>Free UAE delivery over AED 150</span><span>Cash on delivery</span><a href="track-order.html">Track order</a><a href="#" data-langtoggle>العربية</a></span>
</div></div>
<div class="mast"><div class="wrap">
  <a class="logo" href="index.html"><span class="logomark">%(slotlogo)s</span><span class="wm">BGS CORNER</span></a>
  <form class="search" action="collection.html" method="get" role="search">
    <input name="q" aria-label="Search products" placeholder="Search ouds, oud, bakhoor&hellip;"><button type="submit" class="go" aria-label="Search">%(search)s</button></form>
  <div class="acts">
    <a class="act" href="account.html">%(user)s<span>Account</span></a>
    <a class="act" href="account.html">%(heart)s<span>Wishlist</span></a>
    <a class="act" href="cart.html">%(bag)s<span>Bag</span><i class="n">4</i></a>
  </div>
</div>
<div class="msearch"><form class="search" action="collection.html" method="get" role="search"><input name="q" aria-label="Search products" placeholder="Search ouds, oud, bakhoor&hellip;"><button type="submit" class="go" aria-label="Search">%(search)s</button></form></div></div>
%(strip)s
%(body)s
<footer><div class="wrap"><div class="cols">
  <div><div class="wm" style="color:#fff;font-size:20px;margin-bottom:14px">BGS CORNER</div>
    <p>BGS Corner General Trading LLC &middot; Dubai, UAE</p>
    <p>%(addr)s</p><div class="nl"><span class="field">Your email</span><span class="btn">Join</span></div></div>
  <div><h5>Shop</h5><a href="collection.html">Oud Oils</a><a href="collection.html">Oud</a><a href="collection.html">Bakhoor</a><a href="collection.html">EDP sprays</a><a href="gift-box.html">Gift sets</a></div>
  <div><h5>Help</h5><a href="product.html?p=royal-amber&amp;tab=delivery">Delivery &amp; returns</a><a href="product.html?p=royal-amber&amp;tab=apply">How to apply oud</a><a href="track-order.html">Track your order</a><span class="soon">FAQ</span></div>
  <div><h5>BGS Corner</h5><a href="account.html">Your account</a><span class="soon">Our story</span><a href="corporate.html">Corporate gifting</a><a href="corporate.html">Wholesale</a></div>
</div><div class="bot"><span>&copy; 2026 BGS Corner General Trading LLC</span>
<span>Cards &middot; Apple Pay &middot; Tabby &middot; Tamara &middot; Cash on delivery</span></div></div></footer>
<div class="tabbar">%(tabs)s</div>
<script src="assets/catalogue.js?v=%(cssv)s"></script>
<script src="assets/shop.js?v=%(cssv)s"></script></body></html>
""" % dict(title=title, body=body, cssv=CSSV, page=page,
   desc=esc(desc), canon=esc(canon),
   ogimg=esc((SITE_URL + "/" + SEO.get("og_image", "") ) if SITE_URL else SEO.get("og_image", "")),
   strip=(strip if strip_here else ""), tabs="".join(A(l,h,tab) for l,h in TABS),
   clock=sv("clock",13,2), menu=sv("menu",22), chev=sv("chev",14,2), search=sv("search",17),
   user=sv("user"), heart=sv("heart"), bag=sv("bag"),
   slotlogo=slot("logo"), addr=slot("address, hours, phone"))

# ---------------------------------------------------------------- DATA
# names + sizes: BGS Corner Sheet.xlsx "OUD & Bakhoor Stock"; prices: brief §3
ATTARS = ["Imperial Crown","Dark Leather","Royal Amber","Golden Bloom","Majestic Musk",
          "Musk Bloom","Belle Aura","Magnolia Veil","Parisian Muse","Velvet Spell","Desert Breeze","Seasonal slot"]
OUD = [("Majlis OUD","6 ml","650"),("Majlis OUD","12 ml","1,295"),("Platinum Musk OUD","6 ml","399")]
BAKHOOR = [("Shay","50 g","50"),("Compodi","50 g","50"),("Mattar","25 g","35"),
           ("Falah","40 g","50"),("Philippine","20 g","35")]
# EDP names: brief §3. Notes + barcode: BGS_Perfume_Ingredients.xlsx (only "Be Mine" is named there)
EDP = json.loads(pathlib.Path('edp_data.json').read_text())
SETS = [("Discovery Trio","3 &times; 3 ml","129"),("His &amp; Hers Duo","2 &times; 6 ml","149"),
        ("Majlis Ritual Set","6 ml + bakhoor","129"),("Oud Lover&rsquo;s Flight","3 &times; 6 ml","199"),
        ("Eid Royal Hamper","2 &times; 6 ml + EDP + bakhoor","299"),("Dubai in a Bottle","3 ml + mini bakhoor","79")]

def card(name, meta, price, sizes=None, halo=False, notes=None, barcode=None, low=None,
         pid=None, images=None):
    key = pid or slug(name)
    b = '<span class="badge res">Reserve</span>' if halo else ''
    if low: b = '<span class="badge low">%s left</span>' % low
    sz = ''
    if sizes:
        sel = 0
        for i, ss in enumerate(sizes):
            if ss.replace("&middot;", "·").rstrip().endswith("AED %s" % price):
                sel = i; break
        sz = '<div class="sizes">' + "".join(
            '<button type="button"%s data-size="%s">%s</button>' % (' class="on"' if i == sel else "", s, s)
            for i, s in enumerate(sizes)) + '</div>'
    nt = '<span class="notes">%s</span>' % notes if notes else ''
    hl = '<span class="norm">Never discounted</span>' if halo else ''
    heart = ('<button type="button" class="heart" data-wish="%s" aria-pressed="false" '
             'aria-label="Save %s to wishlist">%s</button>'
             % (key, esc(name), sv("heart", 15)))
    return """<a class="p" href="product.html?p=%s">
  <div class="ph">%s%s%s</div>
  <div class="b"><span class="meta">%s</span><span class="nm">%s</span>%s
  %s<div class="pr"><b>AED %s</b></div>%s
  <span class="btn sm solid" style="margin-top:4px">Add to bag</span></div></a>""" % (
    key, ph_img(images, name), b, heart, meta, esc(name), nt, sz, price, hl)

def ph_img(images, alt, card_size=True):
    """A real photograph if the product has one, the placeholder if not.

       Two frames are emitted when the product has them: the close-up, and the
       shot with the box underneath it. CSS cross-fades to the second on hover,
       so the card turns into the boxed view. Products with only one shot get
       one image and simply do not swap."""
    if not images:
        return '<span class="none">Product image</span>'
    a = alt.replace('"', "&quot;")
    def src(n):
        return n.replace(".jpg", "-card.jpg") if card_size else n
    out = ('<img class="ph-a" src="assets/img/%s" alt="%s" loading="lazy" '
           'decoding="async" width="520" height="520">' % (src(images[0]), a))
    if len(images) > 1:
        out += ('<img class="ph-b" src="assets/img/%s" alt="" aria-hidden="true" '
                'loading="lazy" decoding="async" width="520" height="520">'
                % src(images[1]))
    return out

def money(n):
    """Prices carry a thousands separator: AED 1,295 not AED 1295.
       A cleared field (None / "") coerces to 0 rather than crashing the build."""
    try:
        return "{:,}".format(int(str(n).replace(",", "")))
    except (TypeError, ValueError):
        return "0"

def _meta(pr):
    """The one place a product's meta line is composed, so the admin can change
       a name, size or gender and every card follows."""
    c = pr["category"]
    if c == "edp":       return "EDP spray &middot; %s &middot; %s" % (pr.get("size","50 ml"), pr.get("gender",""))
    if c == "oud-oils":  return "Oud oil &middot; " + " / ".join(z["label"] for z in pr.get("sizes", []))
    if c == "reserve":   return "Reserve &middot; " + (pr.get("sizes") or [{"label":""}])[0]["label"]
    if c == "bakhoor":   return "Bakhoor &middot; %s" % pr.get("size","")
    if c == "gift-sets": return "Gift set &middot; %s" % pr.get("contents","")
    return ""

def _cards(cat, n=None):
    out = []
    for pr in published(cat)[:n]:
        sizes = ["%s &middot; AED %s" % (z["label"], money(z["price"])) for z in pr.get("sizes", [])] or None
        stock = pr.get("stock")
        notes = None
        if pr.get("top") or pr.get("heart"):
            notes = " &middot; ".join(x for x in (pr.get("top"), pr.get("heart")) if x)
        out.append(card(pr["name"], _meta(pr), money(pr["price"]), sizes=sizes, pid=pr["id"],
                        images=pr.get("images"),
                        halo=pr.get("never_discount", False), notes=notes,
                        barcode=pr.get("barcode") or None,
                        low=(stock if isinstance(stock, int) and stock <= 5 else None)))
    return "".join(out)

def oudoil_cards(n=None):  return _cards("oud-oils", n)
def reserve_cards(n=None): return _cards("reserve", n)
def bakhoor_cards(n=None): return _cards("bakhoor", n)
def edp_cards(n=None):     return _cards("edp", n)
def set_cards(n=None):     return _cards("gift-sets", n)


def usp_strip():
    """The four promises under the hero, from content/copy.json."""
    return "".join(
        '<div>%s<div><b>%s</b><span>%s</span></div></div>'
        % (sv(u.get("icon", "leaf"), 20), u["title"], u["sub"])
        for u in COPY["usp"])

def hero_slides():
    """Each slide is a document: eyebrow, headline, body and up to two CTAs.
       A newline in the headline becomes a line break, so the admin can control
       where it wraps without knowing any HTML."""
    out = []
    for i, sl in enumerate(HOME["hero_slides"]):
        cta = ""
        if sl.get("primary"):
            cta += '<a class="btn gold" href="%s">%s</a>' % (esc(sl["primary"]["href"]), esc(sl["primary"]["label"]))
        if sl.get("secondary"):
            cta += '<a class="btn ghost" href="%s">%s</a>' % (esc(sl["secondary"]["href"]), esc(sl["secondary"]["label"]))
        out.append(
            '<div class="over slide%s" data-slide><div class="wrap"><div class="box">'
            '<span class="eyebrow gold">%s</span>'
            '<h1>%s</h1>'
            '<p>%s</p>'
            '<div style="display:flex;gap:10px;flex-wrap:wrap">%s</div>'
            '</div></div></div>'
            % (" on" if i == 0 else "", esc(sl.get("eyebrow", "")),
               esc(sl.get("headline", "")).replace("\n", "<br>"), esc(sl.get("body", "")), cta))
    return "".join(out)

def hero_dots():
    return "".join('<i%s data-dot="%d"></i>' % (' class="on"' if i == 0 else "", i)
                   for i in range(len(HOME["hero_slides"])))

# ---------------------------------------------------------------- HOME
home = """
<div class="hero" data-carousel>
  <div class="heroimg"><img src="assets/img/banner-1.jpg" alt="" fetchpriority="high" decoding="async" width="2400" height="790"><span class="none corner"><b data-slideno>1</b>/%(hero_n)s</span></div>
  %(hero)s
  <button class="arrow prev" data-prev aria-label="Previous slide">%(prev)s</button>
  <button class="arrow next" data-next aria-label="Next slide">%(next)s</button>
  <div class="dots" data-dots>%(hero_dots)s</div>
</div>

%(catstrip)s
<div class="usp">
  %(usp)s
</div>

<section style="padding-top:26px;padding-bottom:0"><div class="wrap">
  <div class="quizband">
    <div>
      <span class="eyebrow gold">%(qb_eyebrow)s</span>
      <h3>%(qb_heading)s</h3>
      <p>%(qb_body)s</p>
    </div>
    <a class="btn gold" href="%(qb_href)s">%(qb_cta)s</a>
  </div>
</div></section>

<section class="alt"><div class="wrap">
  <div class="sec-h"><h2>House ouds</h2><a href="collection.html">All 12 &rarr;</a></div>
  <div class="grid g4">%(attars)s</div>
</div></section>

<section><div class="wrap"><div class="band">
  <div><span class="eyebrow gold-d">Start here</span>
    <h3>Discovery Trio, AED 129</h3>
    <p>Three 3 ml ouds. Whatever you spend comes back as a single-use voucher on any bottle over AED 75, valid 60 days.</p></div>
  <a class="btn gold" href="gift-box.html">Choose three</a>
</div></div></section>

<section><div class="wrap">
  <div class="sec-h"><h2>Reserve</h2><a href="collection.html">All oud &rarr;</a></div>
  <div class="grid feat">%(oud)s</div>
</div></section>

<section class="alt"><div class="wrap">
  <div class="sec-h"><h2>Gift sets</h2><a href="gift-box.html">All sets &rarr;</a></div>
  <div class="grid g3">%(sets)s</div>
</div></section>

<section><div class="wrap">
  <div class="sec-h"><h2>Shop by scent family</h2></div>
  <div class="fam">
    <a href="collection.html?family=oud-and-woods" style="background:var(--f-oud)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20c4-2 6-6 6-10M8 20c3-2 5-5 6-9M13 20c2-2 4-5 5-8"/><circle cx="17" cy="6" r="2.5"/></svg><b>Oud &amp; Woods</b><span>%(ct)s</span></a>
    <a href="collection.html?family=amber-and-spice" style="background:var(--f-amber)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l2.2 4.6L19 8.3l-3.5 3.4.9 4.9-4.4-2.4-4.4 2.4.9-4.9L5 8.3l4.8-.7z"/></svg><b>Amber &amp; Spice</b><span>%(ct)s</span></a>
    <a href="collection.html?family=musk-and-clean" style="background:var(--f-musk)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3s6 6.5 6 10.5A6 6 0 0 1 6 13.5C6 9.5 12 3 12 3z"/></svg><b>Musk &amp; Clean</b><span>%(ct)s</span></a>
    <a href="collection.html?family=floral-veil" style="background:var(--f-floral)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2.5"/><path d="M12 3a3.2 3.2 0 0 1 0 6.4M12 21a3.2 3.2 0 0 0 0-6.4M3 12a3.2 3.2 0 0 1 6.4 0M21 12a3.2 3.2 0 0 0-6.4 0"/></svg><b>Floral Veil</b><span>%(ct)s</span></a>
    <a href="collection.html?family=fresh-and-citrus" style="background:var(--f-fresh)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17M3.5 12h17M6 6l12 12M18 6L6 18"/></svg><b>Fresh &amp; Citrus</b><span>%(ct)s</span></a>
    <a href="collection.html?family=sweet-and-gourmand" style="background:var(--f-sweet)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 21V10a5 5 0 0 1 10 0v11z"/><path d="M9 10V6a3 3 0 0 1 6 0v4"/></svg><b>Sweet &amp; Gourmand</b><span>%(ct)s</span></a>
    <a href="collection.html?family=reserve" style="background:var(--f-res)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 8l4 3 4-6 4 6 4-3-2 11H6z"/></svg><b>Reserve</b><span>%(ct)s</span></a>
    <a href="collection.html?family=bakhoor-and-home" style="background:var(--f-bak)"><svg class="fic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M6 14h12l-1.5 6h-9z"/><path d="M4 14h16"/><path d="M11 10c0-2 2-3 2-5 2 2 2 3.5 1.5 5"/></svg><b>Bakhoor &amp; Home</b><span>%(ct)s</span></a>
  </div>
</div></section>

<section style="padding-top:26px"><div class="wrap">
  <div class="grid g3 promos">
    <a class="promo" href="gift-box.html"><span class="none">Banner</span><div><b>Build a gift box</b><span>Three or six scents, wrapped</span></div></a>
    <a class="promo" href="collection.html?cat=discovery"><span class="none">Banner</span><div><b>Discovery 3 ml</b><span>Credit back on your first bottle</span></div></a>
    <a class="promo" href="corporate.html"><span class="none">Banner</span><div><b>Corporate gifting</b><span>Quote above 20 units</span></div></a>
  </div>
</div></section>

<section class="alt"><div class="wrap">
  <div class="sec-h"><h2>Bakhoor &amp; home</h2><a href="collection.html">All 5 &rarr;</a></div>
  <div class="grid g4">%(bakhoor)s</div>
</div></section>

<section><div class="wrap">
  <div class="sec-h"><h2>EDP sprays</h2><a href="collection.html">All 9 &rarr;</a></div>
  <div class="grid g3">%(edp)s</div>
</div></section>
""" % dict(catstrip=catstrip(), usp=usp_strip(),
           hero=hero_slides(), hero_dots=hero_dots(), hero_n=len(HOME["hero_slides"]),
           qb_eyebrow=COPY["quiz_banner"]["eyebrow"], qb_heading=COPY["quiz_banner"]["heading"],
           qb_body=COPY["quiz_banner"]["body"], qb_cta=COPY["quiz_banner"]["cta_label"],
           qb_href=COPY["quiz_banner"]["cta_href"],
           prev=sv("left",22,2), next=sv("right",22,2),
           attars=oudoil_cards(4), oud=reserve_cards(), sets=set_cards(),
           bakhoor=bakhoor_cards(4), edp=edp_cards(6), ct=slot("count"))

# ---------------------------------------------------------------- COLLECTION
# Only facets the content layer actually carries: category and price for all
# products, gender for the EDP sprays. Family/tone/occasion/season are in the
# brief taxonomy but have no per-product value in any source, so they are not
# offered as controls that would do nothing.
FACETS_LIVE = [
    ("Category", "cat", [("Oud oils", "oud-oils"), ("Reserve", "reserve"),
                         ("Bakhoor", "bakhoor"), ("EDP sprays", "edp"),
                         ("Gift sets", "gift-sets")]),
    ("Price", "price", [("Under AED 50", "0-49"), ("AED 50-100", "50-100"),
                        ("AED 100-200", "100-200"), ("AED 200+", "200-999999")]),
    ("Gender", "gender", [("Him", "Him"), ("Her", "Her"), ("Unisex", "Unisex")]),
]

def facet_live(title, key, rows):
    return '<div class="fbox"><h4>%s</h4>%s</div>' % (title, "".join(
        '<label><input type="checkbox" data-facet="%s" value="%s">%s</label>' % (key, val, lbl)
        for lbl, val in rows))

collection = """
<section><div class="wrap">
  <span class="eyebrow" data-crumb>Home / All products</span>
  <div class="sec-h" style="margin-top:10px"><div>
    <h2 style="font-size:26px" data-title>All products</h2>
    <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0;max-width:70ch" data-intro>Every blend in the shop: oud oils, Reserve, bakhoor, EDP sprays and gift sets.</p></div></div>
  <div class="plp">
    <div class="side" data-filters>
      <div class="drawerhead"><b>Filters</b><button type="button" class="closex" data-closefilters aria-label="Close filters">&times;</button></div>
      <div class="toolbar" style="border:0;padding:0;margin-bottom:6px"><b style="font-size:13px">Filters</b><button type="button" class="linkbtn" data-clearall>Clear all</button></div>
      %(facets)s
      <div class="draweractions"><button type="button" class="btn solid block" data-closefilters>Show <span data-count>34</span> products</button></div>
    </div>
    <div class="scrim" data-closefilters></div>
    <div>
      <div class="toolbar">
        <button type="button" class="filterbtn" data-openfilters>%(filt)s Filters <i class="fcount" data-fcount hidden>0</i></button>
        <div class="pills" data-pills></div>
        <div style="display:flex;gap:12px;align-items:center">
          <span style="font-size:13px;color:var(--mut)"><span data-count>34</span> products</span>
          <label class="sel"><span class="none-visual">Sort</span>
            <select data-sort aria-label="Sort products">
              <option value="featured">Sort: Featured</option>
              <option value="price-asc">Price: low to high</option>
              <option value="price-desc">Price: high to low</option>
              <option value="name">Name: A to Z</option>
            </select>%(chev)s</label></div>
      </div>
      <div class="grid g4" data-grid></div>
      <div class="emptystate" data-empty hidden>
        <b>Nothing matches those filters.</b>
        <p style="color:var(--mut);font-size:13.5px;margin:6px 0 14px">Try removing one, or clear them all.</p>
        <button type="button" class="btn ghost" data-clearall>Clear all filters</button>
      </div>
    </div>
  </div>
</div></section>
""" % dict(facets="".join(facet_live(t, k, r) for t, k, r in FACETS_LIVE),
           chev=sv("chev", 13, 2), filt=sv("filter", 15, 1.9))

# ---------------------------------------------------------------- PDP
product = """
<section><div class="wrap">
  <span class="eyebrow">Home / Oud Oils / Royal Amber</span>
  <div class="pdp" style="margin-top:18px">
    <div class="gal" data-gallery>
      <div class="galmain">
        <div class="galslide on" data-gs="0"><span class="none">Product image 1</span></div>
        <div class="galslide" data-gs="1"><span class="none">Product image 2</span></div>
        <div class="galslide" data-gs="2"><span class="none">Product image 3</span></div>
        <div class="galslide" data-gs="3"><span class="none">Video still</span></div>
        <button type="button" class="galnav prev" data-gprev aria-label="Previous image">%(gprev)s</button>
        <button type="button" class="galnav next" data-gnext aria-label="Next image">%(gnext)s</button>
        <span class="galcount"><b data-gnum>1</b>/4</span>
      </div>
      <div class="galthumbs">
        <button type="button" class="galthumb on" data-gt="0" aria-label="Image 1"><span>1</span></button>
        <button type="button" class="galthumb" data-gt="1" aria-label="Image 2"><span>2</span></button>
        <button type="button" class="galthumb" data-gt="2" aria-label="Image 3"><span>3</span></button>
        <button type="button" class="galthumb" data-gt="3" aria-label="Video"><span>Video</span></button>
      </div>
    </div>
    <div class="buy">
      <h1>Royal Amber</h1>
      <div class="pricerow">
        <span class="amt">AED 75</span>
        <span class="permeta">6 ml &middot; VAT included</span></div>
      <div class="sizeblock" data-sizeblock><span class="eyebrow">Size</span>
        <div class="sizes" style="gap:8px"><button type="button" data-size="3 ml &middot; AED 45">3 ml &middot; AED 45</button><button type="button" class="on" data-size="6 ml &middot; AED 75">6 ml &middot; AED 75</button></div></div>
      <div class="atcrow">
        <span class="stepper" data-stepper><button type="button" data-step="-1" aria-label="Decrease quantity">&minus;</button><i data-qty>1</i><button type="button" data-step="1" aria-label="Increase quantity">+</button></span>
        <a class="btn solid" style="flex-grow:1" href="cart.html">Add to bag: AED 75</a></div>
      <a class="btn block" href="gift-box.html" style="margin-bottom:12px">Send as a gift</a>

      <div class="belowbuy">
        <p class="story-slot" data-desc>%(desc)s</p>
        <div class="note">Try the 3 ml first, the AED 45 comes back as a voucher on any bottle over AED 75, issued the day it is delivered.</div>
        <div class="kv" data-specs style="margin-top:16px">
          <div><span>Longevity</span><span>%(lon)s</span></div>
          <div><span>Sillage</span><span>%(sil)s</span></div>
          <div><span>Batch number</span><span>%(bat)s</span></div>
          <div><span>Availability</span><span>%(av)s</span></div>
        </div>
        <div class="kv" style="margin-top:16px">
          <div><span>%(truck)s Delivery</span><span>Free over AED 150 &middot; same-day before 2 PM</span></div>
          <div><span>%(cash)s Payment</span><span>Card &middot; Apple Pay &middot; Tabby &middot; Tamara &middot; COD</span></div>
        </div>
      </div>
    </div>
  </div>
</div></section>
<div class="stickybuy">
  <div><b data-sbname>Royal Amber</b><span data-sbmeta>AED 75 &middot; 6 ml</span></div>
  <a class="btn solid sm" href="cart.html">Add to bag</a>
</div>
<section class="alt"><div class="wrap">
  <div class="tabs2" role="tablist">
    <button type="button" class="on" data-tab="pyramid" role="tab" aria-selected="true">Scent pyramid</button>
    <button type="button" data-tab="apply" role="tab" aria-selected="false">How to apply oud</button>
    <button type="button" data-tab="ing" role="tab" aria-selected="false">Ingredients &amp; allergens</button>
    <button type="button" data-tab="delivery" role="tab" aria-selected="false">Delivery &amp; returns</button>
    <button type="button" data-tab="reviews" role="tab" aria-selected="false">Reviews</button>
  </div>
  <div data-panel="pyramid">
    <div class="grid g3">
      <div><span class="eyebrow">Top</span><p style="margin:8px 0 0" data-note="top"></p></div>
      <div><span class="eyebrow">Heart</span><p style="margin:8px 0 0" data-note="heart"></p></div>
      <div><span class="eyebrow">Base</span><p style="margin:8px 0 0" data-note="base"></p></div>
    </div>
    <div class="note" data-pyrnote style="margin-top:20px" hidden>The scent pyramid is published for our EDP sprays. For the oud oils it is coming soon.</div>
  </div>
  <div data-panel="apply" hidden>
    <div class="grid g3">
      <div><span class="eyebrow">Where</span><p style="margin:8px 0 0">Wrists, the base of the throat, behind the ears. Warm points carry the oil.</p></div>
      <div><span class="eyebrow">How much</span><p style="margin:8px 0 0">These are oils, not sprays. One dab on each point is the dose; a 3 ml bottle lasts accordingly.</p></div>
      <div><span class="eyebrow">Do not rub</span><p style="margin:8px 0 0">Press the points together rather than rubbing, which breaks the top notes.</p></div>
    </div>
    <div class="note" style="margin-top:20px">Every blend in the shop is alcohol-free and oil based.</div>
  </div>
  <div data-panel="ing" hidden>
    <div data-ingpanel><p style="margin:0;color:var(--mut)">Full ingredient and allergen lists are published for our EDP sprays. This one is coming soon.</p></div>
  </div>
  <div data-panel="delivery" hidden>
    <div class="grid g3">
      <div><span class="eyebrow">UAE delivery</span><p style="margin:8px 0 0">Free over AED 150. AED 12 below that. UAE only.</p></div>
      <div><span class="eyebrow">Same-day Dubai</span><p style="margin:8px 0 0">AED 25, for orders placed before the 2:00 PM cutoff.</p></div>
      <div><span class="eyebrow">Returns</span><p style="margin:8px 0 0">Exchange on sealed items. Opened fragrance cannot be returned.</p></div>
    </div>
  </div>
  <div data-panel="reviews" hidden>
    <div class="emptystate" style="text-align:left;padding:20px 0">
      <b>No reviews yet.</b>
      <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0">Reviews open after the first orders are delivered. Nothing appears here that a buyer has not left.</p>
    </div>
  </div>
</div></section>
<section><div class="wrap">
  <div class="sec-h"><h2>Complete the ritual</h2><a href="collection.html">More &rarr;</a></div>
  <div class="grid g4">%(rel)s</div>
</div></section>
""" % dict(gprev=sv("left",20,2), gnext=sv("right",20,2), fam=slot("family"), tone=slot("tone"), gen=slot("gender"), rev=slot("no reviews yet"),
   desc="", lon="", sil="",
   bat="", av="",
   truck=sv("truck",16), cash=sv("cash",16), 
   rel=oudoil_cards(4))

# ---------------------------------------------------------------- GIFT BOX
giftbox = """
<section><div class="wrap">
  <span class="eyebrow">Home / Gift sets / Build a box</span>
  <div class="sec-h" style="margin-top:10px"><div><h2 style="font-size:26px">Build a gift box</h2>
  <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0">Three or six slots, filled from eligible products, leaving as one cart line with its contents itemised.</p></div></div>
  <div class="two">
    <div>
      <div class="pills" style="margin-bottom:18px"><span class="pill on">3 slots</span><span class="pill">6 slots</span></div>
      <div class="grid g3" style="margin-bottom:22px">
        <div class="p"><div class="ph"><span class="none">Slot 1</span></div><div class="b"><span class="nm">Royal Amber</span><span class="notes">6 ml &middot; tap to remove</span></div></div>
        <div class="p"><div class="ph"><span class="none">Slot 2</span></div><div class="b"><span class="nm">Majestic Musk</span><span class="notes">6 ml &middot; tap to remove</span></div></div>
        <div class="p" style="border-style:dashed"><div class="ph" style="background:var(--alt)"><span class="none">Slot 3 empty</span></div><div class="b"><span class="nm" style="color:var(--faint)">Choose a scent</span><span class="notes">Pairing hint reads from the taxonomy</span></div></div>
      </div>
      <div class="sec-h"><h2 style="font-size:17px">Add to the box</h2></div>
      <div class="grid g4">%(pick)s</div>
    </div>
    <div>
      <div class="sum">
        <div class="r"><span>2 scents</span><span>AED 150</span></div>
        <div class="r"><span>Premium box</span><span>AED 25</span></div>
        <div class="r" style="color:var(--faint)"><span>Volume discount at 3 items</span><span>&minus;10%%</span></div>
        <div class="r t"><span>Total</span><span>AED 175</span></div>
        <a class="btn solid block" href="cart.html" style="margin-top:12px">Fill 1 more slot</a>
      </div>
      <div class="sum" style="margin-top:16px;background:#fff">
        <span class="eyebrow">Gift options</span>
        <div class="kv" style="margin-top:10px">
          <div><span>Wrap &amp; handwritten card</span><span>+AED 10</span></div>
          <div><span>QR video message &middot; 60s</span><span style="color:var(--green);font-weight:600">Free</span></div>
          <div><span>Scheduled delivery date</span><span>Up to +30 days</span></div>
          <div><span>Ship to recipient &middot; hide prices</span><span>Off</span></div>
        </div>
      </div>
    </div>
  </div>
</div></section>
""" % dict(pick=oudoil_cards(4))

def stepper(qty, fixed=False):
    if fixed:
        return '<span class="stepper fixed"><i>%d</i></span>' % qty
    return ('<span class="stepper" data-stepper>'
            '<button type="button" data-step="-1" aria-label="Decrease quantity">&minus;</button>'
            '<i data-qty>%d</i>'
            '<button type="button" data-step="1" aria-label="Increase quantity">+</button></span>') % qty

def cline(name, meta, unit, qty, extra="", halo=False, gift=False):
    return """<div class="line" data-line data-unit="%s" data-halo="%s" data-gift="%s">
    <div class="im"><span class="none">Image</span></div>
    <div class="linfo"><div class="lname">%s</div>
    <div class="lmeta">%s</div>
    %s%s</div>
    <div class="lprice"><span data-lineprice>AED %s</span></div></div>""" % (
      unit, "1" if halo else "0", "1" if gift else "0", name, meta,
      stepper(qty, gift), extra, "{:,.0f}".format(unit * qty) if unit else "0")

cart = """
<section><div class="wrap">
  <div class="sec-h"><h2 style="font-size:26px">Your bag &middot; 4 items</h2><a href="collection.html">Continue shopping &rarr;</a></div>
  <div class="two">
    <div>
      <div class="sum" style="background:#fff;margin-bottom:18px">
        <div class="prog"><div class="lb"><span>Free UAE delivery over AED 150</span><b data-p1lb style="color:var(--green)">Unlocked</b></div><div class="tr"><i data-p1 style="width:100%%"></i></div></div>
        <div class="prog" style="margin-top:14px"><div class="lb"><span>Free mystery oud over AED 300</span><b data-p2lb style="color:var(--green)">Unlocked</b></div><div class="tr"><i data-p2 style="width:100%%"></i></div></div>
        <div class="prog" style="margin-top:14px"><div class="lb"><span data-p3txt>Add 3 more items to save 15%%</span><b data-p3lb style="color:var(--gold-d)">3 of 6</b></div><div class="tr"><i class="part" data-p3 style="width:50%%"></i></div></div>
      </div>
      %(l1)s%(l2)s%(l3)s%(l4)s
      <div class="note" style="margin-top:16px">The 10%% volume discount applies to the three eligible items only. Majlis OUD is a Reserve piece. It is never discounted, on any offer, at any basket size.</div>
    </div>
    <div><div class="sum">
      <div class="r"><span>Subtotal</span><span data-subtotal>AED 845</span></div>
      <div class="r" style="color:var(--green)" data-tierrow><span>Volume discount &middot; <b data-tierpct>10</b>%%</span><span data-tieramt>&minus; AED 19.50</span></div>
      <div class="r"><span>Delivery</span><span data-delivery style="color:var(--green)">Free</span></div>
      <div class="r" data-vatrow style="color:var(--mut);font-size:12.5px"><span>Includes VAT at 5%%</span><span data-vat>AED 39.31</span></div>
      <div class="r t"><span>Total</span><span data-total>AED 825.50</span></div>
      <a class="btn solid block" href="checkout.html" style="margin-top:12px">Checkout</a>
      <div class="pay" data-pay style="margin-top:14px;justify-content:center"><span>Card</span><span>Apple Pay</span><span>Tabby</span><span>Tamara</span><span class="off">COD</span></div>
      <p data-codnote style="font-size:11.5px;color:var(--mut);margin:12px 0 0;text-align:center">Cash on delivery is withheld over AED 300.</p>
    </div></div>
  </div>
</div></section>
""" % dict(vat=slot("VAT registration expected ~month 9"),
  l1=cline("Royal Amber","Oud oil &middot; 6 ml", 75, 2),
  l2=cline("Imperial Crown","Oud oil &middot; 3 ml &middot; AED 45 credit back", 45, 1),
  l3=cline("Majlis OUD","Oud &middot; 6 ml &middot; Reserve", 650, 1,
           '<div class="norm" style="margin-top:6px">Never discounted</div>', halo=True),
  l4=cline("Mystery oud, 3 ml","Gift with purchase over AED 300", 0, 1, gift=True))

checkout = """
<section><div class="wrap">
  <div class="sec-h"><h2 style="font-size:26px">Checkout</h2><span style="font-size:13px;color:var(--mut)">Guest checkout &middot; account optional</span></div>
  <div class="two">
    <div>
      <span class="eyebrow">1 &middot; Contact</span>
      <div class="grid g2" style="margin:10px 0 18px"><span class="field">Full name</span><span class="field">Phone &middot; UAE</span><span class="field" style="grid-column:1/-1">Email</span></div>
      <label style="display:flex;gap:9px;font-size:13px;color:var(--body);margin-bottom:26px"><input type="checkbox">Send me order updates on WhatsApp <span class="norm">, unticked by default, consent logged</span></label>
      <span class="eyebrow">2 &middot; Delivery</span>
      <div class="kv" style="margin:10px 0 26px">
        <div><span><b>Standard</b> &middot; free over AED 150</span><span>AED 12 below</span></div>
        <div><span><b>Same-day Dubai</b> &middot; before 2:00 PM</span><span>+AED 25</span></div>
        <div><span><b>Scheduled</b></span><span>Tomorrow to +30 days</span></div>
      </div>
      <span class="eyebrow">3 &middot; Payment</span>
      <div class="pay" data-paypick style="margin:10px 0 14px"><button type="button" class="on">Card</button><button type="button">Apple Pay</button><button type="button">Tabby</button><button type="button">Tamara</button><button type="button" data-codbtn>Cash on delivery</button></div>
      <div class="note">COD is withheld here because the bag is over AED 300. Under that it carries an AED 8 fee, waived when paid online. It is also withheld on QR-video orders and from customers with a prior refusal.</div>
    </div>
    <div><div class="sum">
      <div class="r"><span>4 items</span><span data-subtotal>AED 845</span></div>
      <div class="r" style="color:var(--green)" data-tierrow><span>Volume discount &middot; <b data-tierpct>10</b>%%</span><span data-tieramt>&minus; AED 19.50</span></div>
      <div class="r"><span>Delivery</span><span data-delivery style="color:var(--green)">Free</span></div>
      <div class="r" data-vatrow style="color:var(--mut);font-size:12.5px"><span>Includes VAT at 5%%</span><span data-vat>AED 39.31</span></div>
      <div class="r t"><span>Total</span><span data-total>AED 825.50</span></div>
      <a class="btn solid block" href="confirmed.html" style="margin-top:12px">Place order</a>
    </div></div>
  </div>
</div></section>
"""
confirmed = """
<section><div class="wrap" style="max-width:760px">
  <div style="text-align:center;padding:20px 0 34px">
    <div class="tick">%(check)s</div>
    <h2 style="font-size:26px;margin:0 0 8px">Order confirmed</h2>
    <p style="color:var(--mut);margin:0">Order number %(num)s</p>
  </div>
  <div class="kv">
    <div><span>Delivery</span><span>Free &middot; same-day if placed before 2 PM</span></div>
    <div><span>Includes VAT at 5%%</span><span>AED 39.31</span></div>
    <div><span>Tax registration number</span><span>%(trn)s</span></div>
    <div><span>Credit back</span><span>AED 45 voucher, issued the day it is delivered</span></div>
    <div><span>Review request</span><span>Delivery + 3 days</span></div>
    <div><span>Referral</span><span>Friend AED 20 off &middot; you credited after their delivery + 3 days</span></div>
  </div>
  <div style="display:flex;gap:12px;margin-top:24px"><a class="btn solid" href="track-order.html">Track this order</a><a class="btn" href="index.html">Keep shopping</a></div>
</div></section>
""" % dict(check=sv("check",26,2.6), num=slot("generated at checkout"), trn=slot("TRN, registration expected ~month 9"))
corporate = """
<section><div class="wrap">
  <div class="sec-h"><div><h2 style="font-size:26px">Corporate gifting</h2>
  <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0">Above 20 units this becomes a quote, not a checkout.</p></div></div>
  <div class="grid g4" style="margin-bottom:24px">
    <div class="sum" style="background:#fff"><span class="eyebrow">10 units</span><div class="tier">%(s)s</div><p style="font-size:12.5px;color:var(--mut);margin:0">Co-branding options</p></div>
    <div class="sum" style="background:#fff"><span class="eyebrow">25 units</span><div class="tier">%(s)s</div><p style="font-size:12.5px;color:var(--mut);margin:0">Co-branding options</p></div>
    <div class="sum" style="background:#fff"><span class="eyebrow">50 units</span><div class="tier">%(s)s</div><p style="font-size:12.5px;color:var(--mut);margin:0">Co-branding options</p></div>
    <div class="sum" style="background:#fff"><span class="eyebrow">100 units</span><div class="tier">Quote</div><p style="font-size:12.5px;color:var(--mut);margin:0">Full co-branding</p></div>
  </div>
  <div class="band"><div><h3>Tell us the occasion and the headcount</h3><p>Above 20 units this becomes a quote rather than a checkout. Send the details and we will come back with pricing.</p></div><a class="btn gold" href="#corporate-form">Request a quote</a></div>
  <div id="corporate-form" style="margin-top:22px;max-width:560px">
    <div class="grid g2" style="margin-bottom:12px"><input class="field" data-cq="name" aria-label="Your name" placeholder="Your name"><input class="field" data-cq="email" type="email" aria-label="Work email" placeholder="Work email"></div>
    <div class="grid g2" style="margin-bottom:12px"><input class="field" data-cq="occasion" aria-label="Occasion" placeholder="Occasion (Eid, wedding, staff gift)"><input class="field" data-cq="units" type="number" aria-label="Units" placeholder="Headcount / units"></div>
    <button type="button" class="btn solid" data-cqsend>Send enquiry</button>
    <p class="note" data-cqresult hidden style="margin:10px 0 0"></p>
  </div>
</div></section>
""" % dict(s="On quote")

track = """
<section><div class="wrap" style="max-width:720px">
  <span class="eyebrow">Home / Track order</span>
  <div class="sec-h" style="margin-top:10px"><div><h2 style="font-size:26px">Track your order</h2>
  <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0">Enter the order number from your confirmation, or the phone number you ordered with.</p></div></div>
  <div class="grid g2" style="margin-bottom:14px"><input class="field" data-ordernum aria-label="Order number" placeholder="Order number"><input class="field" data-orderphone type="tel" aria-label="Phone number" placeholder="Phone &middot; UAE"></div>
  <button type="button" class="btn solid block" data-findorder style="margin-bottom:10px">Find my order</button>
  <p class="note" data-findresult hidden style="margin:0 0 26px"></p>
  <span class="eyebrow">Where it will be</span>
  <div class="kv" style="margin-top:10px">
    <div><span>Placed</span><span>Order confirmed, payment taken</span></div>
    <div><span>Confirmed</span><span>COD orders wait here until confirmed</span></div>
    <div><span>Packed</span><span>Picked at the kiosk</span></div>
    <div><span>Shipped</span><span>Courier reference appears here</span></div>
    <div><span>Delivered</span><span>Credit-back voucher issues at this point</span></div>
  </div>
  <div class="note" style="margin-top:20px">Order updates can also come by WhatsApp, the opt-in is on the confirmation page, unticked by default.</div>
</div></section>
"""

account = """
<section><div class="wrap">
  <span class="eyebrow">Home / Account</span>
  <div class="acct-head">
    <div>
      <h2 style="font-size:26px;margin:8px 0 6px">%(name)s</h2>
      <p style="color:var(--mut);font-size:13.5px;margin:0">%(contact)s</p>
    </div>
    <div class="tierbadge"><span class="eyebrow gold-d">BGS One</span><b>%(tier)s</b></div>
  </div>

  <div class="acct">
    <nav class="acctnav">
      <a class="on" href="account.html">Overview</a>
      <a href="account.html">Orders</a>
      <a href="account.html">BGS One &amp; wallet</a>
      <a href="account.html">Referrals</a>
      <a href="account.html">Addresses</a>
      <a href="account.html">Details &amp; consent</a>
      <a href="index.html" class="out">Sign out</a>
    </nav>

    <div class="acctbody">
      <div class="grid g3" style="margin-bottom:26px">
        <div class="sum" style="background:#fff"><span class="eyebrow">Drops</span><div class="tier">%(drops)s</div><p class="mini">1 drop per AED 1 &middot; 100 drops = AED 5 credit</p></div>
        <div class="sum" style="background:#fff"><span class="eyebrow">Wallet credit</span><div class="tier">%(credit)s</div><p class="mini">Credit-back vouchers and referral credit</p></div>
        <div class="sum" style="background:#fff"><span class="eyebrow">Orders</span><div class="tier">%(orders)s</div><p class="mini">Lifetime, all channels</p></div>
      </div>

      <div class="sec-h"><h2 style="font-size:17px">BGS One</h2><a href="#">How it works &rarr;</a></div>
      <div class="sum" style="background:#fff;margin-bottom:26px">
        <div class="tiers">
          <div class="t on"><b>Musk</b><span>0 lifetime</span></div>
          <div class="t"><b>Amber</b><span>500 lifetime</span></div>
          <div class="t"><b>Oud</b><span>1,500 lifetime</span></div>
        </div>
        <div class="tr" style="margin:14px 0 10px"><i class="part" style="width:%(tierpct)s"></i></div>
        <p class="mini" style="margin:0">%(tiernext)s</p>
        <div class="kv" style="margin-top:14px">
          <div><span>Birthday oud</span><span>Oud tier</span></div>
          <div><span>Early access to a drop</span><span>Amber and Oud</span></div>
          <div><span>Double-drop events</span><span>When running</span></div>
        </div>
      </div>

      <div class="sec-h"><h2 style="font-size:17px">Wallet</h2></div>
      <div class="sum" style="background:#fff;margin-bottom:26px">
        <div class="kv">
          <div><span>Credit-back voucher &middot; 3 ml purchase</span><span>%(voucher)s</span></div>
          <div><span>Redeemable on</span><span>Any bottle over AED 75</span></div>
          <div><span>Expires</span><span>60 days from issue</span></div>
        </div>
        <p class="mini" style="margin:12px 0 0">Issued automatically the day a 3 ml order is delivered. Single use.</p>
      </div>

      <div class="sec-h"><h2 style="font-size:17px">Refer a friend</h2></div>
      <div class="sum" style="background:#fff;margin-bottom:26px">
        <div class="refbox"><span class="code">%(refcode)s</span><span class="btn sm">Copy link</span></div>
        <div class="kv" style="margin-top:14px">
          <div><span>They get</span><span>AED 20 off a first order over AED 99</span></div>
          <div><span>You get</span><span>AED 20 credit, 3 days after their delivery</span></div>
          <div><span>Referred so far</span><span>%(referred)s</span></div>
        </div>
      </div>

      <div class="sec-h"><h2 style="font-size:17px">Recent orders</h2><a href="track-order.html">Track an order &rarr;</a></div>
      <div class="sum" style="background:#fff;margin-bottom:26px">
        <div class="emptystate">
          <b>No orders yet</b>
          <p class="mini">Orders placed as a guest with this phone number will appear here once the number is verified.</p>
          <a class="btn sm" href="collection.html">Start shopping</a>
        </div>
      </div>

      <div class="sec-h"><h2 style="font-size:17px">Details &amp; consent</h2></div>
      <div class="sum" style="background:#fff">
        <div class="kv">
          <div><span>Phone</span><span>%(contact)s</span></div>
          <div><span>Email</span><span>%(email)s</span></div>
          <div><span>Language</span><span>English &middot; العربية</span></div>
        </div>
        <label class="consent"><input type="checkbox">Order updates on WhatsApp</label>
        <label class="consent"><input type="checkbox">Offers and new drops on WhatsApp</label>
        <p class="mini" style="margin:10px 0 0">Each opt-in is stored with its time, source and language. Opting out here also stops messages sent from the CRM.</p>
      </div>
    </div>
  </div>
</div></section>
""" % dict(name=slot("customer name"), contact=slot("phone"), email=slot("email"),
           tier="Musk", drops=slot("0"), credit=slot("AED 0"), orders=slot("0"),
           tierpct="0%%", tiernext="500 lifetime drops to Amber",
           voucher=slot("none active"), refcode=slot("unique code per customer"),
           referred=slot("0"))

quiz = """
<section><div class="wrap" style="max-width:760px">
  <span class="eyebrow">Home / Test your scent</span>

  <div class="quiz" data-quiz>
    <div class="qprog"><i data-qbar style="width:20%%"></i></div>
    <span class="qstep">Question <b data-qnum>1</b> of 5 &middot; under a minute</span>

    <div class="qcard" data-q="0">
      <h2>When will you wear it?</h2>
      <div class="qopts">
        <button type="button" data-a="daily">Every day<span>Work, errands, the school run</span></button>
        <button type="button" data-a="office">The office<span>Close to the skin, nothing loud</span></button>
        <button type="button" data-a="evening">Evenings out<span>Dinner, weddings, long nights</span></button>
        <button type="button" data-a="majlis">The majlis<span>Guests, oud, the good room</span></button>
      </div>
    </div>

    <div class="qcard" data-q="1" hidden>
      <h2>What should it feel like?</h2>
      <div class="qopts">
        <button type="button" data-a="bold">Bold<span>Announces itself</span></button>
        <button type="button" data-a="soft">Soft<span>Quiet, skin-close</span></button>
        <button type="button" data-a="warm">Warm<span>Spiced, resinous</span></button>
        <button type="button" data-a="fresh">Fresh<span>Bright and clean</span></button>
      </div>
    </div>

    <div class="qcard" data-q="2" hidden>
      <h2>Which of these draws you first?</h2>
      <div class="qopts qopts-2">
        <button type="button" data-a="citrus">Cut lemon and bergamot</button>
        <button type="button" data-a="rose">Rose and jasmine</button>
        <button type="button" data-a="spice">Clove, cinnamon, pepper</button>
        <button type="button" data-a="sweet">Vanilla and tonka</button>
        <button type="button" data-a="violet">Powdery violet and iris</button>
        <button type="button" data-a="wood">Agarwood and resin</button>
      </div>
    </div>

    <div class="qcard" data-q="3" hidden>
      <h2>How much should it carry?</h2>
      <div class="qopts">
        <button type="button" data-a="intimate">Only up close<span>Intimate</span></button>
        <button type="button" data-a="noticeable">Arm&rsquo;s length<span>Noticeable</span></button>
        <button type="button" data-a="room">Fills the room<span>Room-filling</span></button>
      </div>
    </div>

    <div class="qcard" data-q="4" hidden>
      <h2>Which half of the year?</h2>
      <div class="qopts">
        <button type="button" data-a="summer">Gulf summer<span>Has to survive the heat</span></button>
        <button type="button" data-a="winter">Cooler months<span>Room for something heavier</span></button>
        <button type="button" data-a="both">All year<span>One bottle, no thinking</span></button>
      </div>
    </div>

    <button type="button" class="qback" data-qback hidden>&larr; Back</button>
  </div>

  <div class="qresult" data-qresult hidden>
    <span class="eyebrow gold-d">Your profile</span>
    <h2 class="qtitle" data-rtitle></h2>
    <div class="pills" data-rpills style="margin:14px 0 22px"></div>

    <div class="sec-h"><h2 style="font-size:17px">Closest to what you described</h2></div>
    <div class="sum" style="background:#fff;margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap">
        <div style="min-width:0">
          <div style="font-weight:600;font-size:16px" data-rname></div>
          <div style="font-size:12.5px;color:var(--mut);margin-top:3px" data-rmeta></div>
        </div>
        <div style="font-weight:700;font-size:16px">AED 89</div>
      </div>
      <div class="kv" style="margin-top:14px">
        <div><span>Declared aroma facets</span><span data-rnotes style="text-align:right;max-width:60%%"></span></div>
        <div><span>Barcode</span><span data-rcode></span></div>
        <div><span>Match strength</span><span data-rscore></span></div>
      </div>
      <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
        <a class="btn solid" href="collection.html?cat=edp">See it</a>
        <button type="button" class="btn" data-qretake>Retake the quiz</button>
      </div>
    </div>

    <div class="note" style="margin-bottom:26px">These facets are estimated from the fragrance-allergen
    declarations printed on the package, not from an official note pyramid, the method is set out in the
    ingredients sheet. Eight of the nine sprays are not yet named on their packaging, so the barcode identifies
    them until you tell us the names.</div>

    <div class="band" style="margin-bottom:26px">
      <div><span class="eyebrow gold-d">Not ready to commit</span>
        <h3>Discovery Trio, AED 129</h3>
        <p>Three 3 ml ouds, including one from the family above. What you spend comes back as credit on your first full bottle.</p></div>
      <a class="btn gold" href="gift-box.html">Choose three</a>
    </div>

    <div class="sum" style="background:#fff">
      <span class="eyebrow">Send it to yourself</span>
      <p style="font-size:13px;color:var(--mut);margin:8px 0 14px">We can send this profile to your phone so you have it when you visit the kiosk.</p>
      <div class="grid g2" style="margin-bottom:12px"><span class="field">Your name</span><span class="field">+971 5X XXX XXXX</span></div>
      <label class="consent"><input type="checkbox">Send my scent profile and offers on WhatsApp</label>
      <p class="mini">Unticked on purpose. Nothing is sent unless you tick it, and the time, source and language of the
      consent are stored with it.</p>
      <button type="button" class="btn solid block" style="margin-top:12px">WhatsApp me my profile</button>
    </div>
  </div>
</div></section>
"""

# --- emit the product catalogue for the client, from one source ---
def unent(t):
    """catalogue.js is consumed with textContent, which escapes again. Store the
       actual characters so "His & Hers Duo" does not render as "HIS &AMP;"."""
    import html as _h
    return _h.unescape(_h.unescape(str(t)))

def emit_catalogue():
    """The client-side catalogue is a projection of the same content documents
       the pages are built from, so a price edited in the admin moves the card,
       the PDP and the cart together."""
    CRUMB = {"oud-oils": "Oud oils", "reserve": "Reserve", "bakhoor": "Bakhoor",
             "edp": "EDP sprays", "gift-sets": "Gift sets"}
    cat = {}
    for pr in published():
        doc = {
            "name": pr["name"], "meta": _meta(pr), "price": money(pr["price"]),
            "pn": (int(str(pr["price"]).replace(",", "")) if str(pr.get("price", "")).strip().replace(",", "").isdigit() else 0),
            "cat": pr["category"],
            "crumb": CRUMB.get(pr["category"], ""),
        }
        if pr.get("sizes"):
            doc["sizes"] = ["%s &middot; AED %s" % (z["label"], money(z["price"]))
                            for z in pr["sizes"]]
        if pr.get("images"):
            doc["images"] = pr["images"]
        for k_src, k_out in (("top","top"), ("heart","heart"), ("base","base"),
                             ("ingredients","ing"), ("barcode","sku"),
                             ("gender","gender"), ("story","story")):
            if pr.get(k_src):
                doc[k_out] = pr[k_src]
        if isinstance(pr.get("stock"), int):
            doc["stock"] = pr["stock"]
        if pr.get("never_discount"):
            doc["halo"] = True
        cat[pr["id"]] = doc

    def _clean(o):
        if isinstance(o, dict):  return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):  return [_clean(v) for v in o]
        if isinstance(o, str):   return unent(o)
        return o
    pathlib.Path("assets/catalogue.js").write_text(
        "window.BGS_CATALOGUE = " + json.dumps(_clean(cat), ensure_ascii=False) + ";\n")
    return len(cat)


PAGES = [("index.html","Oud Oils, Bakhoor &amp; EDP Sprays: Blended in Dubai",home,"","Home"),
         ("collection.html","Oud Oils: Alcohol-Free Perfume Oil in 3 ml and 6 ml",collection,"Oud Oils","Shop"),
         ("product.html","Royal Amber",product,"Oud Oils","Shop"),
         ("gift-box.html","Build a Gift Box: Three or Six Scents, Wrapped",giftbox,"Gift Sets","Gifts"),
         ("cart.html","Your Bag",cart,"","Bag"),
         ("checkout.html","Checkout: Guest Checkout, COD and Tabby",checkout,"","Bag"),
         ("confirmed.html","Order Confirmed",confirmed,"","Bag"),
         ("track-order.html","Track Your Order",track,"","Home"),
         ("account.html","Your Account: BGS One, Wallet and Referrals",account,"","Account"),
         ("quiz.html","Test Your Scent: Five Questions, One Minute",quiz,"","Home"),
         ("corporate.html","Corporate Gifting: Co-Branded Oud and Bakhoor",corporate,"Corporate Gifting","Home")]
print("catalogue:", emit_catalogue(), "products")
# The ?v= token stamps flow.css, shop.js AND catalogue.js, so it must hash all
# three (catalogue.js is written by emit_catalogue above). Hashing only flow.css
# served stale JS after any content or script edit.
CSSV = hashlib.md5(b"".join(
    pathlib.Path("assets/" + f).read_bytes() for f in ("flow.css", "shop.js", "catalogue.js")
)).hexdigest()[:8]
for fn, t, b, on, tab in PAGES:
    canon = (SITE_URL + "/" + fn) if SITE_URL else fn
    pathlib.Path(fn).write_text(shell(t, b, on, tab, strip_here=(fn != "index.html"),
                                      page="page-" + fn.replace(".html", ""),
                                      desc=PAGE_DESC.get(fn, SEO.get("default_description", "")),
                                      canon=canon))
print("wrote", len(PAGES), "pages")
