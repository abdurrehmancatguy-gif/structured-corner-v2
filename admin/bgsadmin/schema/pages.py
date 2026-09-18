"""Page text (flow/content/pages.json): the words of the header and footer
every page shares, the homepage's bands, and the collection, product, gift
box, bag, tracking, corporate, account and 404 pages.

Fields are grouped by page ("group") and, inside a long page, by the part of
it they belong to ("section"), so the Pages screen can show one page at a
time. RESOURCE["groups"] lists those pages in the screen's order, each with
the storefront page it opens; checkout and the order confirmation are listed
too, locked, because their words stay in code with payments and VAT. The top
strip and the search hint are under Site text; the legal name, the location
and the tab-title suffix are under Settings.
"""
SHELL, HOME, COLLECTION, PRODUCT = "Header and footer", "Homepage bands", "Collection", "Product page"
LEGAL = "Legal pages"
GIFT_BOX, BAG, TRACK, CORPORATE, ACCOUNT, NOT_FOUND = "Gift box", "Bag", "Track order", "Corporate", "Account", "404"
LOCKED = "Changed by a developer in code"

GROUPS = [
    {"key": "shell", "label": SHELL, "page": "index.html",
     "about": "The header links, the footer and the no-JavaScript notice every page shares. "
              "The top strip and the search hint are under Site text."},
    {"key": "home", "label": HOME, "page": "index.html",
     "about": "The Discovery band, the promo tiles, the scent family tiles and the link beside the films. "
              "The banner and the shelves are under Homepage and Collections."},
    {"key": "collection", "label": COLLECTION, "page": "collection.html",
     "about": "The collection page's filters, sorting and empty state. Category names and intros are under Collections."},
    {"key": "product", "label": PRODUCT, "page": "product.html",
     "about": "The words around every product: the buy box, the detail rows, the tabs and the related row. "
              "Each product's own text is under Products."},
    {"key": "gift-box", "label": GIFT_BOX, "page": "gift-box.html",
     "about": "The gift box builder: its heading, slots, summary and gift options. The box fee and its discount are under Discounts."},
    {"key": "bag", "label": BAG, "page": "cart.html",
     "about": "The bag page: its progress bars, lines, empty state and summary, the checkout bar on phones, "
              "and the panel that opens after Add to bag on every page. "
              "The payment chips and the cash on delivery note belong to checkout and stay in code."},
    {"key": "track-order", "label": TRACK, "page": "track-order.html",
     "about": "The order tracking page and the replies its button gives."},
    {"key": "corporate", "label": CORPORATE, "page": "corporate.html",
     "about": "The corporate gifting page, its enquiry form and the replies the form gives."},
    {"key": "account", "label": ACCOUNT, "page": "account.html",
     "about": "The account page's sign-in panel, its headings and its programme, wallet, referral and consent text. "
              "A signed-in shopper's name, email and picture come from sign-in; their other details stay placeholders "
              "until the database arrives."},
    {"key": "legal", "label": LEGAL, "page": "privacy-policy.html",
     "about": "The four policy pages linked in the footer: shipping and delivery, returns and refunds, privacy, and "
              "terms and conditions. Each one is a title, the date it was last updated and its text, one line per "
              "paragraph: a line starting \"## \" is a heading and a line starting \"- \" is a point in a list."},
    {"key": "404", "label": NOT_FOUND, "page": "404.html",
     "about": "The page a visitor sees when a link leads nowhere."},
    {"key": "checkout", "label": "Checkout", "page": "checkout.html", "locked": LOCKED,
     "about": "Its words sit with payments, VAT and cash on delivery, which are locked."},
    {"key": "confirmed", "label": "Order confirmed", "page": "confirmed.html", "locked": LOCKED,
     "about": "Its words sit with payments and VAT, which are locked."},
]

RESOURCE = {"name": "pages", "label": "Pages", "kind": "document",
            "intro": "The words on the shop's pages: the header and footer every page shares, the homepage's bands, "
                     "and the collection, product, gift box, bag, tracking, corporate, account and 404 pages.",
            "groups": GROUPS}

# Some texts carry a {token} the build fills in; a field's pattern names the
# ones it may use, so any other brace is refused before it reaches the site.
RULES = ("dispatch", "free_over", "delivery_fee", "sameday_fee", "cutoff", "cutoff_short")
RULE_HELP = ("{dispatch} prints how long dispatch takes, {free_over} prints the free delivery threshold, {delivery_fee} the delivery fee, {sameday_fee} the "
             "same-day fee, {cutoff} the same-day cutoff written like 2:00 PM and {cutoff_short} written like 2 PM. "
             "They come from Settings, so the text follows a change there.")
RULE_PATTERN_HELP = "Use only {free_over}, {delivery_fee}, {sameday_fee}, {cutoff} or {cutoff_short}; leave out any other braces."
COUNT = r"[^{}]*\{n\}[^{}]*"
COUNT_HELP = "Keep {n} once: it is where the number goes."


def tokens(*names):
    """A pattern that allows the named {tokens} and no other brace."""
    return r"(?:[^{}]|\{(?:%s)\})*" % "|".join(names)


def needs(name, *others):
    """A pattern that needs {name} at least once and allows it and the other
    named tokens, as build.py's need= checks it."""
    return r"(?=[\s\S]*\{%s\})" % name + tokens(name, *others)


def only(*names):
    """The patternHelp that goes with tokens(names) or needs(names)."""
    return "Use only %s; leave out any other braces." % " and ".join("{%s}" % n for n in names)


def text(path, label, group, max_length, section=None, help=None, required=True, kind="text", **more):
    f = {"path": path, "type": kind, "label": label, "required": required, "maxLength": max_length, "group": group}
    if section:
        f["section"] = section
    if help:
        f["help"] = help
    f.update(more)
    return f


def href(path, label, group, section=None, help=None):
    f = {"path": path, "type": "href", "label": label, "required": True, "group": group}
    if section:
        f["section"] = section
    if help:
        f["help"] = help
    return f


