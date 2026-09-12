# BGS Corner storefront - built ONLY from:
#   A) BGSecommercebuildbrief.md      (catalogue §3, taxonomy §4, rules §5-§11)
#   B) BGS Corner Sheet.xlsx          (product lineup, weights, August selling prices)
#   C) BGS_Perfume_Ingredients.xlsx   (EDP note profiles + barcodes)
# No images. No data from any other source. Unsourced fields render as placeholders.
import pathlib, hashlib, json, html, re, struct, sys

def esc(t):
    """Escape admin-authored free text so a typed & or < cannot break markup."""
    return html.escape(str(t), quote=True)
# Every asset URL carries ?v=<content hash>. Netlify caches /assets/* for a year
# as immutable, so a file replaced under its own name has to change URL or
# returning visitors keep the old one.
_VH = {}
def _md5(path, salt=b""):
    if (path, salt) not in _VH:
        try:
            _VH[(path, salt)] = hashlib.md5(pathlib.Path(path).read_bytes() + salt).hexdigest()[:8]
        except OSError:
            _VH[(path, salt)] = ""
    return _VH[(path, salt)]
def V(path):
    h = _md5(path)
    return path + ("?v=" + h if h else "")
# Product photos: one version per photo, from its 1000 px original, shared by the
# copies tools/make_derivatives.py makes of it (-600, -card, -card-360, -thumb).
# Bump DERIVATIVES when those copies change without the original changing.
DERIVATIVES = b"d1"
def PV(name, suffix=""):
    h = _md5("assets/img/" + name, DERIVATIVES)
    return "assets/img/" + (name.replace(".jpg", suffix + ".jpg") if suffix else name) + ("?v=" + h if h else "")
# Card photos. On a phone two columns with a 16px wrap and a 13px gap make a
# 165px card, which 50vw would call 187px and so send the 520 file where the
# 360 is enough. The "Never discounted" row is one card per line up to 900px
# and a third of the wrap above it, so it has its own.
CARD_SIZES = "(max-width:560px) calc(50vw - 23px), (max-width:700px) 33vw, (max-width:900px) 25vw, 240px"
FEAT_SIZES = "(max-width:900px) calc(100vw - 34px), 410px"
GALLERY_SIZES = "(max-width:700px) 245px, (max-width:900px) 330px, 470px"
def png_size(path):
    """Width and height from a PNG header, so the <img> reserves its box before
       the file arrives. Anything that is not a PNG gets no size."""
    try:
        b = pathlib.Path(path).read_bytes()[:24]
    except OSError:
        return (0, 0)
    return struct.unpack(">II", b[16:24]) if b[:8] == b"\x89PNG\r\n\x1a\n" else (0, 0)

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
 "drop":'<path d="M12 3s6 6.5 6 10.5a6 6 0 0 1-12 0C6 9.5 12 3 12 3z"/>',
 "chev":'<path d="M6 9l6 6 6-6"/>', "filter":'<path d="M3 6h18M7 12h10M11 18h2"/>',
 "home":'<path d="M4 11.5 12 5l8 6.5"/><path d="M6 10.5V19h12v-8.5"/><path d="M10 19v-5h4v5"/>',
 "shop":'<rect x="4.5" y="4.5" width="6" height="6" rx="1"/><rect x="13.5" y="4.5" width="6" height="6" rx="1"/><rect x="4.5" y="13.5" width="6" height="6" rx="1"/><rect x="13.5" y="13.5" width="6" height="6" rx="1"/>',
 "share":'<path d="M4 13v6a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6"/><path d="M12 15V3.5"/><path d="M8 7.5l4-4 4 4"/>',
 "c_gift":'<rect x="3.5" y="9" width="17" height="11" rx="1"/><path d="M3.5 13h17M12 9v11"/><path d="M12 9S9.5 4 7.5 5.5 10 9 12 9zm0 0s2.5-5 4.5-3.5S14 9 12 9z"/>',
 "left":'<path d="M15 5l-7 7 7 7"/>', "right":'<path d="M9 5l7 7-7 7"/>', "check":'<path d="M5 12l5 5L19 7"/>',
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
    "collection.html": "Shop BGS Corner: attars and perfume oils, bakhoor, EDP sprays and gift sets. Filter by category, price and gender.",
    "product.html": "House-blended, alcohol-free fragrance from BGS Corner, Dubai. Attars and perfume oils, bakhoor and EDP sprays.",
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

# Data shop.js reads besides the catalogue: one window global each, written
# into catalogue.js after the catalogue in the order registered. An entry is
# (global name, function returning JSON data); the part of the build that
# owns the data registers it beside its own code.
EXTRA_GLOBALS = []

def published(cat=None):
    """Documents in display order, optionally one category."""
    rows = [dict(p, id=k) for k, p in PRODUCTS.items() if p.get("published", True)]
    if cat:
        rows = [r for r in rows if r.get("category") == cat]
    return sorted(rows, key=lambda r: r.get("order") or 0)

def tab_link(label, href, icon, on):
    """One tab-bar entry, drawn as its icon. The label stays as the accessible
       name - aria-label for screen readers, title for a pointer - because an
       icon-only bar has nothing else to announce. A tab whose icon key is
       missing from P falls back to its label, so a content edit that forgets
       the icon gets a word rather than an empty slot."""
    cur = ' class="on" aria-current="page"' if label == on else ""
    face = sv(icon, 21, 1.6) if icon in P else esc(label)
    return '<a href="%s" aria-label="%s" title="%s"%s>%s</a>' % (
        esc(href), esc(label), esc(label), cur, face)
def slug(t):
    import re as _r
    t = t.replace("&amp;","and").replace("&middot;"," ").replace("&rsquo;","")
    return _r.sub(r"[^a-z0-9]+","-",t.lower()).strip("-")

def slot(label):
    """A field with no value in any of the three sources."""
    return '<span class="slot">%s</span>' % label

BRAND = C["settings"].get("brand", {})

def _brand_alt():
    return esc(BRAND.get("logo_alt") or SETTINGS.get("name") or "BGS Corner")

