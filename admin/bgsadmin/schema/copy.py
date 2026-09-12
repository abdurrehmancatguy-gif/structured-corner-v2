"""Site copy (flow/content/copy.json)."""
RESOURCE = {"name": "copy", "label": "Site text", "kind": "document"}

NOT_SHOWN = "Saved, but the shop does not use this yet: the site still has it written into its code."

FIELDS = [
    {"path": "/usp", "type": "rows", "label": "Promises under the banner", "min": 1, "max": 6, "itemLabel": "title",
     "canAdd": True, "group": "Homepage strip", "fields": [
         {"path": "/title", "type": "text", "label": "Headline", "required": True, "maxLength": 40},
         {"path": "/sub", "type": "text", "label": "Detail", "maxLength": 60},
         {"path": "/icon", "type": "icon", "label": "Icon"},
     ]},
    {"path": "/quiz_banner/eyebrow", "type": "text", "label": "Small heading", "maxLength": 50, "group": "Scent quiz banner"},
    {"path": "/quiz_banner/heading", "type": "text", "label": "Heading", "maxLength": 60, "group": "Scent quiz banner"},
    {"path": "/quiz_banner/body", "type": "textarea", "label": "Text", "maxLength": 240, "group": "Scent quiz banner"},
    {"path": "/quiz_banner/cta_label", "type": "text", "label": "Button", "maxLength": 30, "group": "Scent quiz banner"},
    {"path": "/quiz_banner/cta_href", "type": "href", "label": "Button link", "group": "Scent quiz banner"},
    {"path": "/strip/countdown_line", "type": "text", "label": "Top strip line", "maxLength": 80, "group": "Top strip", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/strip/right_links", "type": "rows", "label": "Top strip links", "max": 4, "itemLabel": "label", "canAdd": True,
     "group": "Top strip", "rendered": False, "notShown": NOT_SHOWN, "fields": [
         {"path": "/label", "type": "text", "label": "Text", "required": True, "maxLength": 40},
         {"path": "/href", "type": "href", "label": "Link (empty for plain text)"},
     ]},
    {"path": "/search_placeholder", "type": "text", "label": "Search box hint", "maxLength": 40, "group": "Header", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/collection_intros/all", "type": "textarea", "label": "All products", "maxLength": 200, "group": "Collection intros", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/collection_intros/attars", "type": "textarea", "label": "Attars", "maxLength": 200, "group": "Collection intros", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/collection_intros/bakhoor", "type": "textarea", "label": "Bakhoor", "maxLength": 200, "group": "Collection intros", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/collection_intros/edp", "type": "textarea", "label": "EDP sprays", "maxLength": 200, "group": "Collection intros", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/collection_intros/gift-sets", "type": "textarea", "label": "Gift sets", "maxLength": 200, "group": "Collection intros", "rendered": False, "notShown": NOT_SHOWN},
]