# ---- every page -------------------------------------------------------------

_SHELL = [
    text("/shell/noscript", "No-JavaScript notice", SHELL, 200, kind="textarea",
         help="At the top of every page for a visitor whose browser has JavaScript turned off."),
    text("/shell/crumb_home", "Breadcrumb start", SHELL, 20,
         help="The first step of every breadcrumb: the collection, product, gift box, tracking and account pages."),
    text("/shell/header/account", "Account link", SHELL, 20, section="Header"),
    text("/shell/header/wishlist", "Wishlist link", SHELL, 20, section="Header",
         help="It opens the account page, which has no wishlist yet."),
    text("/shell/header/bag", "Bag link", SHELL, 20, section="Header"),
    text("/shell/header/signed_in", "Account link, signed in", SHELL, 60, section="Header",
         pattern=needs("name"), patternHelp="Keep {name}: it is where the shopper's name goes.",
         help="What screen readers hear on the header's account link and the phone tab bar's Account while a "
              "shopper is signed in; the link also shows the shopper's picture or first letter."),
    text("/shell/search/see_all", "See all results row", SHELL, 40, section="Search",
         help="The last row of the list that opens under the search box as a shopper types. "
              "It opens the collection page with every product the words find."),
    text("/shell/search/none", "No matches line", SHELL, 80, section="Search",
         help="In the list, when no product matches what is typed. Screen readers hear it too."),
    text("/shell/search/count_one", "Result count, one", SHELL, 40, section="Search", pattern=COUNT,
         patternHelp=COUNT_HELP, help="What screen readers hear when the words find one product. {n} is 1."),
    text("/shell/search/count_many", "Result count, several", SHELL, 40, section="Search", pattern=COUNT,
         patternHelp=COUNT_HELP, help="What screen readers hear when the words find more than one product. "
                                      "{n} is how many."),
    text("/shell/footer/contact/address", "Address", SHELL, 120, section="Footer", required=False,
         help="The footer line under the legal name. While address, hours and phone are all empty, "
              "the footer shows its address, hours, phone placeholder."),
    text("/shell/footer/contact/hours", "Opening hours", SHELL, 60, section="Footer", required=False),
    text("/shell/footer/contact/phone", "Phone", SHELL, 30, section="Footer", required=False,
         pattern=r"[0-9+() -]*", patternHelp="Digits, spaces, +, brackets and hyphens only."),
    text("/shell/footer/newsletter/placeholder", "Newsletter box", SHELL, 30, section="Footer",
         help="The footer's email box and button are text, not a form: nothing signs anyone up yet."),
    text("/shell/footer/newsletter/button", "Newsletter button", SHELL, 20, section="Footer"),
    {"path": "/shell/footer/copyright_year", "type": "int", "label": "Copyright year", "required": True,
     "min": 2000, "max": 2100, "group": SHELL, "section": "Footer",
     "help": "The footer's last line reads the copyright sign, this year and the legal name from Settings. "
             "The year is typed here rather than taken from the date, so a rebuild never changes the pages by itself."},
]

# ---- homepage ---------------------------------------------------------------

# The scent family tiles: their links, colours and drawings are code; the
# words and the photographs are content.
FAMILIES = (("oud-and-woods", "Oud & Woods"), ("amber-and-spice", "Amber & Spice"), ("musk-and-clean", "Musk & Clean"),
            ("floral-veil", "Floral Veil"), ("fresh-and-citrus", "Fresh & Citrus"),
            ("sweet-and-gourmand", "Sweet & Gourmand"), ("reserve", "Reserve"), ("bakhoor-and-home", "Bakhoor & Home"))

_HOME = [
    {"path": "/index/discovery_band/product", "type": "product-ref", "label": "Product", "required": True,
     "group": HOME, "section": "Discovery band",
     "help": "The band under the attars shelf. Its heading's {price} is this product's price, so it follows the product."},
    text("/index/discovery_band/eyebrow", "Small heading", HOME, 40, section="Discovery band"),
    text("/index/discovery_band/heading", "Heading", HOME, 60, section="Discovery band",
         pattern=tokens("price"), patternHelp="Write {price} where the product's price goes; leave out any other braces."),
    text("/index/discovery_band/body", "Text", HOME, 240, section="Discovery band", kind="textarea",
         help="The product page's credit-back note describes the same voucher: keep the two in step."),
    text("/index/discovery_band/cta_label", "Button", HOME, 30, section="Discovery band"),
    href("/index/discovery_band/cta_href", "Button link", HOME, section="Discovery band"),
    {"path": "/index/promos", "type": "rows", "label": "Promo tiles", "min": 1, "max": 3, "itemLabel": "title",
     "canAdd": True, "group": HOME, "section": "Promo tiles",
     "help": "The tiles under the scent families. Their pictures arrive with the media stage; "
             "until then each tile shows its Banner placeholder.",
     "fields": [
         {"path": "/title", "type": "text", "label": "Title", "required": True, "maxLength": 40},
         {"path": "/sub", "type": "text", "label": "Line under it", "required": True, "maxLength": 60},
         {"path": "/href", "type": "href", "label": "Link", "required": True},
     ]},
] + [f for slug, name in FAMILIES for f in (
    text("/index/families/%s/label" % slug, name + " tile", HOME, 30, section="Scent families",
         help="The tile opens the collection page showing this family's products."),
    text("/index/families/%s/words" % slug, name + " words", HOME, 200, section="Scent families", required=False,
         help="Words, separated by commas, that put a product in this family when its name, category, size line "
              "or notes contain one (oud finds every Oud Attar). A product whose Scent family field names this "
              "family is in it too, and Reserve also holds every never-discounted product."),
    {"path": "/index/families/%s/image" % slug, "type": "image", "label": name + " photo", "required": True,
     "upload": "family", "group": HOME, "section": "Scent families",
     "help": "Behind the tile's name, under a dark overlay so the white words stay readable. It is cropped to the "
             "tile's 4:3 at 900x675, and a 450 px copy is made from it."})
] + [
    text("/index/reels_link/label", "Link beside the films", HOME, 30, section="Product films",
         help="The films and their heading are under Homepage."),
    href("/index/reels_link/href", "Its link", HOME, section="Product films"),
]