def header_logo():
    """Masthead brand: the logo image when set in settings.brand, else the
    wordmark fallback. Content-driven - the admin swaps the file, not the code.
    The art carries the whole lockup, CORNER included (tools/make_gold_logo.py),
    so there is nothing to set beside it."""
    logo = BRAND.get("logo")
    if logo:
        w, h = png_size(logo)
        size = ' width="%d" height="%d"' % (w, h) if w else ""
        return ('<a class="logo" href="index.html">'
                '<img class="brandmark" src="%s" alt="%s"%s></a>' % (esc(V(logo)), _brand_alt(), size))
    return ('<a class="logo" href="index.html"><span class="logomark">%s</span>'
            '<span class="wm">BGS CORNER</span></a>' % slot("logo"))

def favicon_links():
    """Tab/home-screen icons from settings.brand.icons - generated by
    tools/make_favicon.py off the gold emblem. Emits only what is set."""
    ic = BRAND.get("icons") or {}
    tags = []
    if ic.get("ico"):
        tags.append('<link rel="icon" href="%s" sizes="any">' % esc(ic["ico"]))
    if ic.get("png32"):
        tags.append('<link rel="icon" type="image/png" sizes="32x32" href="%s">' % esc(V(ic["png32"])))
    if ic.get("png16"):
        tags.append('<link rel="icon" type="image/png" sizes="16x16" href="%s">' % esc(V(ic["png16"])))
    if ic.get("apple"):
        tags.append('<link rel="apple-touch-icon" href="%s">' % esc(V(ic["apple"])))
    return "\n".join(tags)

def footer_logo():
    """Footer brand: the lifted logo on the dark ground, else wordmark."""
    logo = BRAND.get("logo_light") or BRAND.get("logo")
    if logo:
        w, h = png_size(logo)
        size = ' width="%d" height="%d"' % (w, h) if w else ""
        return ('<img class="foot-logo" src="%s" alt="%s"%s loading="lazy" decoding="async">'
                % (esc(V(logo)), _brand_alt(), size))
    return ('<div class="wm" style="color:#fff;font-size:20px;margin-bottom:14px">'
            'BGS CORNER</div>')

NAV = [(n["label"], n["href"]) for n in NAVC["main"]]
TABS = [(n["label"], n["href"], n.get("icon", "")) for n in NAVC["tabs"]]

CATS = [(c["label"], c["href"], c["tint"], c["image"], c.get("cutout", False))
        for c in NAVC["categories"]]
def catnav():
    """The sticky category bar under the masthead.

    Built from nav.categories, not nav.main. nav.main carries the same eight
    labels but every href is a bare collection.html, so all eight would land on
    the same unfiltered page; nav.categories carries the ?cat= that actually
    filters. nav.main was read into NAV at import and then emitted by nothing,
    which is why there was nothing under the masthead to begin with."""
    return ('<nav class="catnav" aria-label="Categories"><div class="wrap">'
            + "".join('<a href="%s" data-catnav="%s">%s</a>'
                      % (esc(h), esc(h.split("cat=")[1] if "cat=" in h else ""), esc(n))
                      for n, h, k, img, cut in CATS)
            + '</div></nav>')

def footer_cols():
    """The footer's link columns, from navigation.json (they used to be written
       out in shell(), so an edit to the file changed nothing). A link with no
       address yet is shown as text, as FAQ and Our story are."""
    return "".join(
        '  <div><h5>%s</h5>%s</div>\n' % (esc(col["heading"]), "".join(
            '<a href="%s">%s</a>' % (esc(l["href"]), esc(l["label"])) if l.get("href")
            else '<span class="soon">%s</span>' % esc(l["label"])
            for l in col["links"]))
        for col in NAVC["footer"])

def catstrip():
    # data-n: how many circles there are, so narrow screens can split them
    # into even rows (six as three and three, not four and two).
    return ('<div class="catstrip"><div class="wrap"><div class="cs" data-n="%d">' % len(CATS) + "".join(
        # The photograph is an <img> whose path comes from navigation.json, not
        # a url() in flow.css, which used to name every file. A cut-out on
        # transparency ("cutout": true) gets class pop and stands in front of its
        # circle instead of being clipped by it. The label is text, with a break
        # opportunity after "/": "Attars/Perfume" has no space, so without one it
        # overflowed its cell at 375px - 78px of text in 76px. A cut-out marked
        # "wide" is a group wider than it is tall (the gift boxes): it sits
        # across the circle instead of rising out of it.
        '<a class="c-{2}{4}" href="{0}"><span class="circle"><img src="{3}" alt="" '
        'width="108" height="108"></span><span>{1}</span></a>'.format(
            esc(h), esc(n).replace("/", "/<wbr>"), k, esc(V(img)),
            " pop wide" if cut == "wide" else " pop" if cut else "")
        for n, h, k, img, cut in CATS) + '</div></div></div>')

# The strip's language toggle swaps interface labels for their Arabic in the
# browser: shop.js looks each label's exact English text up in this
# dictionary, which reaches it as window.BGS_AR in catalogue.js. Keeping it in
# content lets the admin edit it; build.py itself prints no Arabic.
TRANSLATIONS = json.loads((CONTENT_DIR / "translations.json").read_text(encoding="utf-8"))
EXTRA_GLOBALS.append(("BGS_AR", lambda: TRANSLATIONS.get("ar", {})))

# The bag, checkout, confirmation, account and tracking pages are for someone
# mid-purchase, not for search results.
NOINDEX = {"page-cart", "page-checkout", "page-confirmed", "page-account", "page-track-order"}

