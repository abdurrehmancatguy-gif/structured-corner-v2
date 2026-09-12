"""Store settings (flow/content/settings.json).

Payments, tax and cash on delivery belong to checkout, which stays locked in
code: the server refuses any change to them, however it is sent.
"""
RESOURCE = {"name": "settings", "label": "Settings", "kind": "document",
            "intro": "Store details, delivery rules and brand. Payments, tax and cash on delivery are locked: a developer changes those in code."}

NOT_SHOWN = "Saved, but the shop does not use this yet: the site still has it written into its code."
CHECKOUT = "Part of checkout and payments, which a developer changes in code."
UPLOAD = "Changed by uploading a new file, which arrives with the media stage."
LOGIN = "Arrives with login: a tracking ID adds a third-party script to every page."

FIELDS = [
    {"path": "/store/name", "type": "text", "label": "Store name", "required": True, "maxLength": 60, "group": "Store details"},
    {"path": "/store/legal_name", "type": "text", "label": "Legal name", "maxLength": 80, "group": "Store details", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/location", "type": "text", "label": "Location", "maxLength": 60, "group": "Store details", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/currency", "type": "text", "label": "Currency", "group": "Store details", "locked": "The shop sells in one currency, AED."},
    {"path": "/store/free_delivery_over", "type": "int", "label": "Free delivery over (AED)", "min": 0, "max": 2000, "group": "Shipping and delivery", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/delivery_fee", "type": "int", "label": "Delivery fee (AED)", "min": 0, "max": 500, "group": "Shipping and delivery", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/sameday_fee", "type": "int", "label": "Same-day fee (AED)", "min": 0, "max": 500, "group": "Shipping and delivery", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/sameday_cutoff", "type": "text", "label": "Same-day cutoff (Dubai time)", "group": "Shipping and delivery",
     "pattern": r"(1[0-2]|[1-9]):[0-5]\d (AM|PM)", "patternHelp": "Like 2:00 PM.", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/giftbox_fee", "type": "int", "label": "Gift box fee (AED)", "min": 0, "max": 500, "group": "Gift box", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/giftbox_volume_discount_at", "type": "int", "label": "Box discount from this many scents", "min": 1, "max": 12, "group": "Gift box", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/store/giftbox_volume_discount_percent", "type": "int", "label": "Box discount (%)", "min": 0, "max": 50, "group": "Gift box", "rendered": False, "notShown": NOT_SHOWN},
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
    {"path": "/brand/logo", "type": "image", "label": "Logo", "group": "Brand", "readonly": UPLOAD},
    {"path": "/brand/logo_light", "type": "image", "label": "Logo on dark", "group": "Brand", "readonly": UPLOAD},
    {"path": "/brand/suffix", "type": "text", "label": "Wordmark suffix", "group": "Brand", "rendered": False, "notShown": NOT_SHOWN, "maxLength": 20},
    {"path": "/brand/icons/ico", "type": "image", "label": "Favicon", "group": "Brand", "readonly": UPLOAD},
    {"path": "/brand/icons/png32", "type": "image", "label": "Favicon 32 px", "group": "Brand", "readonly": UPLOAD},
    {"path": "/brand/icons/png16", "type": "image", "label": "Favicon 16 px", "group": "Brand", "readonly": UPLOAD},
    {"path": "/brand/icons/apple", "type": "image", "label": "Home screen icon", "group": "Brand", "readonly": UPLOAD},
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