# ---- collection page ----------------------------------------------------------

# The filter and sort values are code: shop.js reads a price band as its range
# and compares a gender with the products' own. Only the words are content.
PRICE_BANDS = (("0-49", "AED 0 to 49"), ("50-100", "AED 50 to 100"), ("100-200", "AED 100 to 200"),
               ("200-999999", "AED 200 and up"))
GENDERS = ("Him", "Her", "Unisex")
SORTS = (("featured", "Featured"), ("price-asc", "Price, low to high"), ("price-desc", "Price, high to low"),
         ("name", "Name, A to Z"))

_COLLECTION = [
    text("/collection/crumb_categories", "Breadcrumb for a category", COLLECTION, 30,
         help="A one-category page's breadcrumb reads the breadcrumb start, this, then the category's own "
              "breadcrumb name from Collections."),
    text("/collection/filters/heading", "Filters heading", COLLECTION, 20, section="Filters",
         help="On the filter button, above the filters, and on the filter drawer on phones."),
    text("/collection/filters/clear", "Clear all button", COLLECTION, 20, section="Filters"),
    text("/collection/filters/show", "Drawer button", COLLECTION, 40, section="Filters", pattern=COUNT,
         patternHelp=COUNT_HELP, help="Closes the filter drawer on phones. {n} is the number of products shown."),
    text("/collection/filters/category", "Category heading", COLLECTION, 30, section="Filters",
         help="The category names are under Collections."),
    text("/collection/filters/price", "Price heading", COLLECTION, 30, section="Filters"),
    text("/collection/filters/gender", "Gender heading", COLLECTION, 30, section="Filters"),
] + [
    text("/collection/price_bands/%s" % value, "Price band " + said, COLLECTION, 30, section="Filters",
         help="The band itself is fixed at %s; only its words change here." % said)
    for value, said in PRICE_BANDS
] + [
    text("/collection/genders/%s" % value, "Gender " + value, COLLECTION, 20, section="Filters",
         help="Finds the products whose gender is %s. The filter pill shows the same words." % value)
    for value in GENDERS
] + [
    text("/collection/count", "Product count", COLLECTION, 40, section="Sorting", pattern=COUNT, patternHelp=COUNT_HELP,
         help="Beside the sort menu. {n} is the number of products shown."),
] + [
    text("/collection/sort/%s" % value, "Sort: " + said, COLLECTION, 40, section="Sorting")
    for value, said in SORTS
] + [
    text("/collection/empty/title", "Heading", COLLECTION, 60, section="No results",
         help="When no product matches the filters."),
    text("/collection/empty/body", "Text", COLLECTION, 160, section="No results", kind="textarea"),
    text("/collection/empty/clear", "Button", COLLECTION, 30, section="No results"),
]

# ---- product page ---------------------------------------------------------------

# The tab ids are code: a link ending in ?tab=delivery or ?tab=apply opens the
# page on that tab. Only the words are content.
TABS = (("pyramid", "Scent pyramid tab", "On EDP sprays and attars."),
        ("apply", "How to apply tab", "On attars only."),
        ("ing", "Ingredients tab", None),
        ("delivery", "Delivery and returns tab",
         "A link ending in tab=delivery, like the footer's Delivery & returns, opens the product page on this tab."),
        ("reviews", "Reviews tab", None))
NOT_FILLED = "No product fills this row, so the page never shows it."