def shell(title, body, nav_on="", tab="Home", page="", desc="", canon=""):
    """No category strip here. The circles are a homepage shelf now - the sticky
       catnav carries the same eight destinations on every page, so a second copy
       of them under the masthead was the same row twice. index.html emits its
       own from the home template; strip_here went with it."""
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s | BGS Corner</title>
<meta name="description" content="%(desc)s">
%(robots)s<link rel="canonical" href="%(canon)s">
<meta property="og:type" content="website">
<meta property="og:title" content="%(title)s | BGS Corner">
<meta property="og:description" content="%(desc)s">
<meta property="og:image" content="%(ogimg)s">
<meta name="twitter:card" content="summary_large_image">
%(icons)s
%(preload)s<link rel="stylesheet" href="%(css)s"></head><body class="%(page)s">
<noscript><div class="nojs">This shop needs JavaScript for products, the bag and checkout. Please turn it on in your browser.</div></noscript>
<div class="strip"><div class="wrap">
  <span>%(clock)s Order by 2:00 PM for delivery today in Dubai<span data-cutoff hidden> &middot; <b></b></span></span>
  <span class="r"><span>Free UAE delivery over AED 150</span><span>Cash on delivery</span><a href="track-order.html">Track order</a><a href="#" data-langtoggle>العربية</a></span>
</div></div>
<div class="mast"><div class="wrap">
  %(brandlogo)s
  <form class="search" action="collection.html" method="get" role="search">
    <input name="q" aria-label="Search products" placeholder="Search ouds, oud, bakhoor&hellip;"><button type="submit" class="go" aria-label="Search">%(search)s</button></form>
  <div class="acts">
    <a class="act" href="account.html">%(user)s<span>Account</span></a>
    <a class="act" href="account.html">%(heart)s<span>Wishlist</span></a>
    <a class="act" href="cart.html">%(bag)s<span>Bag</span><i class="n" data-bagcount hidden>0</i></a>
  </div>
</div>
<div class="msearch"><form class="search" action="collection.html" method="get" role="search"><input name="q" aria-label="Search products" placeholder="Search ouds, oud, bakhoor&hellip;"><button type="submit" class="go" aria-label="Search">%(search)s</button></form></div></div>
%(catnav)s
%(body)s
<footer><div class="wrap"><div class="cols">
  <div>%(footlogo)s
    <p>BGS Corner General Trading LLC &middot; Dubai, UAE</p>
    <p>%(addr)s</p><div class="nl"><span class="field">Your email</span><span class="btn">Join</span></div></div>
%(footcols)s
</div><div class="bot"><span>&copy; 2026 BGS Corner General Trading LLC</span>
<span>Cards &middot; Apple Pay &middot; Tabby &middot; Tamara &middot; Cash on delivery</span></div></div></footer>
<div class="tabbar">%(tabs)s</div>
<script src="%(catjs)s"></script>
<script src="%(shopjs)s"></script></body></html>
""" % dict(title=title, body=body, page=page, css=V("assets/flow.min.css"),
   catjs=V("assets/catalogue.js"), shopjs=V("assets/shop.js"),
   preload=PRELOAD if page == "page-product" else "",
   robots='<meta name="robots" content="noindex,follow">\n' if page in NOINDEX else "",
   desc=esc(desc), canon=esc(canon),
   ogimg=esc(((SITE_URL + "/") if SITE_URL else "") + (V(SEO["og_image"]) if SEO.get("og_image") else "")),
   catnav=catnav(), tabs="".join(tab_link(l, h, ic, tab) for l, h, ic in TABS),
   clock=sv("clock",13,2), menu=sv("menu",22), chev=sv("chev",14,2), search=sv("search",17),
   user=sv("user"), heart=sv("heart"), bag=sv("bag"),
   brandlogo=header_logo(), footlogo=footer_logo(), footcols=footer_cols(), icons=favicon_links(),
   addr=slot("address, hours, phone"))

# ---------------------------------------------------------------- DATA
# names + sizes: BGS Corner Sheet.xlsx "OUD & Bakhoor Stock"; prices: brief §3
ATTARS = ["Imperial Crown","Dark Leather","Royal Amber","Golden Bloom","Majestic Musk",
          "Musk Bloom","Belle Aura","Magnolia Veil","Parisian Muse","Velvet Spell","Desert Breeze","Seasonal slot"]
OUD = [("Majlis OUD","6 ml","650"),("Majlis OUD","12 ml","1,295"),("Platinum Musk OUD","6 ml","399")]
# EDP names: brief §3. Notes + barcode: BGS_Perfume_Ingredients.xlsx (only "Be Mine" is named there)
EDP = json.loads(pathlib.Path('edp_data.json').read_text())
SETS = [("Discovery Trio","3 &times; 3 ml","129"),("His &amp; Hers Duo","2 &times; 6 ml","149"),
        ("Majlis Ritual Set","6 ml + bakhoor","129"),("Oud Lover&rsquo;s Flight","3 &times; 6 ml","199"),
        ("Eid Royal Hamper","2 &times; 6 ml + EDP + bakhoor","299"),("Dubai in a Bottle","3 ml + mini bakhoor","79")]

def card(name, meta, price, sizes=None, halo=False, notes=None, barcode=None, low=None,
         pid=None, images=None, img_sizes=CARD_SIZES):
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
  <button type="button" class="btn sm solid" data-add="%s" style="margin-top:4px">Add to bag</button></div></a>""" % (
    key, ph_img(images, name, img_sizes), b, heart, meta, esc(name), nt, sz, price, hl, key)

def ph_img(images, alt, img_sizes=CARD_SIZES):
    """A real photograph if the product has one, the placeholder if not.

       Two frames are emitted when the product has them: the close-up, and the
       shot with the box underneath it. CSS cross-fades to the second on hover,
       so the card turns into the boxed view. Products with only one shot get
       one image and simply do not swap."""
    if not images:
        return '<span class="none">Product image</span>'
    a = alt.replace('"', "&quot;")
    def srcs(n):
        return PV(n, "-card"), "%s 360w, %s 520w" % (PV(n, "-card-360"), PV(n, "-card"))
    s, ss = srcs(images[0])
    out = ('<img class="ph-a" src="%s" srcset="%s" sizes="%s" alt="%s" loading="lazy" '
           'decoding="async" width="520" height="520">' % (s, ss, img_sizes, a))
    if len(images) > 1:
        # The hover-only second photo waits for a pointer or focus (shop.js). At
        # opacity 0 with a src it downloaded with the first on every card.
        s, ss = srcs(images[1])
        out += ('<img class="ph-b" data-src="%s" data-srcset="%s" sizes="%s" alt="" '
                'aria-hidden="true" decoding="async" width="520" height="520">'
                % (s, ss, img_sizes))
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
    if c == "attars":    return "Perfume oil &middot; " + " / ".join(z["label"] for z in pr.get("sizes", []))
    if c == "bakhoor":   return "Bakhoor &middot; %s" % pr.get("size","")
    if c == "gift-sets": return "Gift set &middot; %s" % pr.get("contents","")
    return ""

