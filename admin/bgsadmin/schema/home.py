"""The homepage (flow/content/home.json)."""
RESOURCE = {"name": "home", "label": "Homepage", "kind": "document"}

NOT_SHOWN = "Saved, but the shop does not use this yet: the site still has it written into its code."
UPLOAD = "New banner images and films arrive with the media stage; duplicate a slide to start from its picture."

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
    {"path": "/reels/title", "type": "text", "label": "Heading", "maxLength": 60, "group": "Product films"},
    {"path": "/reels/items", "type": "rows", "label": "Films", "max": 12, "itemLabel": "product", "canAdd": False,
     "group": "Product films", "help": "Each film links to its product. " + UPLOAD, "fields": [
         {"path": "/product", "type": "product-ref", "label": "Product", "required": True},
         {"path": "/video", "type": "video", "label": "Film", "readonly": UPLOAD},
         {"path": "/still", "type": "image", "label": "Poster", "readonly": UPLOAD},
     ]},
    {"path": "/sections/house_ouds", "type": "text", "label": "Attars shelf heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sections/reserve", "type": "text", "label": "Never discounted heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sections/gift_sets", "type": "text", "label": "Gift sets heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sections/scent_family", "type": "text", "label": "Scent family heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sections/bakhoor", "type": "text", "label": "Bakhoor heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sections/edp", "type": "text", "label": "EDP heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/sections/delivered_today", "type": "text", "label": "Delivered today heading", "maxLength": 60, "group": "Section headings", "rendered": False, "notShown": NOT_SHOWN},
]
