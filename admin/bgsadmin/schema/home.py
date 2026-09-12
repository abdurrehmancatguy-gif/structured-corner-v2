"""The homepage (flow/content/home.json)."""
RESOURCE = {"name": "home", "label": "Homepage", "kind": "document",
            "intro": "The homepage banner, the product films, and each shelf's heading, size and see-all link."}

NOT_SHOWN = "Saved, but the shop does not use this yet: the site still has it written into its code."
UPLOAD = "New banner images and films arrive with the media stage; duplicate a slide to start from its picture."

# The product shelves in the order the homepage shows them: id (the key in
# home.json "sections" and "shelves"), name, the category it draws from (None:
# the never-discounted products) and where its see-all link goes. Which
# products a shelf draws from and the link's address are code (build.py
# SHELVES); the heading, the number of cards and the link's words are content.
SHELVES = (
    ("house_ouds", "Attars shelf", "attars", "collection.html?cat=attars"),
    ("reserve", "Never discounted shelf", None, "collection.html?cat=attars"),
    ("gift_sets", "Gift sets shelf", "gift-sets", "collection.html?cat=gift-sets"),
    ("bakhoor", "Bakhoor shelf", "bakhoor", "collection.html?cat=bakhoor"),
    ("edp", "EDP shelf", "edp", "collection.html?cat=edp"),
)
LINK_PATTERN = r"(?:[^{}]|\{n\})*"


def _shelf(key, name, cat, href):
    source = "never-discounted products" if cat is None else "products in the category"
    return [
        {"path": "/sections/%s" % key, "type": "text", "label": "Heading", "required": True, "maxLength": 60, "group": name},
        {"path": "/shelves/%s/limit" % key, "type": "int", "label": "Cards on the shelf", "nullable": True,
         "nullableLabel": "Limit to", "min": 1, "max": 20, "group": name,
         "help": "The first published %s, in the shop's order. Without a limit the shelf shows them all." % source},
        {"path": "/shelves/%s/link_label" % key, "type": "text", "label": "See-all link", "required": True, "maxLength": 30,
         "pattern": LINK_PATTERN, "patternHelp": "Write {n} where the number goes; leave out any other braces.",
         "group": name,
         "help": "It goes to %s. Write {n} for the number of published %s; the build counts them." % (href, source)},
    ]


def _shelves(upto=None, start=None):
    keys = [s[0] for s in SHELVES]
    lo = keys.index(start) if start else 0
    hi = keys.index(upto) + 1 if upto else len(keys)
    return [f for s in SHELVES[lo:hi] for f in _shelf(*s)]


FIELDS = [
    {"path": "/hero_slides", "type": "rows", "label": "Banner slides", "min": 1, "max": 8, "itemLabel": "headline",
     "canAdd": False, "group": "Banner", "help": "The banner turns through these in order. " + UPLOAD, "fields": [
         {"path": "/eyebrow", "type": "text", "label": "Small heading", "maxLength": 60},
         {"path": "/headline", "type": "textarea", "label": "Headline", "required": True, "maxLength": 80, "multiline": True,
          "help": "Press Enter where the line should break."},
         {"path": "/body", "type": "textarea", "label": "Text", "maxLength": 200},
         {"path": "/primary/label", "type": "text", "label": "First button", "maxLength": 30},
         {"path": "/primary/href", "type": "href", "label": "First button link"},
         {"path": "/secondary/label", "type": "text", "label": "Second button", "maxLength": 30},
         {"path": "/secondary/href", "type": "href", "label": "Second button link"},
         {"path": "/image", "type": "image", "label": "Picture", "readonly": UPLOAD},
         {"path": "/image_alt", "type": "text", "label": "Picture description (alt text)", "maxLength": 120},
     ]},
] + _shelves(upto="gift_sets") + [
    {"path": "/sections/scent_family", "type": "text", "label": "Heading", "required": True, "maxLength": 60, "group": "Scent families"},
] + _shelves(start="bakhoor") + [
    {"path": "/reels/title", "type": "text", "label": "Heading", "maxLength": 60, "group": "Product films"},
    {"path": "/reels/items", "type": "rows", "label": "Films", "max": 12, "itemLabel": "product", "canAdd": False,
     "group": "Product films", "help": "Each film links to its product. " + UPLOAD, "fields": [
         {"path": "/product", "type": "product-ref", "label": "Product", "required": True},
         {"path": "/video", "type": "video", "label": "Film", "readonly": UPLOAD},
         {"path": "/still", "type": "image", "label": "Poster", "readonly": UPLOAD},
     ]},
    {"path": "/sections/delivered_today", "type": "text", "label": "Delivered today heading", "maxLength": 60, "group": "Unused", "rendered": False,
     "notShown": "No section on the homepage uses this heading."},
]