def _cards(cat, n=None):
    return _cards_from(published(cat)[:n])

def _cards_from(rows, img_sizes=CARD_SIZES):
    out = []
    for pr in rows:
        sizes = ["%s &middot; AED %s" % (z["label"], money(z["price"])) for z in pr.get("sizes", [])] or None
        stock = pr.get("stock")
        notes = None
        if pr.get("top") or pr.get("heart"):
            notes = " &middot; ".join(x for x in (pr.get("top"), pr.get("heart")) if x)
        out.append(card(pr["name"], _meta(pr), money(pr["price"]), sizes=sizes, pid=pr["id"],
                        images=pr.get("images"), img_sizes=img_sizes,
                        halo=pr.get("never_discount", False), notes=notes,
                        barcode=pr.get("barcode") or None,
                        low=(stock if isinstance(stock, int) and stock <= 5 else None)))
    return "".join(out)

def attar_cards(n=None):   return _cards("attars", n)

def halo_cards(n=None):
    """The pieces that sit outside every discount. This used to be the Reserve
       category; now that Reserve is folded into attars it selects on
       never_discount, which is what made them Reserve in the first place."""
    return _cards_from([r for r in published() if r.get("never_discount")][:n], FEAT_SIZES)
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
       where it wraps without knowing any HTML. The space before the <br> is
       load-bearing: the phone hides the break, since home.json's newlines are
       chosen for the desktop hero's line length, and without a space the two
       halves joined into "Platinum MuskOUD." A trailing space before a line
       break collapses, so desktop is unaffected."""
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
               esc(sl.get("headline", "")).replace("\n", " <br>"), esc(sl.get("body", "")), cta))
    return "".join(out)

def reels():
    """Portrait product films (9:16) in a row of their own under the EDP shelf.
       Each card shows a still first; shop.js requests the muted film only once
       the card is on screen and pauses it when it leaves, so a visitor who never
       scrolls this far downloads none of it. The list is content (home.json
       "reels"): the film, its still and the product the card links to."""
    r = HOME.get("reels") or {}
    items = [it for it in r.get("items", []) if it.get("video") and it.get("still")]
    if not items:
        return ""
    cards = []
    for it in items:
        pid = it.get("product", "")
        pr = PRODUCTS.get(pid) or {}
        href = ("product.html?p=" + pid) if pr else "collection.html?cat=edp"
        cards.append('<a class="reel" href="%s"><img src="%s" alt="" loading="lazy" decoding="async" '
                     'width="480" height="854"><video data-src="%s" muted loop playsinline preload="none" '
                     'aria-hidden="true"></video><span>%s</span></a>'
                     % (esc(href), esc(V(it["still"])), esc(V(it["video"])), esc(it.get("label") or pr.get("name", ""))))
    return ('<section class="alt reels"><div class="wrap">\n'
            '  <div class="sec-h"><h2>%s</h2><a href="collection.html?cat=edp">All EDP sprays &rarr;</a></div>\n'
            '  <div class="reelrow">%s</div>\n</div></section>\n' % (esc(r.get("title", "")), "".join(cards)))

def hero_images():
    """One photograph per slide, so the carousel changes picture and not only
       words. Driven from home.json's hero_slides, like the copy is - a slide
       with no image set falls back to the first one that has, which keeps the
       band from going black if the admin adds a slide and forgets the photo.

       Only the first is eager and fetchpriority=high; the rest are lazy, or
       five full-width banners would compete with the one actually on screen."""
    slides = HOME["hero_slides"]
    first = next((s["image"] for s in slides if s.get("image")), "")
    out = []
    for i, sl in enumerate(slides):
        src = sl.get("image") or first
        if not src:
            continue
        # A <picture>, because the phone gets a different CROP, not a smaller
        # copy. object-position could only ever be right at one band width: the
        # window's share of the frame changes with the viewport, so the value
        # that centred the product at 375px pushed it off at 614px. The phone
        # asset is cropped 1.85:1 around the product, which is the band's exact
        # ratio, so there is nothing left to aim - centre is centre everywhere.
        # Phones pick 750 or 1110 px, desktops 1320 or 2400, by width and
        # density. Slides other than the first are display:none until shop.js
        # marks them "seen" (flow.css), since opacity 0 does not stop a download.
        phone = src.replace(".jpg", "-phone.jpg")
        out.append(
            '<picture>'
            '<source media="(max-width:900px)" srcset="%s 750w, %s 1110w" '
            'sizes="(max-width:560px) 100vw, 560px">'
            '<img class="hs%s" src="%s" srcset="%s 1320w, %s 2400w" '
            'sizes="(max-width:1320px) 100vw, 1320px" alt="%s" width="2400" height="790"%s>'
            '</picture>'
            % (esc(V(phone.replace(".jpg", "-750.jpg"))), esc(V(phone)),
               " on seen" if i == 0 else "", esc(V(src)),
               esc(V(src.replace(".jpg", "-1320.jpg"))), esc(V(src)),
               esc(sl.get("image_alt", "")),
               ' fetchpriority="high" decoding="async"' if i == 0
               else ' loading="lazy" decoding="async"'))
    return "".join(out)

def hero_dots():
    return "".join('<i%s data-dot="%d"></i>' % (' class="on"' if i == 0 else "", i)
                   for i in range(len(HOME["hero_slides"])))

# ---------------------------------------------------------------- HOME
home = """
<div class="hero" data-carousel>
  <div class="heroimg">%(hero_img)s<span class="none corner"><b data-slideno>1</b>/%(hero_n)s</span></div>
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
  <div class="sec-h"><h2>Attars and perfume oils</h2><a href="collection.html?cat=attars">All 13 &rarr;</a></div>
  <div class="grid g5">%(attars)s</div>
</div></section>