_PRODUCT = [
    text("/product/share/label", "Share button", PRODUCT, 20, section="Buy box"),
    text("/product/share/copied", "Share button after copying", PRODUCT, 30, section="Buy box",
         help="Where the browser has no share menu, the button copies the link and says this for a moment."),
    text("/product/share/failed", "Share button when copying fails", PRODUCT, 30, section="Buy box"),
    text("/product/size_label", "Size heading", PRODUCT, 20, section="Buy box"),
    text("/product/gift_cta/label", "Gift button", PRODUCT, 30, section="Buy box"),
    href("/product/gift_cta/href", "Gift button link", PRODUCT, section="Buy box"),
    text("/product/notes/top", "Notes strip: top", PRODUCT, 20, section="Buy box",
         help="The strip under the buttons, on products with notes."),
    text("/product/notes/heart", "Notes strip: heart", PRODUCT, 20, section="Buy box"),
    text("/product/notes/base", "Notes strip: base", PRODUCT, 20, section="Buy box"),
    text("/product/voucher_note", "Credit-back note", PRODUCT, 240, section="Buy box", kind="textarea",
         help="Only on products sold in 3 ml. The homepage's Discovery band describes the same voucher."),
    text("/product/facts/delivery_label", "Delivery fact heading", PRODUCT, 20, section="Buy box"),
    text("/product/facts/delivery", "Delivery fact", PRODUCT, 80, section="Buy box", pattern=tokens(*RULES),
         patternHelp=RULE_PATTERN_HELP,
         help=RULE_HELP + " The payment line under it is part of checkout and stays in code."),
    text("/product/specs/availability", "Availability row", PRODUCT, 30, section="Details",
         help="On products with a stock count."),
    text("/product/specs/in_stock", "In stock", PRODUCT, 30, section="Details"),
    text("/product/specs/only_left", "Low stock", PRODUCT, 30, section="Details", pattern=COUNT, patternHelp=COUNT_HELP,
         help="When the stock is at or below the low stock level in Settings. {n} is the number left."),
    text("/product/specs/barcode", "Barcode row", PRODUCT, 30, section="Details", help="On products with a barcode."),
    text("/product/specs/batch", "Batch number row", PRODUCT, 30, section="Details", rendered=False,
         notShown="The row shows only for a product with a barcode, and then reads as the barcode row."),
    text("/product/specs/longevity", "Longevity row", PRODUCT, 30, section="Details", rendered=False, notShown=NOT_FILLED),
    text("/product/specs/sillage", "Sillage row", PRODUCT, 30, section="Details", rendered=False, notShown=NOT_FILLED),
] + [
    text("/product/tabs/%s" % key, label, PRODUCT, 30, section="Tabs", help=help) for key, label, help in TABS
] + [
    text("/product/pyramid/top", "Top notes heading", PRODUCT, 20, section="Scent pyramid"),
    text("/product/pyramid/heart", "Heart notes heading", PRODUCT, 20, section="Scent pyramid"),
    text("/product/pyramid/base", "Base notes heading", PRODUCT, 20, section="Scent pyramid"),
    text("/product/pyramid/missing", "When a product has no notes", PRODUCT, 200, section="Scent pyramid",
         kind="textarea"),
    {"path": "/product/apply_steps", "type": "rows", "label": "Steps", "min": 1, "max": 6, "itemLabel": "title",
     "canAdd": True, "group": PRODUCT, "section": "How to apply", "help": "On attars only.", "fields": [
         {"path": "/title", "type": "text", "label": "Heading", "required": True, "maxLength": 30},
         {"path": "/body", "type": "textarea", "label": "Text", "required": True, "maxLength": 200},
     ]},
    text("/product/apply_note", "Note under the steps", PRODUCT, 200, section="How to apply", kind="textarea",
         help="It speaks for every blend in the shop, the sprays included, so keep it true of them all."),
    text("/product/ingredients/heading", "Ingredients heading", PRODUCT, 40, section="Ingredients",
         help="Above a product's declared ingredients, when it has them."),
    text("/product/ingredients/missing", "When a product has no ingredients", PRODUCT, 200, section="Ingredients",
         kind="textarea"),
    {"path": "/product/delivery_rows", "type": "rows", "label": "Delivery and returns", "min": 1, "max": 6,
     "itemLabel": "title", "canAdd": True, "group": PRODUCT, "section": "Delivery and returns", "help": RULE_HELP,
     "fields": [
         {"path": "/title", "type": "text", "label": "Heading", "required": True, "maxLength": 30},
         {"path": "/body", "type": "textarea", "label": "Text", "required": True, "maxLength": 200,
          "pattern": tokens(*RULES), "patternHelp": RULE_PATTERN_HELP},
     ]},
    text("/product/reviews_empty/title", "Heading", PRODUCT, 40, section="Reviews",
         help="The Reviews tab, while there are no reviews."),
    text("/product/reviews_empty/body", "Text", PRODUCT, 200, section="Reviews", kind="textarea"),
    text("/product/related/heading", "Heading", PRODUCT, 60, section="Related products",
         help="The row under the tabs, which shows the first four attars."),
    text("/product/related/link_label", "Link", PRODUCT, 30, section="Related products"),
    href("/product/related/link_href", "Its link", PRODUCT, section="Related products"),
    text("/product/not_found/title", "Heading", PRODUCT, 60, section="Product not found",
         help="When a product link names no product in the shop."),
    text("/product/not_found/cta", "Button", PRODUCT, 30, section="Product not found",
         help="It opens the collection page."),
    text("/product/not_found/crumb", "Breadcrumb", PRODUCT, 30, section="Product not found",
         help="After the breadcrumb start."),
    text("/product/not_found/page_title", "Tab title", PRODUCT, 60, section="Product not found",
         help="Followed by the title suffix from Settings."),
]

# ---- gift box ---------------------------------------------------------------------

# The box sizes (3 and 6), the six attars in the picker and the amounts are
# code and store rules; only the words are content.
_GIFT_BOX = [
    text("/gift_box/crumb", "Breadcrumb", GIFT_BOX, 40, section="Top of the page", help="After the breadcrumb start."),
    text("/gift_box/title", "Heading", GIFT_BOX, 60, section="Top of the page"),
    text("/gift_box/intro", "Intro", GIFT_BOX, 200, section="Top of the page", kind="textarea",
         help="It says the box leaves as one bag line, but the box's button only opens the bag for now: "
              "the box is not added to it yet."),
    text("/gift_box/size_label", "Size buttons", GIFT_BOX, 20, section="Slots", pattern=COUNT, patternHelp=COUNT_HELP,
         help="The two buttons that pick a box of 3 or 6 slots. {n} is the number of slots; the sizes are code."),
    text("/gift_box/slots/filled", "Filled slot", GIFT_BOX, 20, section="Slots", pattern=tokens("n"),
         patternHelp=only("n"), help="On a slot's picture once a scent is in it. {n} is the slot's number."),
    text("/gift_box/slots/remove", "Remove hint", GIFT_BOX, 30, section="Slots",
         help="After the scent's price on a filled slot."),
    text("/gift_box/slots/empty", "Empty slot", GIFT_BOX, 30, section="Slots", pattern=tokens("n"),
         patternHelp=only("n"), help="On an empty slot's picture. {n} is the slot's number."),
    text("/gift_box/slots/choose", "Empty slot heading", GIFT_BOX, 30, section="Slots"),
    text("/gift_box/slots/pick", "Empty slot hint", GIFT_BOX, 30, section="Slots"),
    text("/gift_box/picker_heading", "Picker heading", GIFT_BOX, 40, section="Slots",
         help="Above the scents a visitor can add: the first six attars in the shop's order."),
    text("/gift_box/summary/scents_one", "Scent count, one", GIFT_BOX, 30, section="Summary",
         pattern=COUNT, patternHelp=COUNT_HELP),
    text("/gift_box/summary/scents_many", "Scent count, more", GIFT_BOX, 30, section="Summary",
         pattern=COUNT, patternHelp=COUNT_HELP, help="Also for the empty box the page opens with, which reads 0."),
    text("/gift_box/summary/box_label", "Box fee row", GIFT_BOX, 30, section="Summary",
         help="The fee beside it is the gift box fee under Discounts."),
    text("/gift_box/summary/discount_label", "Discount row", GIFT_BOX, 60, section="Summary",
         pattern=tokens("box_at"), patternHelp=only("box_at"),
         help="{box_at} prints the number of scents the box discount starts at, such as 3 items, from Discounts."),
    text("/gift_box/summary/total_label", "Total row", GIFT_BOX, 20, section="Summary"),
    text("/gift_box/summary/fill_one", "Button, one slot left", GIFT_BOX, 40, section="Summary",
         pattern=COUNT, patternHelp=COUNT_HELP),
    text("/gift_box/summary/fill_many", "Button, slots left", GIFT_BOX, 40, section="Summary",
         pattern=COUNT, patternHelp=COUNT_HELP, help="{n} is the number of empty slots. The page opens with 3."),
    text("/gift_box/summary/add", "Button, box full", GIFT_BOX, 40, section="Summary",
         pattern=tokens("total"), patternHelp=only("total"),
         help="{total} prints the box's total. The button opens the bag, but the box is not added to it yet."),
    text("/gift_box/summary/full", "Button, no room left", GIFT_BOX, 40, section="Summary",
         help="Shown for a moment when a visitor tries to add a scent to a full box."),
    text("/gift_box/options_heading", "Heading", GIFT_BOX, 30, section="Gift options"),
    {"path": "/gift_box/options", "type": "rows", "label": "Options", "min": 1, "max": 6, "itemLabel": "label",
     "canAdd": True, "group": GIFT_BOX, "section": "Gift options",
     "help": "Words only: nothing on the page lets a visitor choose or pay for these yet. Keep each line true of "
             "what the shop does.",
     "fields": [
         {"path": "/label", "type": "text", "label": "Option", "required": True, "maxLength": 40},
         {"path": "/value", "type": "text", "label": "Price or setting", "required": True, "maxLength": 30},
         {"path": "/highlight", "type": "bool", "label": "Show it in green", "required": True},
     ]},
]

