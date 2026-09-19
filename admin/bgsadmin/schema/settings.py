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
LOGO_UNUSED = ("Saved, but the header and the footer now show the emblem and the wordmark as text; "
               "this picture comes back only if the wordmark is left empty.")
EMBLEM = "The emblem is replaced with the Favicon upload below, which makes the site icons from it too."
ICON = "Made from the emblem: upload a new one at Favicon above."
LOGIN = "Arrives with login: a tracking ID adds a third-party script to every page."
# Shopper sign-in runs on Auth0. Both values come from the "bgs-corner"
# application's Settings tab and are public: every shopper's browser reads
# them. The application is a Single Page Application, which has no client
# secret, so there is no field for one. build.py checks the same two patterns
# and validate.py that both are set or both are empty.
SIGNIN = "Shopper sign-in"
SIGNIN_HELP = "Shoppers sign in and create accounts on Auth0's page for this shop. Leave this and the Client ID empty and the shop shows no sign-in."
AUTH_DOMAIN = r"(?=.{4,100}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"
AUTH_CLIENT_ID = r"[A-Za-z0-9]{20,40}"

FIELDS = [
    {"path": "/store/name", "type": "text", "label": "Store name", "required": True, "maxLength": 60, "group": "Store details"},
    {"path": "/store/legal_name", "type": "text", "label": "Legal name", "maxLength": 80, "group": "Store details",
     "help": "In every page's footer, before the location, and in its copyright line. Left empty, the footer uses the store name."},
    {"path": "/store/location", "type": "text", "label": "Location", "maxLength": 60, "group": "Store details",
     "help": "In every page's footer, after the legal name."},
    {"path": "/store/currency", "type": "text", "label": "Currency", "group": "Store details", "locked": "The shop sells in one currency, AED."},
    # Where the shop is served. build.py writes it into every page's canonical
    # link and its social picture, and the admin's "View on store" links point
    # at it: without it they point at the admin's own address, which serves no
    # shop pages once the admin is somewhere else.
    {"path": "/site_url", "type": "text", "label": "The shop's address", "maxLength": 120, "group": "Store details",
     "pattern": r"https://[a-z0-9.-]+[a-z]", "patternHelp": "The address the shop is served at, like https://bgscorner.com: https, no path and no slash at the end.",
     "help": "Used for each page's canonical link, the picture a shared link shows, and the View on store buttons here."},
    # The rules below are printed on the pages and applied by shop.js, which
    # reads them from catalogue.js (window.BGS_RULES). Cross-field checks (the
    # cutoff's hours, the ladder's order) are in validate.py.
    {"path": "/store/free_delivery_over", "type": "int", "label": "Free delivery over (AED)", "required": True, "min": 0, "max": 2000, "group": "Shipping and delivery",
     "help": "The bag delivers free from this subtotal."},
    # How long an order waits before it is dispatched. Migration 003 put it in
    # settings when the shop stopped promising same-day delivery; it is printed
    # in the strip, on the product page and in the page descriptions, so it
    # belongs to the owner rather than to the code.
    {"path": "/store/dispatch_days", "type": "text", "label": "Dispatched in", "required": True, "maxLength": 40,
     "group": "Shipping and delivery",
     "help": "In the owner's own words, as the policies say it: \"1 to 3 business days\". Shown in the line above "
             "the masthead, on every product page and in what search engines print."},
    {"path": "/store/delivery_fee", "type": "int", "label": "Delivery fee (AED)", "required": True, "min": 0, "max": 500, "group": "Shipping and delivery",
     "help": "Charged on a bag below the free delivery amount."},
    {"path": "/store/sameday_fee", "type": "int", "label": "Same-day fee (AED)", "required": True, "min": 0, "max": 500, "group": "Shipping and delivery"},
    {"path": "/store/sameday_cutoff", "type": "text", "label": "Same-day cutoff (Dubai time)", "required": True, "group": "Shipping and delivery",
     "pattern": r"(1[0-2]|[1-9]):[0-5][0-9] (AM|PM)", "patternHelp": "Like 2:00 PM.",
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
    {"path": "/brand/wordmark", "type": "text", "label": "Wordmark", "group": "Brand", "maxLength": 30,
     "help": "The words beside the emblem in the header and the footer, set in Cormorant Garamond Bold."},
    {"path": "/brand/emblem", "type": "image", "label": "Emblem beside the wordmark", "group": "Brand", "readonly": EMBLEM},
    {"path": "/brand/logo", "type": "image", "label": "Logo", "group": "Brand", "upload": "logo-dark", "rendered": False, "notShown": LOGO_UNUSED,
     "help": LOGO + " This one was on the header."},
    {"path": "/brand/logo_light", "type": "image", "label": "Logo on dark", "group": "Brand", "upload": "logo-light", "rendered": False, "notShown": LOGO_UNUSED,
     "help": LOGO + " This one was on the footer."},
    {"path": "/brand/suffix", "type": "text", "label": "Wordmark suffix", "group": "Brand", "rendered": False, "notShown": NOT_SHOWN, "maxLength": 20},
    {"path": "/brand/icons/ico", "type": "image", "label": "Favicon", "group": "Brand", "upload": "emblem",
     "help": "The site icons are all made from one emblem: a PNG with a transparent background, at least 180 px on its long side. "
             "Uploading a new emblem makes this favicon and the three icons below again; the emblem it replaces goes to the trash."},
    {"path": "/brand/icons/png32", "type": "image", "label": "Favicon 32 px", "group": "Brand", "upload": "icon", "help": ICON},
    {"path": "/brand/icons/png16", "type": "image", "label": "Favicon 16 px", "group": "Brand", "upload": "icon", "help": ICON},
    {"path": "/brand/icons/apple", "type": "image", "label": "Home screen icon", "group": "Brand", "upload": "icon", "help": ICON},
    {"path": "/seo/og_image", "type": "image", "label": "Link preview image", "group": "Search and sharing", "readonly": UPLOAD},
    {"path": "/seo/default_title_suffix", "type": "text", "label": "Title suffix", "required": True, "maxLength": 40, "group": "Search and sharing",
     "help": "Follows each page's name in the browser tab and in link previews, after a bar, as in Your Bag | BGS Corner. "
             "The page-not-found page keeps its own title for now."},
    {"path": "/seo/default_description", "type": "textarea", "label": "Default description", "maxLength": 160, "group": "Search and sharing", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/social/instagram", "type": "href", "social": True, "label": "Instagram", "group": "Social", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/social/whatsapp", "type": "href", "social": True, "label": "WhatsApp", "group": "Social", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/social/tiktok", "type": "href", "social": True, "label": "TikTok", "group": "Social", "rendered": False, "notShown": NOT_SHOWN},
    {"path": "/auth/domain", "type": "text", "label": "Auth0 domain", "maxLength": 100, "group": SIGNIN,
     "pattern": AUTH_DOMAIN, "patternHelp": "Only the domain, in lower case, like dev-abc123.us.auth0.com: no https:// and no slash.",
     "help": SIGNIN_HELP + " The Domain on the application's Settings tab in Auth0; the shop reaches it over https."},
    {"path": "/auth/client_id", "type": "text", "label": "Client ID", "maxLength": 40, "group": SIGNIN,
     "pattern": AUTH_CLIENT_ID, "patternHelp": "Letters and digits only, as Auth0 shows the Client ID. A client secret is longer and never goes here.",
     "help": "The Client ID on the same Settings tab. It is not a secret: every shopper's browser sees it. "
             "The application is a Single Page Application, which has no client secret, and none belongs anywhere in the shop."},
    {"path": "/analytics/ga4_id", "type": "text", "label": "Google Analytics", "group": "Analytics", "locked": LOGIN},
    {"path": "/analytics/meta_pixel_id", "type": "text", "label": "Meta pixel", "group": "Analytics", "locked": LOGIN},
    {"path": "/analytics/tiktok_pixel_id", "type": "text", "label": "TikTok pixel", "group": "Analytics", "locked": LOGIN},
    {"path": "/languages/english", "type": "bool", "label": "English", "group": "Languages", "locked": "The shop is written in English."},
    {"path": "/languages/arabic", "type": "bool", "label": "Arabic", "group": "Languages", "rendered": False, "notShown": NOT_SHOWN},
]