<section><div class="wrap"><div class="band">
  <div><span class="eyebrow gold-d">Start here</span>
    <h3>Discovery Trio, AED 129</h3>
    <p>Three 3 ml ouds. Whatever you spend comes back as a single-use voucher on any bottle over AED 75, valid 60 days.</p></div>
  <a class="btn gold" href="gift-box.html">Choose three</a>
</div></div></section>

<section><div class="wrap">
  <div class="sec-h"><h2>Never discounted</h2><a href="collection.html?cat=attars">All attars &rarr;</a></div>
  <div class="grid feat">%(oud)s</div>
</div></section>

<section class="alt"><div class="wrap">
  <div class="sec-h"><h2>Gift sets</h2><a href="collection.html?cat=gift-sets">All sets &rarr;</a></div>
  <div class="grid g5">%(sets)s</div>
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
    <a class="promo" href="collection.html?cat=gift-sets"><span class="none">Banner</span><div><b>Discovery 3 ml</b><span>Credit back on your first bottle</span></div></a>
    <a class="promo" href="corporate.html"><span class="none">Banner</span><div><b>Corporate gifting</b><span>Quote above 20 units</span></div></a>
  </div>
</div></section>

<section class="alt"><div class="wrap">
  <div class="sec-h"><h2>Bakhoor &amp; home</h2><a href="collection.html?cat=bakhoor">Shop bakhoor &rarr;</a></div>
  <div class="grid g5">%(bakhoor)s</div>
</div></section>

<section><div class="wrap">
  <div class="sec-h"><h2>EDP sprays</h2><a href="collection.html?cat=edp">All 9 &rarr;</a></div>
  <div class="grid g5">%(edp)s</div>
</div></section>
%(reels)s""" % dict(reels=reels(), catstrip=catstrip(), usp=usp_strip(),
           hero=hero_slides(), hero_img=hero_images(), hero_dots=hero_dots(),
           hero_n=len(HOME["hero_slides"]),
           qb_eyebrow=COPY["quiz_banner"]["eyebrow"], qb_heading=COPY["quiz_banner"]["heading"],
           qb_body=COPY["quiz_banner"]["body"], qb_cta=COPY["quiz_banner"]["cta_label"],
           qb_href=COPY["quiz_banner"]["cta_href"],
           prev=sv("left",22,2), next=sv("right",22,2),
           attars=attar_cards(5), oud=halo_cards(), sets=set_cards(5),
           bakhoor=bakhoor_cards(), edp=edp_cards(5), ct=slot("count"))

# ---------------------------------------------------------------- COLLECTION
# Only facets the content layer actually carries: category and price for all
# products, gender for the EDP sprays. Family/tone/occasion/season are in the
# brief taxonomy but have no per-product value in any source, so they are not
# offered as controls that would do nothing.
FACETS_LIVE = [
    ("Category", "cat", [("Attars", "attars"),
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
    <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0;max-width:70ch" data-intro>Every blend in the shop: attars and perfume oils, bakhoor, EDP sprays and gift sets.</p></div></div>
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
# One template serves every product and shop.js fills it in. What the template
# has no value for (the notes strip, the spec lines) ships hidden and is shown
# once filled, so no bare labels are drawn. Blocks that describe only some
# kinds of product name them in data-cats: the notes and the pyramid are for
# the perfumes, how to apply is for the oils. The credit-back note is about
# buying the 3 ml, so it names that size in data-with-size. shop.js takes these
# out of any other product's page.
product = """
<section><div class="wrap">
  <span class="eyebrow">Home / Attars / Royal Amber</span>
  <div class="pdp">
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
        <span class="permeta">6 ml</span>
        <!-- Share sits on the price row, not on a row of its own: the buy
             decision was measured to fit a 900px screen with 2px to spare, so
             anything that adds height here pushes it off. -->
        <button type="button" class="sharebtn" data-share
                aria-label="Share this product">%(share)s<span data-sharelabel>Share</span></button></div>
      <div class="sizeblock" data-sizeblock><span class="eyebrow">Size</span>
        <div class="sizes" style="gap:8px"><button type="button" data-size="3 ml &middot; AED 45">3 ml &middot; AED 45</button><button type="button" class="on" data-size="6 ml &middot; AED 75">6 ml &middot; AED 75</button></div></div>
      <div class="atcrow">
        <span class="stepper" data-stepper><button type="button" data-step="-1" aria-label="Decrease quantity">&minus;</button><i data-qty>1</i><button type="button" data-step="1" aria-label="Increase quantity">+</button></span>
        <button type="button" class="btn solid" style="flex-grow:1" data-add data-addqty>Add to bag: AED 75</button></div>
      <a class="btn block" href="gift-box.html" style="margin-bottom:12px">Send as a gift</a>
      <div class="notestop" data-notestop data-cats="edp attars" hidden>
        <div><span class="ni">%(leaf)s</span><b>Top</b><p data-note="top"></p></div>
        <div><span class="ni">%(hrt)s</span><b>Heart</b><p data-note="heart"></p></div>
        <div><span class="ni">%(drop)s</span><b>Base</b><p data-note="base"></p></div>
      </div>

      <div class="belowbuy">
        <p class="story-slot" data-desc>%(desc)s</p>
        <div class="note" data-with-size="3 ml">Try the 3 ml first, the AED 45 comes back as a voucher on any bottle over AED 75, issued the day it is delivered.</div>
        <div class="kv" data-specs style="margin-top:16px" hidden>
          <div hidden><span>Longevity</span><span>%(lon)s</span></div>
          <div hidden><span>Sillage</span><span>%(sil)s</span></div>
          <div hidden><span>Batch number</span><span>%(bat)s</span></div>
          <div hidden><span>Availability</span><span>%(av)s</span></div>
        </div>
        <div class="kv facts" style="margin-top:16px">
          <div><span>%(truck)s Delivery</span><span>Free over AED 150 &middot; same-day before 2 PM</span></div>
          <div><span>%(cash)s Payment</span><span>Card &middot; Apple Pay &middot; Tabby &middot; Tamara &middot; COD</span></div>
        </div>
      </div>
    </div>
  </div>