# ---- bag ------------------------------------------------------------------------------

# The sums, the rungs and the never-discount rule are the pricing engine's, in
# code; the bars' thresholds are store rules. Only the words are content.
_BAG = [
    text("/cart/title", "Heading", BAG, 30, section="Top of the page"),
    text("/cart/items/one", "Item count, one", BAG, 20, section="Top of the page", pattern=COUNT, patternHelp=COUNT_HELP,
         help="After the heading once the bag holds something."),
    text("/cart/items/many", "Item count, more", BAG, 20, section="Top of the page", pattern=COUNT, patternHelp=COUNT_HELP),
    text("/cart/continue/label", "Continue link", BAG, 30, section="Top of the page"),
    href("/cart/continue/href", "Its link", BAG, section="Top of the page"),
    text("/cart/progress/free_delivery", "Free delivery bar", BAG, 60, section="Progress bars",
         pattern=tokens(*RULES), patternHelp=RULE_PATTERN_HELP, help=RULE_HELP),
    text("/cart/progress/gift", "Free gift bar", BAG, 60, section="Progress bars",
         pattern=tokens("gift", "gift_over"), patternHelp=only("gift", "gift_over"),
         help="{gift} prints the free gift's name and {gift_over} the amount it needs, both from Discounts."),
    text("/cart/progress/unlocked", "Bar reached", BAG, 20, section="Progress bars",
         help="Beside a bar once the bag has reached it."),
    text("/cart/progress/to_go", "Bar not reached", BAG, 30, section="Progress bars",
         pattern=needs("amount"), patternHelp="Keep {amount}: it is where the amount still to spend goes."),
    text("/cart/progress/ladder_next", "Discount bar", BAG, 60, section="Progress bars",
         pattern=needs("n", "pct"), patternHelp="Keep {n}, the items still to add. {pct} is the next discount. "
                                                "Leave out any other braces.",
         help="The discount's rungs are under Discounts. With JavaScript off the bar keeps the rules' own wording."),
    text("/cart/progress/ladder_top", "Discount bar at the top", BAG, 60, section="Progress bars",
         pattern=tokens("pct"), patternHelp=only("pct"), help="{pct} is the top rung's discount."),
    text("/cart/progress/ladder_count", "Discount bar count", BAG, 20, section="Progress bars",
         pattern=needs("n", "goal"), patternHelp="Keep {n}, the items counted. {goal} is the next rung's. "
                                                 "Leave out any other braces."),
    text("/cart/line/no_image", "Line without a photo", BAG, 20, section="Bag lines"),
    text("/cart/line/remove", "Remove button", BAG, 20, section="Bag lines"),
    text("/cart/gift_line/placeholder", "Free gift picture", BAG, 20, section="Bag lines",
         help="The free gift's line has no photo; this word stands in its place."),
    text("/cart/gift_line/meta", "Free gift line", BAG, 60, section="Bag lines", pattern=tokens("amount"),
         patternHelp=only("amount"), help="Under the gift's name. {amount} prints the amount the gift needs."),
    text("/cart/never_discount_note", "Never-discounted note", BAG, 200, section="Bag lines", kind="textarea",
         help="Shown when the bag holds a never-discounted product. The code leaves those products out of the "
              "volume discount whatever this says."),
    text("/cart/empty/text", "Empty bag", BAG, 60, section="Empty bag"),
    text("/cart/empty/cta_label", "Button", BAG, 30, section="Empty bag"),
    href("/cart/empty/cta_href", "Its link", BAG, section="Empty bag"),
    text("/cart/summary/subtotal", "Subtotal row", BAG, 20, section="Summary",
         help="Also the bag row of the panel that opens after Add to bag."),
    text("/cart/summary/discount", "Volume discount row", BAG, 30, section="Summary",
         help="The rate after it follows the bag."),
    text("/cart/summary/delivery", "Delivery row", BAG, 20, section="Summary"),
    text("/cart/summary/free", "Free", BAG, 20, section="Summary",
         help="For free delivery, and for a bag line that costs nothing, such as the free gift."),
    text("/cart/summary/total", "Total row", BAG, 20, section="Summary",
         help="Also beside the total on the checkout bar a phone shows at the foot of the bag page."),
    text("/cart/summary/checkout", "Checkout button", BAG, 30, section="Summary",
         help="Also the Checkout button of the panel that opens after Add to bag, and of the checkout bar "
              "a phone shows at the foot of the bag page."),
    text("/cart/added/title", "Heading", BAG, 40, section="Added to bag panel",
         help="Opens after Add to bag on any page, with the product, the bag count and subtotal, a View bag "
              "button and the Summary Checkout button."),
    text("/cart/added/qty", "Quantity line", BAG, 20, section="Added to bag panel", pattern=COUNT,
         patternHelp=COUNT_HELP, help="Under the product name. {n} prints how many of it the bag now holds."),
    text("/cart/added/view_bag", "View bag button", BAG, 20, section="Added to bag panel"),
    text("/cart/added/close", "Close button", BAG, 20, section="Added to bag panel",
         help="Read out by screen readers; the button itself shows a cross."),
    text("/cart/added/button", "Add button, just pressed", BAG, 20, section="Added to bag panel",
         help="What an Add to bag button says for a moment after it is pressed."),
]

