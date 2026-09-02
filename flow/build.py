# BGS Corner storefront — built ONLY from:
#   A) BGSecommercebuildbrief.md      (catalogue §3, taxonomy §4, rules §5-§11)
#   B) BGS Corner Sheet.xlsx          (product lineup, weights, August selling prices)
#   C) BGS_Perfume_Ingredients.xlsx   (EDP note profiles + barcodes)
# No images. No data from any other source. Unsourced fields render as placeholders.
import pathlib, hashlib, json
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

NAV = [("Oud Oils","collection.html"),("Reserve","collection.html"),("Bakhoor","collection.html"),
       ("EDP Sprays","collection.html"),("Gift Sets","gift-box.html"),("Discovery","collection.html"),
       ("Shop by Occasion","collection.html"),("Corporate Gifting","corporate.html")]
TABS = [("Home","index.html"),("Shop","collection.html"),("Gifts","gift-box.html"),("Bag","cart.html"),("Account","account.html")]

CATS = [('Oud Oils', 'collection.html?cat=oud-oils', 'c_oil', 'oud'), ('Reserve', 'collection.html?cat=reserve', 'c_res', 'res'), ('Bakhoor', 'collection.html?cat=bakhoor', 'c_bak', 'bak'), ('EDP Sprays', 'collection.html?cat=edp', 'c_edp', 'musk'), ('Gift Sets', 'gift-box.html', 'c_gift', 'floral'), ('Discovery', 'collection.html?cat=discovery', 'c_disc', 'fresh'), ('Shop by Occasion', 'collection.html?cat=occasion', 'c_occ', 'amber'), ('Corporate Gifting', 'corporate.html', 'c_corp', 'sweet')]
def catstrip():
    return ('<div class="catstrip"><div class="wrap"><div class="cs">' + "".join(
        '<a class="c-{3}" href="{0}"><span class="circle">{1}</span><span>{2}</span></a>'.format(h, sv(ic, 30, 1.5), n, k)
        for n, h, ic, k in CATS) + '</div></div></div>')

def shell(title, body, nav_on="", tab="Home", strip_here=True):
    strip = catstrip()
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s | BGS Corner</title><link rel="stylesheet" href="assets/flow.css?v=%(cssv)s"></head><body>
<div class="strip"><div class="wrap">
  <span>%(clock)s Order by 2:00 PM for delivery today in Dubai &middot; <b>3h 47m</b></span>
  <span class="r"><a href="#">Free UAE delivery over AED 150</a><a href="#">Cash on delivery</a><a href="track-order.html">Track order</a><a href="#" data-langtoggle>العربية</a></span>
</div></div>
<div class="mast"><div class="wrap">
  <span class="burger">%(menu)s</span>
  <a class="logo" href="index.html"><span class="logomark">%(slotlogo)s</span><span class="wm">BGS CORNER</span></a>
  <div class="search"><span class="cat">All categories %(chev)s</span>
    <input placeholder="Search ouds, oud, bakhoor&hellip;"><span class="go">%(search)s</span></div>
  <div class="acts">
    <a class="act" href="account.html">%(user)s<span>Account</span></a>
    <a class="act" href="account.html">%(heart)s<span>Wishlist</span></a>
    <a class="act" href="cart.html">%(bag)s<span>Bag</span><i class="n">4</i></a>
  </div>
</div>
<div class="msearch"><div class="search"><input placeholder="Search ouds, oud, bakhoor&hellip;"><span class="go">%(search)s</span></div></div></div>
%(strip)s
%(body)s
<footer><div class="wrap"><div class="cols">
  <div><div class="wm" style="color:#fff;font-size:20px;margin-bottom:14px">BGS CORNER</div>
    <p>BGS Corner General Trading LLC &middot; Dubai, UAE</p>
    <p>%(addr)s</p><div class="nl"><span class="field">Your email</span><span class="btn">Join</span></div></div>
  <div><h5>Shop</h5><a href="collection.html">Oud Oils</a><a href="collection.html">Oud</a><a href="collection.html">Bakhoor</a><a href="collection.html">EDP sprays</a><a href="gift-box.html">Gift sets</a></div>
  <div><h5>Help</h5><a href="#">Delivery &amp; returns</a><a href="#">How to apply oud</a><a href="track-order.html">Track your order</a><a href="#">FAQ</a></div>
  <div><h5>BGS Corner</h5><a href="account.html">Your account</a><a href="#">Our story</a><a href="corporate.html">Corporate gifting</a><a href="#">Wholesale</a></div>