</div></section>
<div class="stickybuy">
  <div><b data-sbname>Royal Amber</b><span data-sbmeta>AED 75 &middot; 6 ml</span></div>
  <button type="button" class="btn solid sm" data-add data-addqty>Add to bag</button>
</div>
<section class="alt"><div class="wrap">
  <div class="tabs2" role="tablist">
    <button type="button" class="on" data-tab="pyramid" data-cats="edp attars" role="tab" aria-selected="true">Scent pyramid</button>
    <button type="button" data-tab="apply" data-cats="attars" role="tab" aria-selected="false">How to apply oud</button>
    <button type="button" data-tab="ing" role="tab" aria-selected="false">Ingredients &amp; allergens</button>
    <button type="button" data-tab="delivery" role="tab" aria-selected="false">Delivery &amp; returns</button>
    <button type="button" data-tab="reviews" role="tab" aria-selected="false">Reviews</button>
  </div>
  <div data-panel="pyramid" data-cats="edp attars">
    <div class="grid g3">
      <div><span class="eyebrow">Top</span><p style="margin:8px 0 0" data-note="top"></p></div>
      <div><span class="eyebrow">Heart</span><p style="margin:8px 0 0" data-note="heart"></p></div>
      <div><span class="eyebrow">Base</span><p style="margin:8px 0 0" data-note="base"></p></div>
    </div>
    <div class="note" data-pyrnote style="margin-top:20px" hidden>The scent pyramid is published for our EDP sprays. For the attars it is coming soon.</div>
  </div>
  <div data-panel="apply" data-cats="attars" hidden>
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
   leaf=sv("leaf",15), hrt=sv("heart",15), drop=sv("drop",15),
   share=sv("share",15), rel=attar_cards(4))

# ---------------------------------------------------------------- GIFT BOX
giftbox = """
<section><div class="wrap">
  <span class="eyebrow">Home / Build Your Gift Box</span>
  <div class="sec-h" style="margin-top:10px"><div><h2 style="font-size:26px">Build a gift box</h2>
  <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0">Three or six slots, filled from the house scents, leaving as one cart line with its contents itemised.</p></div></div>
  <div class="two">
    <div>
      <div class="pills" style="margin-bottom:18px">
        <button type="button" class="pill on" data-boxsize="3">3 slots</button>
        <button type="button" class="pill" data-boxsize="6">6 slots</button></div>
      <div class="grid g3" data-slots style="margin-bottom:22px"></div>
      <div class="sec-h"><h2 style="font-size:17px">Add to the box</h2></div>
      <div class="grid g4">%(pick)s</div>
    </div>
    <div>
      <div class="sum">
        <div class="r"><span data-boxn>0 scents</span><span data-boxscents>AED 0</span></div>
        <div class="r"><span>Premium box</span><span>AED 25</span></div>
        <div class="r" data-boxdisc style="color:var(--faint)"><span>Volume discount at 3 items</span><span>&minus;10%%</span></div>
        <div class="r t"><span>Total</span><span data-boxtotal>AED 25</span></div>
        <button type="button" class="btn ghost block" data-boxcta style="margin-top:12px">Fill 3 more slots</button>
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
""" % dict(pick=attar_cards(6))

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
  <div class="sec-h"><h2 style="font-size:26px">Your bag<span data-bagitems></span></h2><a href="collection.html">Continue shopping &rarr;</a></div>
  <div class="two">
    <div>
      <div class="sum" data-cartprogress style="background:#fff;margin-bottom:18px">
        <div class="prog"><div class="lb"><span>Free UAE delivery over AED 150</span><b data-p1lb style="color:var(--green)">Unlocked</b></div><div class="tr"><i data-p1 style="width:100%%"></i></div></div>
        <div class="prog" style="margin-top:14px"><div class="lb"><span>Free mystery oud over AED 300</span><b data-p2lb style="color:var(--green)">Unlocked</b></div><div class="tr"><i data-p2 style="width:100%%"></i></div></div>
        <div class="prog" style="margin-top:14px"><div class="lb"><span data-p3txt>Add 3 more items to save 15%%</span><b data-p3lb style="color:var(--gold-d)">3 of 6</b></div><div class="tr"><i class="part" data-p3 style="width:50%%"></i></div></div>
      </div>
      <div data-cartlines></div>
      <div data-cartempty class="empty" hidden>
        <p style="margin-bottom:16px">Your bag is empty.</p>
        <a class="btn solid" href="collection.html">Browse the collection</a>
      </div>
      <div data-cartnote class="note" style="margin-top:16px" hidden>Reserve pieces are never discounted, on any offer, at any basket size, so they sit outside the volume ladder.</div>
    </div>
    <div data-cartsummary><div class="sum">
      <div class="r"><span>Subtotal</span><span data-subtotal>AED 0</span></div>
      <div class="r" style="color:var(--green)" data-tierrow><span>Volume discount &middot; <b data-tierpct>10</b>%%</span><span data-tieramt>&minus; AED 19.50</span></div>
      <div class="r"><span>Delivery</span><span data-delivery style="color:var(--green)">Free</span></div>
      <div class="r t"><span>Total</span><span data-total>AED 825.50</span></div>
      <a class="btn solid block" href="checkout.html" style="margin-top:12px">Checkout</a>
      <div class="pay" data-pay style="margin-top:14px;justify-content:center"><span>Card</span><span>Apple Pay</span><span>Tabby</span><span>Tamara</span><span class="off">COD</span></div>
      <p data-codnote style="font-size:11.5px;color:var(--mut);margin:12px 0 0;text-align:center">Cash on delivery is withheld over AED 300.</p>
    </div></div>
  </div>