# ---- track order ------------------------------------------------------------------

# Nothing looks an order up yet: the replies say so, and the stages describe
# how orders will move once they are real.
_TRACK = [
    text("/track/crumb", "Breadcrumb", TRACK, 30, section="Top of the page", help="After the breadcrumb start."),
    text("/track/title", "Heading", TRACK, 60, section="Top of the page"),
    text("/track/intro", "Intro", TRACK, 200, section="Top of the page", kind="textarea"),
    text("/track/form/number", "Order number box", TRACK, 30, section="Form",
         help="The first box's hint, which screen readers also read as its name."),
    text("/track/form/phone", "Phone box", TRACK, 30, section="Form",
         help="The second box's hint. Screen readers call the box Phone number."),
    text("/track/form/button", "Button", TRACK, 30, section="Form"),
    text("/track/replies/missing", "Reply, both boxes empty", TRACK, 160, section="Form", kind="textarea"),
    text("/track/replies/looking", "Reply", TRACK, 240, section="Form", kind="textarea",
         pattern=tokens("query"), patternHelp=only("query"),
         help="{query} is what the visitor typed. Orders cannot be looked up yet, so keep the reply saying so."),
    text("/track/stages_heading", "Heading", TRACK, 40, section="Stages"),
    {"path": "/track/stages", "type": "rows", "label": "Stages", "min": 1, "max": 8, "itemLabel": "label",
     "canAdd": True, "group": TRACK, "section": "Stages",
     "help": "The steps an order goes through, in order. Nothing tracks an order yet, so these describe how "
             "orders will run. Check that each line, such as payment taken or picked at the kiosk, is how the "
             "shop works.",
     "fields": [
         {"path": "/label", "type": "text", "label": "Stage", "required": True, "maxLength": 30},
         {"path": "/body", "type": "text", "label": "What happens", "required": True, "maxLength": 80},
     ]},
    text("/track/whatsapp_note", "WhatsApp note", TRACK, 200, section="Stages", kind="textarea",
         help="Today's text puts the WhatsApp tick box on the confirmation page; it is on the checkout page."),
]

# ---- corporate ----------------------------------------------------------------------

# The form sends nothing yet. Its reply is built from whole phrases: the
# thanks, then the quote line, then the last sentence, joined with full stops.
STOP = "The reply puts a full stop and a space after it, so end it without one."
_CORPORATE = [
    text("/corporate/title", "Heading", CORPORATE, 40, section="Top of the page"),
    text("/corporate/intro", "Intro", CORPORATE, 160, section="Top of the page", kind="textarea",
         help="The bag caps each line at 20; nothing turns a larger order into a quote. The band and a "
              "homepage promo tile say the same."),
    {"path": "/corporate/tiers", "type": "rows", "label": "Tier cards", "min": 1, "max": 8, "itemLabel": "units",
     "canAdd": True, "group": CORPORATE, "section": "Tiers", "help": "The cards above the band. Four fit a row.",
     "fields": [
         {"path": "/units", "type": "text", "label": "Size", "required": True, "maxLength": 20},
         {"path": "/price", "type": "text", "label": "Price", "required": True, "maxLength": 20},
         {"path": "/note", "type": "text", "label": "Note", "required": True, "maxLength": 60},
     ]},
    text("/corporate/band/heading", "Heading", CORPORATE, 60, section="Band"),
    text("/corporate/band/body", "Text", CORPORATE, 240, section="Band", kind="textarea"),
    text("/corporate/band/cta_label", "Button", CORPORATE, 30, section="Band", help="It jumps to the form below."),
    text("/corporate/form/name", "Name box", CORPORATE, 30, section="Form",
         help="The box's hint, which screen readers also read as its name."),
    text("/corporate/form/email", "Email box", CORPORATE, 30, section="Form",
         help="The box's hint, which screen readers also read as its name."),
    text("/corporate/form/occasion", "Occasion box", CORPORATE, 40, section="Form",
         help="Screen readers call the box Occasion."),
    text("/corporate/form/units", "Units box", CORPORATE, 30, section="Form", help="Screen readers call the box Units."),
    text("/corporate/form/send", "Button", CORPORATE, 30, section="Form"),
    text("/corporate/replies/invalid_email", "Reply, email not valid", CORPORATE, 100, section="Replies"),
    text("/corporate/replies/thanks", "Thanks", CORPORATE, 30, section="Replies",
         help="When the visitor left the name box empty. " + STOP),
    text("/corporate/replies/thanks_name", "Thanks with a name", CORPORATE, 40, section="Replies",
         pattern=needs("name"), patternHelp="Keep {name}: it is where the visitor's name goes.", help=STOP),
    text("/corporate/replies/quote", "Quote line", CORPORATE, 60, section="Replies",
         help="When the visitor left the units box empty. " + STOP),
    text("/corporate/replies/quote_units", "Quote line with units", CORPORATE, 60, section="Replies",
         pattern=needs("n"), patternHelp="Keep {n}: it is where the number the visitor typed goes.", help=STOP),
    text("/corporate/replies/not_sent", "Last sentence", CORPORATE, 200, section="Replies", kind="textarea",
         help="The form sends nothing yet: keep this saying so until it does."),
]