</div><div class="bot"><span>&copy; 2026 BGS Corner General Trading LLC</span>
<span>Cards &middot; Apple Pay &middot; Tabby &middot; Tamara &middot; Cash on delivery</span></div></div></footer>
<div class="tabbar">%(tabs)s</div>
<script src="assets/catalogue.js?v=%(cssv)s"></script>
<script src="assets/shop.js?v=%(cssv)s"></script></body></html>
""" % dict(title=title, body=body, cssv=CSSV,
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

def card(name, meta, price, sizes=None, halo=False, notes=None, barcode=None, low=None):
    b = '<span class="badge res">Reserve</span>' if halo else ''
    if low: b = '<span class="badge low">%s left</span>' % low
    sz = ''
    if sizes:
        sz = '<div class="sizes">' + "".join('<span%s>%s</span>' % (ON if i==1 else "", s)
                                             for i, s in enumerate(sizes)) + '</div>'
    nt = '<span class="notes">%s</span>' % notes if notes else '<span class="notes">%s</span>' % slot("scent notes")
    bc = '<span class="norm">Barcode %s</span>' % barcode if barcode else ''
    hl = '<span class="norm">Never discounted</span>' if halo else ''
    return """<a class="p" href="product.html?p=%s">
  <div class="ph"><span class="none">Product image</span>%s<span class="heart">%s</span></div>
  <div class="b"><span class="meta">%s</span><span class="nm">%s</span>%s
  <span class="tax">%s &middot; %s</span>
  <span class="rev">%s</span>
  %s<div class="pr"><b>AED %s</b></div>%s%s
  <span class="btn sm solid" style="margin-top:4px">Add to bag</span></div></a>""" % (
    slug(name), b, sv("heart",15), meta, name, nt, slot("family"), slot("tone"),
    slot("no reviews yet"), sz, price, hl, bc)

def oudoil_cards(n=None):
    return "".join(card(nm, "Oud oil &middot; 3 ml / 6 ml", "75", sizes=["3 ml &middot; 45","6 ml &middot; 75"])
                   for nm in ATTARS[:n])
def reserve_cards():
    return "".join(card(n, "Reserve &middot; %s" % z, p, halo=True) for n, z, p in OUD)
def bakhoor_cards(n=None):
    return "".join(card(x, "Bakhoor &middot; %s" % g, p) for x, g, p in BAKHOOR[:n])
def edp_cards(n=None):
    out = []
    for e in EDP[:n]:
        low = e["stock"] <= 5
        out.append(card(e["name"], "EDP spray &middot; 50 ml &middot; " + e["gender"],
                        str(e["price"]),
                        notes=e["top"] + " &middot; " + e["heart"],
                        barcode=e["sku"], low=(e["stock"] if low else None)))
    return "".join(out)

def set_cards():
    return "".join(card(n, "Gift set &middot; %s" % c, p) for n, c, p in SETS)

# ---------------------------------------------------------------- HOME
home = """
<div class="hero" data-carousel>
  <div class="heroimg"><span class="none corner"><b data-slideno>1</b>/5</span></div>
  <div class="over slide on" data-slide><div class="wrap"><div class="box">
    <span class="eyebrow gold">Blended in Dubai &middot; alcohol-free ouds</span>
    <h1>Find your scent.</h1>
    <p>Eleven house ouds in 3 ml and 6 ml, Reserve oud, bakhoor and EDP sprays.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn gold" href="collection.html">Shop ouds</a>
      <a class="btn ghost" href="gift-box.html">Build a gift box</a>
    </div>
  </div></div></div>
  <div class="over slide" data-slide><div class="wrap"><div class="box">
    <span class="eyebrow gold">Order by 2:00 PM</span>
    <h1>Delivered today<br>in Dubai.</h1>
    <p>Same-day across Dubai for AED 25. Standard delivery is free over AED 150.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn gold" href="collection.html?cat=oud-oils">Shop ready today</a>
      <a class="btn ghost" href="track-order.html">Delivery info</a>
    </div>
  </div></div></div>
  <div class="over slide" data-slide><div class="wrap"><div class="box">
    <span class="eyebrow gold">Start here</span>
    <h1>Discovery Trio<br>, AED 129.</h1>
    <p>Three 3 ml ouds. What you spend comes back as credit on your first full bottle.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn gold" href="gift-box.html">Choose three</a>
      <a class="btn ghost" href="gift-box.html">See all sets</a>
    </div>
  </div></div></div>
  <div class="over slide" data-slide><div class="wrap"><div class="box">
    <span class="eyebrow gold">Gifting</span>
    <h1>Three scents,<br>one wrapped box.</h1>
    <p>Add a handwritten card and a recorded message. Prices never show on a gift receipt.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn gold" href="gift-box.html">Build a gift box</a>
      <a class="btn ghost" href="corporate.html">Corporate gifting</a>
    </div>
  </div></div></div>
  <div class="over slide" data-slide><div class="wrap"><div class="box">
    <span class="eyebrow gold">Reserve</span>
    <h1>Never<br>discounted.</h1>
    <p>Majlis OUD and Platinum Musk sit outside every discount the shop runs.</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <a class="btn gold" href="collection.html?cat=reserve">See Reserve</a>
      <a class="btn ghost" href="index.html">Our story</a>
    </div>
  </div></div></div>
  <button class="arrow prev" data-prev aria-label="Previous slide">%(prev)s</button>
  <button class="arrow next" data-next aria-label="Next slide">%(next)s</button>
  <div class="dots" data-dots><i class="on" data-dot="0"></i><i data-dot="1"></i><i data-dot="2"></i><i data-dot="3"></i><i data-dot="4"></i></div>
