"""Product fields, as flow/content/products.json holds them.

rendered False marks fields that are saved but that build.py and shop.js do
not read yet (docs/CONTENT-MODEL.md); the editor badges them so nobody
expects a change on the site.
"""
RESOURCE = {"name": "products", "label": "Products", "kind": "collection"}

NOT_SHOWN = "Saved, but the shop does not show this yet."
ALL = ["attars", "edp", "bakhoor", "gift-sets"]
# A product photo is <id>-<n>.jpg. Never a banner, and never a name a sized
# copy also has (-600, -card-360): make_derivatives and build.py would take
# one for the other.
FRAME = r"(?!banner-)(?!.*-card-360\.jpg$)[a-z0-9]+(?:-[a-z0-9]+)*-(?!600\.jpg$)[0-9]+\.jpg"

FIELDS = [
    {"path": "/name", "type": "text", "label": "Title", "required": True, "maxLength": 60},
    {"path": "/category", "type": "enum", "label": "Category", "required": True, "enum": ALL,
     # the names the shop shows today (navigation.json); the stored keys stay as they are
     "enumLabels": ["Oud Attar", "EDP Sprays", "Bakhoor", "Gift Sets"],
     "help": "The category decides which fields the card and the product page use."},
    {"path": "/published", "type": "bool", "label": "Active", "required": True,
     "help": "Off is a draft: gone from the shop at the next save. It is still readable in the public GitHub repository."},
    {"path": "/price", "type": "money", "label": "Price (AED)", "required": True, "max": 100000,
     "help": "For attars this is the size the card shows first, and must match one of the sizes below."},
    {"path": "/sizes", "type": "rows", "label": "Sizes", "visibleWhen": {"category": ["attars"]}, "min": 1, "max": 4,
     "itemLabel": "label", "canAdd": True,
     "help": "Heads up: the bag currently charges the price above whichever size a customer picks (a known issue in the locked cart code).",
     "fields": [
         {"path": "/label", "type": "text", "label": "Size", "required": True, "maxLength": 20},
         {"path": "/price", "type": "money", "label": "Price (AED)", "required": True, "max": 100000},
     ]},
    {"path": "/size", "type": "text", "label": "Size", "visibleWhen": {"category": ["edp", "bakhoor"]}, "maxLength": 20,
     "help": "As written on the card, for example 50 ml or 40 g."},
    {"path": "/contents", "type": "text", "label": "What is in the set", "visibleWhen": {"category": ["gift-sets"]}, "maxLength": 60},
    {"path": "/gender", "type": "enum", "label": "Worn by", "visibleWhen": {"category": ["edp"]}, "enum": ["Him", "Her", "Unisex"]},
    {"path": "/stock", "type": "int", "label": "Stock", "nullable": True, "min": 0, "max": 100000,
     "help": "Leave empty to not track stock. At 5 or fewer the card shows how many are left."},
    {"path": "/never_discount", "type": "bool", "label": "Never discounted", "guarded": True, "required": True,
     "help": "Shows the Reserve badge and keeps the product out of every volume discount."},
    {"path": "/story", "type": "lines", "label": "Story", "max": 6, "itemMaxLength": 140,
     "help": "Up to six short lines, shown on the product page."},
    {"path": "/top", "type": "text", "label": "Top notes", "visibleWhen": {"category": ["edp", "attars"]}, "maxLength": 120},
    {"path": "/heart", "type": "text", "label": "Heart notes", "visibleWhen": {"category": ["edp", "attars"]}, "maxLength": 120},
    {"path": "/base", "type": "text", "label": "Base notes", "visibleWhen": {"category": ["edp", "attars"]}, "maxLength": 120, "nullable": True},
    {"path": "/ingredients", "type": "textarea", "label": "Declared ingredients", "maxLength": 600},
    {"path": "/barcode", "type": "text", "label": "Barcode", "pattern": r"[0-9]{8,14}", "patternHelp": "8 to 14 digits."},
    {"path": "/images", "type": "images", "label": "Photos", "itemPattern": FRAME,
     "patternHelp": "Use a photo from the library, named like vibe-3.jpg.",
     "copies": ["", "-card", "-600", "-card-360", "-thumb"],
     "help": "The first photo is the card picture and the first on the product page; the second shows when a shopper points at the card."},
    {"path": "/order", "type": "int", "label": "Position", "min": 0, "max": 100000,
     "readonly": "Change the position by reordering in the product list."},
    {"path": "/name_ar", "type": "text", "label": "Name in Arabic", "dir": "rtl", "maxLength": 60, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/story_ar", "type": "lines", "label": "Story in Arabic", "dir": "rtl", "max": 6, "itemMaxLength": 140, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/family", "type": "text", "label": "Scent family", "maxLength": 40, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/tone", "type": "text", "label": "Tone", "maxLength": 40, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/occasion", "type": "text", "label": "Occasion", "maxLength": 40, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/season", "type": "text", "label": "Season", "maxLength": 40, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/longevity", "type": "text", "label": "Longevity", "maxLength": 40, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sillage", "type": "text", "label": "Sillage", "maxLength": 40, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/badge", "type": "text", "label": "Badge", "maxLength": 20, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/seo_title", "type": "text", "label": "Search engine title", "maxLength": 70, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/seo_description", "type": "textarea", "label": "Search engine description", "maxLength": 160, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/image_alt", "type": "text", "label": "Photo description (alt text)", "maxLength": 120, "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/related", "type": "product-refs", "label": "Related products", "max": 4, "rendered": False, "notShown": NOT_SHOWN},
]
