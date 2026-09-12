"""Page text (flow/content/pages.json): the words of the header and footer
every page shares, the homepage's bands, the collection page and the product
page.

Fields are grouped by page ("group") and, inside a long page, by the part of
it they belong to ("section"), so the Pages screen can show one page at a
time. The top strip and the search hint are under Site text; the legal name,
the location and the tab-title suffix are under Settings.
"""
RESOURCE = {"name": "pages", "label": "Pages", "kind": "document",
            "intro": "The words on the shop's pages: the header and footer every page shares, the homepage's bands, "
                     "and the collection and product pages."}

SHELL, HOME, COLLECTION, PRODUCT = "Every page", "Homepage", "Collection page", "Product page"

# Some texts carry a {token} the build fills in; a field's pattern names the
# ones it may use, so any other brace is refused before it reaches the site.
RULES = ("free_over", "delivery_fee", "sameday_fee", "cutoff", "cutoff_short")
RULE_HELP = ("{free_over} prints the free delivery threshold, {delivery_fee} the delivery fee, {sameday_fee} the "
             "same-day fee, {cutoff} the same-day cutoff written like 2:00 PM and {cutoff_short} written like 2 PM. "
             "They come from Settings, so the text follows a change there.")
RULE_PATTERN_HELP = "Use only {free_over}, {delivery_fee}, {sameday_fee}, {cutoff} or {cutoff_short}; leave out any other braces."
COUNT = r"[^{}]*\{n\}[^{}]*"
COUNT_HELP = "Keep {n} once: it is where the number goes."


def tokens(*names):
    """A pattern that allows the named {tokens} and no other brace."""
    return r"(?:[^{}]|\{(?:%s)\})*" % "|".join(names)


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
         help="The first step of the breadcrumbs on the collection and product pages."),
    text("/shell/header/account", "Account link", SHELL, 20, section="Header"),
    text("/shell/header/wishlist", "Wishlist link", SHELL, 20, section="Header",
         help="It opens the account page, which has no wishlist yet."),
    text("/shell/header/bag", "Bag link", SHELL, 20, section="Header"),
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

# The scent family tiles: their links, colours and drawings are code; only the
# words are content.
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
] + [
    text("/index/families/%s" % slug, name + " tile", HOME, 30, section="Scent families",
         help="The tile opens the collection page, which does not filter by family yet, so it shows every product.")
    for slug, name in FAMILIES
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

FIELDS = _SHELL + _HOME + _COLLECTION + _PRODUCT