</div></section>
""" % dict(vat=slot("VAT registration expected ~month 9"))

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
      <div class="r" style="color:var(--green)" data-tierrow><span>Volume discount &middot; <b data-tierpct>10</b>%</span><span data-tieramt>&minus; AED 19.50</span></div>
      <div class="r"><span>Delivery</span><span data-delivery style="color:var(--green)">Free</span></div>
      <div class="r" data-vatrow style="color:var(--mut);font-size:12.5px"><span>Includes VAT at 5%</span><span data-vat>AED 39.31</span></div>
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
           tierpct="0%", tiernext="500 lifetime drops to Amber",
           voucher=slot("none active"), refcode=slot("unique code per customer"),
           referred=slot("0"))

# ---------------------------------------------------------------- scent quiz
# The quiz lives in content/quiz.json. The questions and their answers are
# printed here; what each answer looks for, the profiles it is scored against
# and the words shop.js writes into the result reach it as window.BGS_QUIZ.
# An answer's key joins the two, which is why keys never change.
QUIZ = json.loads((CONTENT_DIR / "quiz.json").read_text(encoding="utf-8"))
_QKEYS = [o["key"] for q in QUIZ["questions"] for o in q["options"]]
_QP = []
if len(set(_QKEYS)) != len(_QKEYS) or sorted(_QKEYS) != sorted(a["key"] for a in QUIZ["answers"]):
    _QP.append("quiz.json: each answer of each question needs one entry in answers, under its key")
if "{n}" not in QUIZ["page"]["step_label"]:
    _QP.append("quiz.json: the step line needs {n} where the question number goes")
if _QP:
    sys.exit("build failed:\n  " + "\n  ".join(_QP))

def quiz_card(i, q):
    """One question with its answers; only the first shows until one is picked."""
    opts = "\n".join('        <button type="button" data-a="%s">%s%s</button>' % (
        esc(o["key"]), esc(o["label"]), "<span>%s</span>" % esc(o["sub"]) if o.get("sub") else "")
        for o in q["options"])
    return ('    <div class="qcard" data-q="%d"%s>\n      <h2>%s</h2>\n      <div class="qopts%s">\n%s\n'
            '      </div>\n    </div>\n' % (i, " hidden" if i else "", esc(q["title"]),
                                           " qopts-2" if q.get("columns") == 2 else "", opts))

def quiz_global():
    """What shop.js needs to score the answers and word the result: each
       question's kind (the result files an answer's label under it), each
       answer's facets and label, the profiles, and the result's own words."""
    r = QUIZ["result"]
    return {"kinds": [q["kind"] for q in QUIZ["questions"]],
            "answers": {a["key"]: {"facets": a["facets"], "label": a["label"]} for a in QUIZ["answers"]},
            "profiles": QUIZ["profiles"],
            "result": {k: r[k] for k in ("title_fallback", "score", "unnamed", "unnamed_slot")}}
EXTRA_GLOBALS.append(("BGS_QUIZ", quiz_global))

quiz = """
<section><div class="wrap" style="max-width:760px">
  <span class="eyebrow">%(crumb)s</span>

  <div class="quiz" data-quiz>
    <div class="qprog"><i data-qbar style="width:%(bar)s"></i></div>
    <span class="qstep">%(step)s</span>

%(cards)s
    <button type="button" class="qback" data-qback hidden>%(back)s</button>
  </div>

  <div class="qresult" data-qresult hidden>
    <span class="eyebrow gold-d">%(r_eyebrow)s</span>
    <h2 class="qtitle" data-rtitle></h2>
    <div class="pills" data-rpills style="margin:14px 0 22px"></div>

    <div class="sec-h"><h2 style="font-size:17px">%(r_heading)s</h2></div>
    <div class="sum" style="background:#fff;margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap">
        <div style="min-width:0">
          <div style="font-weight:600;font-size:16px" data-rname></div>
          <div style="font-size:12.5px;color:var(--mut);margin-top:3px" data-rmeta></div>
        </div>
        <div style="font-weight:700;font-size:16px" data-rprice></div>
      </div>
      <div class="kv" style="margin-top:14px">
        <div><span>%(r_notes_label)s</span><span data-rnotes style="text-align:right;max-width:60%%"></span></div>
        <div><span>%(r_barcode_label)s</span><span data-rcode></span></div>
        <div><span>%(r_score_label)s</span><span data-rscore></span></div>
      </div>
      <div style="display:flex;gap:10px;margin-top:14px;flex-wrap:wrap">
        <a class="btn solid" href="collection.html?cat=edp" data-rsee>%(r_see_label)s</a>
        <button type="button" class="btn" data-qretake>%(r_retake_label)s</button>
      </div>
    </div>

    <div class="note" style="margin-bottom:26px">%(r_note)s</div>

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
""" % dict(crumb=esc(QUIZ["page"]["crumb"]), back=esc(QUIZ["page"]["back"]),
           step=esc(QUIZ["page"]["step_label"]).replace("{n}", "<b data-qnum>1</b>")
                                              .replace("{total}", str(len(QUIZ["questions"]))),
           bar="%g%%" % (100.0 / len(QUIZ["questions"])),
           cards="\n".join(quiz_card(i, q) for i, q in enumerate(QUIZ["questions"])),
           **{"r_" + k: esc(v) for k, v in QUIZ["result"].items()})

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
    CRUMB = {"attars": "Attars", "bakhoor": "Bakhoor",
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
    # versions for the photos shop.js builds URLs for at runtime (see PV)
    imgv = {n: _md5("assets/img/" + n, DERIVATIVES)
            for pr in published() for n in (pr.get("images") or [])}
    extra = "".join("window.%s = %s;\n" % (name, json.dumps(fn(), ensure_ascii=False, separators=(",", ":")))
                    for name, fn in EXTRA_GLOBALS)
    pathlib.Path("assets/catalogue.js").write_text(
        "window.BGS_CATALOGUE = " + json.dumps(_clean(cat), ensure_ascii=False) + ";\n"
        "window.BGS_IMGV = " + json.dumps({k: v for k, v in imgv.items() if v}, separators=(",", ":")) + ";\n"
        + extra)
    return len(cat)


PAGES = [("index.html","Attars, Bakhoor &amp; EDP Sprays: Blended in Dubai",home,"","Home"),
         ("collection.html","Attars and Perfume Oils: Alcohol-Free, 3 ml and 6 ml",collection,"Attars/Perfume Oils","Shop"),
         ("product.html","Royal Amber",product,"Attars/Perfume Oils","Shop"),
         ("gift-box.html","Build a Gift Box: Three or Six Scents, Wrapped",giftbox,"Gift Sets","Gifts"),
         ("cart.html","Your Bag",cart,"","Bag"),
         ("checkout.html","Checkout: Guest Checkout, COD and Tabby",checkout,"","Bag"),
         ("confirmed.html","Order Confirmed",confirmed,"","Bag"),
         ("track-order.html","Track Your Order",track,"","Home"),
         ("account.html","Your Account: BGS One, Wallet and Referrals",account,"","Account"),
         ("quiz.html","Test Your Scent: Five Questions, One Minute",quiz,"","Home"),
         ("corporate.html","Corporate Gifting: Co-Branded Oud and Bakhoor",corporate,"Corporate Gifting","Home")]
print("catalogue:", emit_catalogue(), "products")
def minify_css(css):
    """The stylesheet ships without comments and spare whitespace: comments are
       a third of flow.css and half of what it compresses to. Quoted strings are
       set aside so nothing inside them changes. Comments and strings are found
       in one left-to-right pass: done one after the other, the apostrophe in a
       comment like "the card's badge" paired with the next quote and took rules
       with it. Spaces are dropped only around { } ; , > and never around ":",
       where ".a :hover" and ".a:hover" are different selectors."""
    keep = []
    def hold(m):
        if m.group(0).startswith("/*"):
            return ""
        keep.append(m.group(0)); return "\x00%d\x00" % (len(keep) - 1)
    css = re.sub(r'/\*.*?\*/|"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'', hold, css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css).replace(";}", "}")
    return re.sub("\x00(\\d+)\x00", lambda m: keep[int(m.group(1))], css).strip() + "\n"
pathlib.Path("assets/flow.min.css").write_text(minify_css(pathlib.Path("assets/flow.css").read_text()))

def product_preload():
    """product.html is one template for every product, and its main photo only
       exists once catalogue.js and shop.js have run, so the browser finds it
       late. This head script finds it early: it reads ?p= and preloads that
       product's photo with the same candidates and sizes the gallery uses."""
    m = {pr["id"]: [PV(pr["images"][0], "-600"), PV(pr["images"][0])]
         for pr in published() if pr.get("images")}
    return ('<script>(function(){var m=%s,p=new URLSearchParams(location.search).get("p"),'
            'e=p&&Object.prototype.hasOwnProperty.call(m,p)&&m[p];if(!e)return;'
            'var l=document.createElement("link");l.rel="preload";l.as="image";'
            'l.fetchPriority="high";l.href=e[1];l.imageSrcset=e[0]+" 600w, "+e[1]+" 1000w";'
            'l.imageSizes=%s;document.head.appendChild(l)})()</script>\n'
            % (json.dumps(m, separators=(",", ":")), json.dumps(GALLERY_SIZES)))