</div>

%(catstrip)s
<div class="usp">
  <div>%(truck)s<div><b>Free delivery over AED 150</b><span>AED 12 below &middot; UAE only</span></div></div>
  <div>%(clock)s<div><b>Same-day in Dubai</b><span>Before 2:00 PM &middot; +AED 25</span></div></div>
  <div>%(cash)s<div><b>Cash on delivery</b><span>Under AED 300 &middot; AED 8 fee</span></div></div>
  <div>%(leaf)s<div><b>Alcohol-free ouds</b><span>Oil based &middot; batch numbered</span></div></div>
</div>

<section style="padding-top:26px;padding-bottom:0"><div class="wrap">
  <div class="quizband">
    <div>
      <span class="eyebrow gold">Five questions &middot; under a minute</span>
      <h3>Find the blend that suits you</h3>
      <p>Tell us when you will wear it and what you are drawn to. We will point you at the closest thing we make.</p>
    </div>
    <a class="btn gold" href="quiz.html">Test your scent</a>
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
""" % dict(catstrip=catstrip(), truck=sv("truck",20), clock=sv("clock",20), cash=sv("cash",20), leaf=sv("leaf",20),
           prev=sv("left",22,2), next=sv("right",22,2),
           attars=oudoil_cards(4), oud=reserve_cards(), sets=set_cards()[:0] or "".join(
               card(n, "Gift set &middot; %s" % c, p) for n, c, p in SETS),
           bakhoor=bakhoor_cards(4), edp=edp_cards(6), ct=slot("count"))

# ---------------------------------------------------------------- COLLECTION
FACETS = [("Scent family",["Oud &amp; Woods","Amber &amp; Spice","Musk &amp; Clean","Floral Veil",
           "Fresh &amp; Citrus","Sweet &amp; Gourmand","Reserve"]),
          ("Tone",["Bold","Soft","Warm","Fresh","Mysterious","Modern"]),
          ("Gender",["Him","Her","Unisex"]),
          ("Format &amp; size",["Oud oil","EDP spray","Bakhoor","Gift set","3 ml","6 ml","12 ml","50 g"]),
          ("Occasion",["Daily","Office","Evening","Wedding","Gift","Majlis"]),
          ("Longevity",["Moderate","Long","Very long"]),
          ("Sillage",["Intimate","Noticeable","Room-filling"]),
          ("Season",["Summer-safe","Winter","Day","Night"]),
          ("Availability",["Ready today"])]
def facet(t, rows):
    return '<div class="fbox"><h4>%s</h4>%s</div>' % (t, "".join(
        '<label><input type="checkbox">%s<span class="ct">%s</span></label>' % (n, slot(",")) for n in rows))

collection = """
<section><div class="wrap">
  <span class="eyebrow">Home / Oud Oils</span>
  <div class="sec-h" style="margin-top:10px"><div><h2 style="font-size:26px">Oud oils</h2>
  <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0;max-width:70ch">Alcohol-free perfume oil in 3 ml and 6 ml. Eleven house blends.</p></div></div>
  <div class="plp">
    <div class="side" data-filters>
      <div class="drawerhead"><b>Filters</b><button type="button" class="closex" data-closefilters aria-label="Close filters">&times;</button></div>
      <div class="toolbar" style="border:0;padding:0;margin-bottom:6px"><b style="font-size:13px">Filters</b><a href="#" style="font-size:12.5px;color:var(--gold-d)">Clear all</a></div>
      %(facets)s
      <div class="fbox"><h4>Price</h4>
        <label><input type="checkbox">Under AED 50<span class="ct">%(s)s</span></label>
        <label><input type="checkbox">AED 50&ndash;100<span class="ct">%(s)s</span></label>
        <label><input type="checkbox">AED 100&ndash;200<span class="ct">%(s)s</span></label>
        <label><input type="checkbox">AED 200+<span class="ct">%(s)s</span></label>
      </div>
      <div class="draweractions"><button type="button" class="btn solid block" data-closefilters>Show 11 products</button></div>
    </div>
    <div class="scrim" data-closefilters></div>
    <div>
      <div class="toolbar">
        <button type="button" class="filterbtn" data-openfilters>%(filt)s Filters <i class="fcount">1</i></button>
        <div class="pills"><span class="pill on">Oud oil &times;</span><span class="pill">Ready today</span><span class="pill">Summer-safe</span></div>
        <div style="display:flex;gap:12px;align-items:center">
          <span style="font-size:13px;color:var(--mut)">11 products</span>
          <span class="sel">Sort: Featured %(chev)s</span></div>
      </div>
      <div class="grid g4">%(cards)s</div>
      <div class="pager"><span class="on">1</span><span>2</span><span>&rarr;</span></div>
    </div>
  </div>
