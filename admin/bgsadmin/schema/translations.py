"""The Arabic dictionary behind the storefront's language toggle
(flow/content/translations.json).

shop.js swaps a label for its Arabic when the label's exact, trimmed English
text is a key here, so an entry stops translating once the English on the
site changes. It covers the shop's interface (menus, buttons, the bag), not
products: their Arabic names and stories are fields of each product, saved
but not shown yet.
"""
RESOURCE = {"name": "translations", "label": "Translations", "kind": "document",
            "intro": "Arabic for the shop's labels, used by the language switch in the top strip. "
                     "Each entry matches the English on the page exactly, letter for letter."}

FIELDS = [
    {"path": "/ar", "type": "dictionary", "label": "Arabic", "keyLabel": "English", "valueLabel": "Arabic",
     "required": True, "dir": "rtl", "keyMaxLength": 120, "maxLength": 300, "max": 400,
     "help": "An entry with no Arabic leaves that label in English."},
]