PRELOAD = product_preload()
for fn, t, b, on, tab in PAGES:
    canon = (SITE_URL + "/" + fn) if SITE_URL else fn
    pathlib.Path(fn).write_text(shell(t, b, on, tab,                                       page="page-" + fn.replace(".html", ""),
                                      desc=PAGE_DESC.get(fn, SEO.get("default_description", "")),
                                      canon=canon))
print("wrote", len(PAGES), "pages")

# 404.html is served for a missing path at any depth, where a relative
# assets/flow.css would point somewhere else, so it carries its own style and
# works out its home link: the GitHub Pages copy lives under /structured-corner-v2/.
pathlib.Path("404.html").write_text("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Page not found | BGS Corner</title><meta name="robots" content="noindex">
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;text-align:center;
background:#faf8f4;color:#171310;font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{padding:24px}h1{font:600 28px/1.2 Georgia,"Times New Roman",serif;margin:0 0 10px}
a{display:inline-block;margin-top:18px;background:#171310;color:#fff;padding:12px 22px;text-decoration:none;border-radius:999px}</style>
</head><body><main><h1>We couldn&rsquo;t find that page</h1><p>The link may be old or mistyped.</p>
<a id="home" href="/">Go to the BGS Corner homepage</a></main>
<script>document.getElementById("home").href=location.pathname.indexOf("/structured-corner-v2/")===0?"/structured-corner-v2/":"/";</script>
</body></html>
""")
# Search results are thin, endless variations of one page.
pathlib.Path("robots.txt").write_text("User-agent: *\nDisallow: /collection.html?q=\n")

# ---------------------------------------------------------------- CHECKS
# The deploys stop when this script fails, and nothing else would notice a page
# asking for a file that is not there: V() and PV() simply leave the ?v= off,
# and the rebuild check compares only this script's output with the commit.
def _problems():
    out = []
    out += ["missing: " + p for (p, salt), h in sorted(_VH.items()) if not h]
    try:
        made = json.loads(pathlib.Path("tools/derivatives.json").read_text())
    except (OSError, ValueError):
        made = {}
    def whole(p):
        return hashlib.md5(pathlib.Path(p).read_bytes()).hexdigest()
    for pr in published():
        for n in pr.get("images") or []:
            orig = "assets/img/" + n
            for suf in ("", "-card", "-600", "-card-360", "-thumb"):
                f = "assets/img/" + n.replace(".jpg", suf + ".jpg")
                if not pathlib.Path(f).exists():
                    out.append("missing: " + f)
                elif suf in ("-600", "-card-360", "-thumb") and pathlib.Path(orig).exists() \
                        and (made.get(f) or [None, None])[1] != whole(orig):
                    out.append("made from an older photo: %s (run tools/make_derivatives.py)" % f)
    for dst, (src, h, _) in sorted(made.items()):
        if pathlib.Path(src).exists() and whole(src) != h:
            out.append("made from an older photo: %s (run tools/make_derivatives.py)" % dst)
    # every *.html here is published, so one this script no longer writes would
    # stay live; delete it, or add it back to PAGES
    written = {fn for fn, *_ in PAGES} | {"404.html"}
    out += ["not written by build.py but would be published: " + f.name
            for f in sorted(pathlib.Path(".").glob("*.html")) if f.name not in written]
    return sorted(set(out))
PROBLEMS = _problems()
if PROBLEMS:
    sys.exit("build failed:\n  " + "\n  ".join(PROBLEMS))