# ---- account --------------------------------------------------------------------------

# A signed-in shopper's name, email and picture come from sign-in (Auth0);
# the rest of a customer's own details stay placeholders until the database
# arrives, and the account menu stays in code with them. Nothing runs the
# programme, the wallet or referrals yet, so these words describe what the
# shop means to offer.
PROMISE = "Nothing runs this yet, so it describes what the shop means to offer: keep it true of that."
SIGNIN = "Sign-in"
_ACCOUNT = [
    text("/account/crumb", "Breadcrumb", ACCOUNT, 30, section="Top of the page", help="After the breadcrumb start."),
    text("/account/programme", "Programme name", ACCOUNT, 30, section="Top of the page",
         help="In the badge beside the customer's name, the heading above the tiers and the account menu."),
    text("/account/signin/heading", "Heading", ACCOUNT, 60, section=SIGNIN,
         help="At the top of the page for a shopper who is not signed in, in place of the account."),
    text("/account/signin/body", "Sentence", ACCOUNT, 200, section=SIGNIN, kind="textarea",
         help="Under the heading. Auth0's page lists every way to sign in that is switched on there, "
              "so keep this true when one is added."),
    text("/account/signin/sign_in", "Sign in button", ACCOUNT, 30, section=SIGNIN, help="It opens Auth0's page to sign in."),
    text("/account/signin/create", "Create account button", ACCOUNT, 30, section=SIGNIN,
         help="It opens Auth0's page on its sign-up form."),
    text("/account/signin/sign_out", "Sign out button", ACCOUNT, 30, section=SIGNIN,
         help="On phones, under the shopper's name and email. The account menu's Sign out stays in code with the menu."),
    text("/account/signin/working", "While signing in", ACCOUNT, 60, section=SIGNIN,
         help="Shown for a moment after Auth0 sends the shopper back, while the shop finishes the sign-in."),
    text("/account/signin/cancelled", "Cancelled", ACCOUNT, 160, section=SIGNIN, kind="textarea",
         help="When Auth0 answers that the sign-in was cancelled or not allowed."),
    text("/account/signin/failed", "Did not work", ACCOUNT, 160, section=SIGNIN, kind="textarea",
         help="When a sign-in cannot be finished for any other reason."),
    text("/account/signin/unsupported", "Browser cannot sign in", ACCOUNT, 160, section=SIGNIN, kind="textarea",
         help="When the browser lacks what sign-in needs, as a very old one does."),
] + [
    f for key, label in (("drops", "Drops card"), ("credit", "Wallet credit card"), ("orders", "Orders card"))
    for f in (text("/account/stats/%s/label" % key, label, ACCOUNT, 30, section="Summary cards",
                   help="The number in the card is a placeholder until customers can sign in."),
              text("/account/stats/%s/note" % key, label + ", line under it", ACCOUNT, 80, section="Summary cards"))
] + [
    text("/account/loyalty/how_label", "Link beside the heading", ACCOUNT, 30, section="Programme",
         help="It goes nowhere yet."),
    {"path": "/account/loyalty/tiers", "type": "rows", "label": "Tiers", "min": 1, "max": 3, "itemLabel": "name",
     "canAdd": True, "group": ACCOUNT, "section": "Programme",
     "help": "The badge shows the first tier, where every customer starts. Three fit the row. " + PROMISE,
     "fields": [
         {"path": "/name", "type": "text", "label": "Tier", "required": True, "maxLength": 20},
         {"path": "/note", "type": "text", "label": "What it takes", "required": True, "maxLength": 30},
     ]},
    text("/account/loyalty/next_tier", "Line under the bar", ACCOUNT, 60, section="Programme",
         help="Written for a customer at the first tier: keep it in step with the second tier."),
    {"path": "/account/loyalty/perks", "type": "rows", "label": "Perks", "min": 1, "max": 6, "itemLabel": "label",
     "canAdd": True, "group": ACCOUNT, "section": "Programme", "help": PROMISE,
     "fields": [
         {"path": "/label", "type": "text", "label": "Perk", "required": True, "maxLength": 40},
         {"path": "/who", "type": "text", "label": "Who gets it", "required": True, "maxLength": 40},
     ]},
    text("/account/wallet/heading", "Heading", ACCOUNT, 30, section="Wallet"),
    text("/account/wallet/voucher_label", "Voucher row", ACCOUNT, 60, section="Wallet",
         help="The same voucher as the product page's credit-back note and the homepage's Discovery band."),
    text("/account/wallet/redeem_label", "Redeemable row", ACCOUNT, 30, section="Wallet"),
    text("/account/wallet/redeem", "Redeemable on", ACCOUNT, 60, section="Wallet"),
    text("/account/wallet/expires_label", "Expiry row", ACCOUNT, 30, section="Wallet"),
    text("/account/wallet/expires", "Expires", ACCOUNT, 60, section="Wallet"),
    text("/account/wallet/note", "Note", ACCOUNT, 200, section="Wallet", kind="textarea", help=PROMISE),
    text("/account/referral/heading", "Heading", ACCOUNT, 30, section="Referrals"),
    text("/account/referral/copy_label", "Copy button", ACCOUNT, 20, section="Referrals",
         help="Beside the customer's code, which is a placeholder. The button does nothing yet."),
    text("/account/referral/friend_label", "Friend row", ACCOUNT, 30, section="Referrals"),
    text("/account/referral/friend", "What the friend gets", ACCOUNT, 80, section="Referrals", help=PROMISE),
    text("/account/referral/you_label", "Customer row", ACCOUNT, 30, section="Referrals"),
    text("/account/referral/you", "What the customer gets", ACCOUNT, 80, section="Referrals", help=PROMISE),
    text("/account/referral/referred_label", "Count row", ACCOUNT, 30, section="Referrals"),
    text("/account/orders/heading", "Heading", ACCOUNT, 30, section="Orders"),
    text("/account/orders/track_label", "Tracking link", ACCOUNT, 30, section="Orders",
         help="It opens the order tracking page."),
    text("/account/orders/empty_title", "No orders", ACCOUNT, 40, section="Orders"),
    text("/account/orders/empty_body", "No orders, text", ACCOUNT, 200, section="Orders", kind="textarea"),
    text("/account/orders/cta_label", "Button", ACCOUNT, 30, section="Orders"),
    href("/account/orders/cta_href", "Its link", ACCOUNT, section="Orders"),
    text("/account/consent/heading", "Heading", ACCOUNT, 40, section="Details and consent"),
    text("/account/consent/phone_label", "Phone row", ACCOUNT, 20, section="Details and consent"),
    text("/account/consent/email_label", "Email row", ACCOUNT, 20, section="Details and consent"),
    text("/account/consent/language_label", "Language row", ACCOUNT, 20, section="Details and consent"),
    text("/account/consent/language", "Languages", ACCOUNT, 40, section="Details and consent"),
    text("/account/consent/order_updates", "First tick box", ACCOUNT, 60, section="Details and consent"),
    text("/account/consent/offers", "Second tick box", ACCOUNT, 60, section="Details and consent"),
    text("/account/consent/note", "Note", ACCOUNT, 240, section="Details and consent", kind="textarea",
         help="It describes consent records and a CRM the shop does not have yet."),
]

