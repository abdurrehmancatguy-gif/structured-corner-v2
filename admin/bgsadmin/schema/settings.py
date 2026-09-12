"""Store settings (flow/content/settings.json).

Payments, tax and cash on delivery belong to checkout, which stays locked in
code: the server refuses any change to them, however it is sent.
"""
RESOURCE = {"name": "settings", "label": "Settings", "kind": "document",
            "intro": "Store details, delivery rules and brand. Payments, tax and cash on delivery are locked: a developer changes those in code."}

NOT_SHOWN = "Saved, but the shop does not use this yet: the site still has it written into its code."
CHECKOUT = "Part of checkout and payments, which a developer changes in code."
UPLOAD = "Not changeable from the admin yet: there is no upload for the link preview picture."
LOGO = "A PNG with a transparent background, at least 486 px wide; the pages show a copy 486 px wide. The logo it replaces goes to the trash."
ICON = "Made from the emblem: upload a new one at Favicon above."
LOGIN = "Arrives with login: a tracking ID adds a third-party script to every page."

FIELDS = [
    {"path": "/store/name", "type": "text", "label": "Store name", "required": True, "maxLength": 60, "group": "Store details"},
    {"path": "/store/legal_name", "type": "text", "label": "Legal name", "maxLength": 80, "group": "Store details", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/location", "type": "text", "label": "Location", "maxLength": 60, "group": "Store details", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/currency", "type": "text", "label": "Currency", "group": "Store details", "locked": "The shop sells in one currency, AED."},
    # The rules below are printed on the pages and applied by shop.js, which
    # reads them from catalogue.js (window.BGS_RULES). Cross-field checks (the
    # cutoff's hours, the ladder's order) are in validate.py.
    {"path": "/store/free_delivery_over", "type": "int", "label": "Free delivery over (AED)", "required": True, "min": 0, "max": 2000, "group": "Shipping and delivery",
     "help": "The bag delivers free from this subtotal."},
    {"path": "/store/delivery_fee", "type": "int", "label": "Delivery fee (AED)", "required": True, "min": 0, "max": 500, "group": "Shipping and delivery",
     "help": "Charged on a bag below the free delivery amount."},
    {"path": "/store/sameday_fee", "type": "int", "label": "Same-day fee (AED)", "required": True, "min": 0, "max": 500, "group": "Shipping and delivery"},
    {"path": "/store/sameday_cutoff", "type": "text", "label": "Same-day cutoff (Dubai time)", "required": True, "group": "Shipping and delivery",
     "pattern": r"(1[0-2]|[1-9]):[0-5]\d (AM|PM)", "patternHelp": "Like 2:00 PM.",
     "help": "Between 6:00 AM and 10:00 PM. The top strip counts down to it."},
    {"path": "/store/giftbox_fee", "type": "int", "label": "Gift box fee (AED)", "required": True, "min": 0, "max": 500, "group": "Gift box"},
    {"path": "/store/giftbox_volume_discount_at", "type": "int", "label": "Box discount from this many scents", "required": True, "min": 1, "max": 6, "group": "Gift box",
     "help": "The gift box holds three or six scents, so a discount above six could never apply."},
    {"path": "/store/giftbox_volume_discount_percent", "type": "int", "label": "Box discount (%)", "required": True, "min": 0, "max": 50, "group": "Gift box"},
    {"path": "/store/volume_ladder", "type": "rows", "label": "Volume ladder", "min": 1, "max": 4, "itemLabel": "units", "canAdd": True, "group": "Volume discount",
     "help": "Each rung takes a percentage off the bag once it holds that many items. Never-discounted products neither count nor get the discount.",
     "fields": [
         {"path": "/units", "type": "int", "label": "From this many items", "required": True, "min": 1, "max": 100},
         {"path": "/percent", "type": "int", "label": "Discount (%)", "required": True, "min": 0, "max": 50},
     ]},
    {"path": "/store/gift_with_purchase/threshold", "type": "int", "label": "Free gift from (AED)", "required": True, "min": 1, "max": 2000, "group": "Gift with purchase",
     "help": "The bag adds the gift once its subtotal reaches this."},
    {"path": "/store/gift_with_purchase/label", "type": "text", "label": "Gift", "required": True, "maxLength": 40, "group": "Gift with purchase",
     "help": "As the bag lists it, like Mystery oud, 3 ml. The bag's progress bar uses the part before the comma."},
    {"path": "/store/low_stock_at", "type": "int", "label": "Low stock at or below", "required": True, "min": 0, "max": 50, "group": "Stock",
     "help": "Cards show 'N left' and product pages 'Only N left' when a product's stock is this or lower."},
    {"path": "/store/vat_rate_percent", "type": "int", "label": "VAT (%)", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/store/vat_inclusive", "type": "bool", "label": "Prices include VAT", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/store/cod_max_order", "type": "int", "label": "Cash on delivery up to (AED)", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/store/cod_fee", "type": "int", "label": "Cash on delivery fee (AED)", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/payments/card", "type": "bool", "label": "Card", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/payments/apple_pay", "type": "bool", "label": "Apple Pay", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/payments/tabby", "type": "bool", "label": "Tabby", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/payments/tamara", "type": "bool", "label": "Tamara", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/payments/cod", "type": "bool", "label": "Cash on delivery", "group": "Payments and tax", "locked": CHECKOUT},
    {"path": "/brand/logo_alt", "type": "text", "label": "Logo description (alt text)", "maxLength": 60, "group": "Brand"},
    {"path": "/brand/logo", "type": "image", "label": "Logo", "group": "Brand", "upload": "logo-dark", "help": LOGO + " This one is on the header."},
    {"path": "/brand/logo_light", "type": "image", "label": "Logo on dark", "group": "Brand", "upload": "logo-light", "help": LOGO + " This one is on the footer."},
    {"path": "/brand/suffix", "type": "text", "label": "Wordmark suffix", "group": "Brand", "rendered": False, "notShown": NOT_SHOWN, "maxLength": 20},
    {"path": "/brand/icons/ico", "type": "image", "label": "Favicon", "group": "Brand", "upload": "emblem",
     "help": "The site icons are all made from one emblem: a PNG with a transparent background, at least 180 px on its long side. "
             "Uploading a new emblem makes this favicon and the three icons below again; the emblem it replaces goes to the trash."},
    {"path": "/brand/icons/png32", "type": "image", "label": "Favicon 32 px", "group": "Brand", "upload": "icon", "help": ICON},
    {"path": "/brand/icons/png16", "type": "image", "label": "Favicon 16 px", "group": "Brand", "upload": "icon", "help": ICON},
    {"path": "/brand/icons/apple", "type": "image", "label": "Home screen icon", "group": "Brand", "upload": "icon", "help": ICON},
    {"path": "/seo/og_image", "type": "image", "label": "Link preview image", "group": "Search and sharing", "readonly": UPLOAD},
    {"path": "/seo/default_title_suffix", "type": "text", "label": "Title suffix", "maxLength": 40, "group": "Search and sharing", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/seo/default_description", "type": "textarea", "label": "Default description", "maxLength": 160, "group": "Search and sharing", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/social/instagram", "type": "href", "social": True, "label": "Instagram", "group": "Social", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/social/whatsapp", "type": "href", "social": True, "label": "WhatsApp", "group": "Social", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/social/tiktok", "type": "href", "social": True, "label": "TikTok", "group": "Social", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/analytics/ga4_id", "type": "text", "label": "Google Analytics", "group": "Analytics", "locked": LOGIN},
    {"path": "/analytics/meta_pixel_id", "type": "text", "label": "Meta pixel", "group": "Analytics", "locked": LOGIN},
    {"path": "/analytics/tiktok_pixel_id", "type": "text", "label": "TikTok pixel", "group": "Analytics", "locked": LOGIN},
    {"path": "/languages/english", "type": "bool", "label": "English", "group": "Languages", "locked": "The shop is written in English."},
    {"path": "/languages/arabic", "type": "bool", "label": "Arabic", "group": "Languages", "rendered": False, "notShown": NOT_SHOWN},
]