</div></section>
""" % dict(facets="".join(facet(t,r) for t,r in FACETS), chev=sv("chev",13,2),
           cards=oudoil_cards(), s=slot(","), filt=sv("filter",15,1.9))

# ---------------------------------------------------------------- PDP
product = """
<section><div class="wrap">
  <span class="eyebrow">Home / Oud Oils / Royal Amber</span>
  <div class="pdp" style="margin-top:18px">
    <div class="gal">
      <div class="main"><span class="none">Product image</span></div>
      <div class="th"><div class="on"><span class="none">1</span></div><div><span class="none">2</span></div><div><span class="none">3</span></div><div><span class="none">Video</span></div></div>
    </div>
    <div class="buy">
      <div class="pills" style="margin-bottom:8px"><span class="pill">%(fam)s</span><span class="pill">%(tone)s</span><span class="pill">%(gen)s</span></div>
      <h1>Royal Amber</h1>
      <span class="rev">%(rev)s</span>
      <p style="color:var(--body);font-size:14px;line-height:1.65;margin:12px 0 16px">%(desc)s</p>
      <div style="display:flex;align-items:baseline;gap:10px;margin-bottom:6px">
        <span style="font-size:30px;font-weight:700">AED 75</span>
        <span style="color:var(--mut);font-size:13px">6 ml &middot; VAT included</span></div>
      <div style="margin:16px 0"><span class="eyebrow" style="display:block;margin-bottom:8px">Size</span>
        <div class="sizes" style="gap:8px"><span style="padding:11px 18px;font-size:13px">3 ml &middot; AED 45</span><span class="on" style="padding:11px 18px;font-size:13px">6 ml &middot; AED 75</span></div></div>
      <div class="kv" style="margin-bottom:16px">
        <div><span>Longevity</span><span>%(lon)s</span></div>
        <div><span>Sillage</span><span>%(sil)s</span></div>
        <div><span>Batch number</span><span>%(bat)s</span></div>
        <div><span>Availability</span><span>%(av)s</span></div>
      </div>
      <div style="display:flex;gap:10px;margin-bottom:12px">
        <span class="stepper" data-stepper><button type="button" data-step="-1" aria-label="Decrease quantity">&minus;</button><i data-qty>1</i><button type="button" data-step="1" aria-label="Increase quantity">+</button></span>
        <a class="btn solid" style="flex-grow:1" href="cart.html">Add to bag: AED 75</a></div>
      <a class="btn block" href="gift-box.html" style="margin-bottom:12px">Send as a gift</a>
      <div class="note">Try the 3 ml first, the AED 45 comes back as a voucher on any bottle over AED 75, issued the day it is delivered.</div>
      <div class="kv" style="margin-top:16px">
        <div><span>%(truck)s Delivery</span><span>Free over AED 150 &middot; same-day before 2 PM</span></div>
        <div><span>%(cash)s Payment</span><span>Card &middot; Apple Pay &middot; Tabby &middot; Tamara &middot; COD</span></div>
      </div>
    </div>
  </div>
</div></section>
<div class="stickybuy">
  <div><b>Royal Amber</b><span>AED 75 &middot; 6 ml</span></div>
  <a class="btn solid sm" href="cart.html">Add to bag</a>