# ---- 404 ------------------------------------------------------------------------------

# The page carries its own style, so it looks the same at any address.
_NOT_FOUND = [
    text("/not_found/title", "Tab title", NOT_FOUND, 60,
         help="The browser tab's title, followed by the title suffix from Settings."),
    text("/not_found/heading", "Heading", NOT_FOUND, 60),
    text("/not_found/body", "Text", NOT_FOUND, 160, kind="textarea"),
    text("/not_found/button", "Button", NOT_FOUND, 40, help="It opens the homepage."),
]

# The four policy pages. Their words are the owner's legal text, so the fields
# are plain and roomy: the title, the date it carries, the words the footer
# links with, and the policy itself as lines.
_LEGAL = [
    text("/legal/shipping/title", "Shipping and delivery: title", LEGAL, 80, section="Shipping and delivery"),
    text("/legal/shipping/link_label", "Shipping and delivery: footer link", LEGAL, 40, section="Shipping and delivery",
         help="The words the footer links with. The link itself is under Navigation."),
    text("/legal/shipping/updated", "Shipping and delivery: last updated", LEGAL, 60, section="Shipping and delivery"),
    {"path": "/legal/shipping/body", "type": "lines", "label": "Shipping and delivery: the policy", "group": LEGAL, "section": "Shipping and delivery",
     "min": 1, "max": 200, "itemMaxLength": 1200,
     "help": "One line per paragraph. A line starting \"## \" is a heading, a line starting \"- \" is a point in a list."},
    text("/legal/returns/title", "Returns and refunds: title", LEGAL, 80, section="Returns and refunds"),
    text("/legal/returns/link_label", "Returns and refunds: footer link", LEGAL, 40, section="Returns and refunds",
         help="The words the footer links with. The link itself is under Navigation."),
    text("/legal/returns/updated", "Returns and refunds: last updated", LEGAL, 60, section="Returns and refunds"),
    {"path": "/legal/returns/body", "type": "lines", "label": "Returns and refunds: the policy", "group": LEGAL, "section": "Returns and refunds",
     "min": 1, "max": 200, "itemMaxLength": 1200,
     "help": "One line per paragraph. A line starting \"## \" is a heading, a line starting \"- \" is a point in a list."},
    text("/legal/privacy/title", "Privacy: title", LEGAL, 80, section="Privacy"),
    text("/legal/privacy/link_label", "Privacy: footer link", LEGAL, 40, section="Privacy",
         help="The words the footer links with. The link itself is under Navigation."),
    text("/legal/privacy/updated", "Privacy: last updated", LEGAL, 60, section="Privacy"),
    {"path": "/legal/privacy/body", "type": "lines", "label": "Privacy: the policy", "group": LEGAL, "section": "Privacy",
     "min": 1, "max": 200, "itemMaxLength": 1200,
     "help": "One line per paragraph. A line starting \"## \" is a heading, a line starting \"- \" is a point in a list."},
    text("/legal/terms/title", "Terms and conditions: title", LEGAL, 80, section="Terms and conditions"),
    text("/legal/terms/link_label", "Terms and conditions: footer link", LEGAL, 40, section="Terms and conditions",
         help="The words the footer links with. The link itself is under Navigation."),
    text("/legal/terms/updated", "Terms and conditions: last updated", LEGAL, 60, section="Terms and conditions"),
    {"path": "/legal/terms/body", "type": "lines", "label": "Terms and conditions: the policy", "group": LEGAL, "section": "Terms and conditions",
     "min": 1, "max": 200, "itemMaxLength": 1200,
     "help": "One line per paragraph. A line starting \"## \" is a heading, a line starting \"- \" is a point in a list."},
]

FIELDS = (_SHELL + _HOME + _COLLECTION + _PRODUCT + _GIFT_BOX + _BAG + _TRACK + _CORPORATE + _ACCOUNT + _LEGAL
          + _NOT_FOUND)

# A text with no {token} of its own takes no brace at all, rows' parts
# included: the build refuses one, so the field refuses it first, where the
# owner can see which text it is.
PLAIN = r"[^{}]*"
PLAIN_HELP = "This text takes no {tokens}; leave out braces."
for _f in FIELDS:
    for _g in [_f] + _f.get("fields", []):
        if _g["type"] in ("text", "textarea") and "pattern" not in _g:
            _g.update(pattern=PLAIN, patternHelp=PLAIN_HELP)