</div>
<section class="alt"><div class="wrap">
  <div class="tabs2"><span class="on">Scent pyramid</span><span>How to apply oud</span><span>Ingredients &amp; allergens</span><span>Delivery &amp; returns</span><span>Reviews</span></div>
  <div class="grid g3">
    <div><span class="eyebrow">Top</span><p style="margin:8px 0 0">%(n1)s</p></div>
    <div><span class="eyebrow">Heart</span><p style="margin:8px 0 0">%(n2)s</p></div>
    <div><span class="eyebrow">Base</span><p style="margin:8px 0 0">%(n3)s</p></div>
  </div>
  <div class="note" style="margin-top:20px">Note values are not yet recorded for the oud oils. The EDP sprays carry theirs.</div>
</div></section>
<section><div class="wrap">
  <div class="sec-h"><h2>Complete the ritual</h2><a href="collection.html">More &rarr;</a></div>
  <div class="grid g4">%(rel)s</div>
</div></section>
""" % dict(fam=slot("family"), tone=slot("tone"), gen=slot("gender"), rev=slot("no reviews yet"),
   desc=slot("product description, not in any source file"), lon=slot("not set"), sil=slot("not set"),
   bat=slot("not set"), av=slot("Available Units column is empty in the sheet"),
   truck=sv("truck",16), cash=sv("cash",16), n1=slot("top notes"), n2=slot("heart notes"), n3=slot("base notes"),
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
      <div class="pay" style="margin-top:14px;justify-content:center"><span>Card</span><span>Apple Pay</span><span>Tabby</span><span>Tamara</span><span class="off">COD</span></div>
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
      <div class="pay" style="margin:10px 0 14px"><span class="on">Card</span><span>Apple Pay</span><span>Tabby</span><span>Tamara</span><span class="off">Cash on delivery</span></div>
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
  <div class="note" style="margin-bottom:20px">The brief specifies a 10 / 25 / 50 / 100 tier table but sets no per-unit prices, and neither spreadsheet carries them.</div>
  <div class="band"><div><h3>Tell us the occasion and the headcount</h3><p>The enquiry opens a pipeline opportunity; 20+ units go to quote rather than checkout.</p></div><a class="btn gold" href="#">Request a quote</a></div>
</div></section>
""" % dict(s=slot("price not set"))

track = """
<section><div class="wrap" style="max-width:720px">
  <span class="eyebrow">Home / Track order</span>
  <div class="sec-h" style="margin-top:10px"><div><h2 style="font-size:26px">Track your order</h2>
  <p style="color:var(--mut);font-size:13.5px;margin:6px 0 0">Enter the order number from your confirmation, or the phone number you ordered with.</p></div></div>
  <div class="grid g2" style="margin-bottom:14px"><span class="field">Order number</span><span class="field">Phone &middot; UAE</span></div>
  <a class="btn solid block" href="#" style="margin-bottom:26px">Find my order</a>
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
def emit_catalogue():
    cat = {}
    for e in EDP:
        cat[slug(e["name"])] = {
            "name": e["name"], "meta": "EDP spray &middot; 50 ml &middot; " + e["gender"],
            "price": str(e["price"]), "crumb": "EDP sprays", "story": e["story"],
            "top": e["top"], "heart": e["heart"], "base": e["base"],
            "ing": e["ing"], "sku": e["sku"], "stock": e["stock"],
        }
    for nm in ATTARS:
        cat[slug(nm)] = {"name": nm, "meta": "Oud oil &middot; 3 ml / 6 ml", "price": "75",
                         "crumb": "Oud oils", "sizes": ["3 ml &middot; AED 45", "6 ml &middot; AED 75"]}
    cat[slug("Majlis OUD")] = {"name": "Majlis OUD", "meta": "Reserve &middot; 6 ml", "price": "650",
        "crumb": "Reserve", "halo": True, "sizes": ["6 ml &middot; AED 650", "12 ml &middot; AED 1,295"]}
    cat[slug("Platinum Musk OUD")] = {"name": "Platinum Musk OUD", "meta": "Reserve &middot; 6 ml",
        "price": "399", "crumb": "Reserve", "halo": True}
    for n, g, pr in BAKHOOR:
        cat[slug(n)] = {"name": n, "meta": "Bakhoor &middot; " + g, "price": str(pr), "crumb": "Bakhoor"}
    for n, c, pr in SETS:
        cat[slug(n)] = {"name": n, "meta": "Gift set &middot; " + c, "price": str(pr), "crumb": "Gift sets"}
    pathlib.Path("assets/catalogue.js").write_text(
        "window.BGS_CATALOGUE = " + json.dumps(cat, ensure_ascii=False) + ";\n")
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
for fn, t, b, on, tab in PAGES:
    pathlib.Path(fn).write_text(shell(t, b, on, tab, strip_here=(fn != "index.html")))
print("wrote", len(PAGES), "pages")
