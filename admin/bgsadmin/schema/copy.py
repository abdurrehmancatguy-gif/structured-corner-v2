"""Site copy (flow/content/copy.json)."""
from .pages import RULE_HELP, RULE_PATTERN_HELP, RULES, tokens

RESOURCE = {"name": "copy", "label": "Site text", "kind": "document",
            "intro": "Text around the shop: the promises under the banner, the quiz banner, the top strip, and each collection's name, breadcrumb and intro."}

# The category keys are code (the filters, the card lines and the breadcrumbs
# switch on them), so there is one fixed set of fields per key; only the words
# are content. "all" is the collection page with no filter.
COLLECTIONS = (("attars", "Attars"), ("bakhoor", "Bakhoor"), ("edp", "EDP sprays"), ("gift-sets", "Gift sets"),
               ("all", "All products page"))


def _collection(key, name):
    group = "Collection: " + name
    if key == "all":
        label_help = "The heading of the collection page with no filter, and its browser tab title."
        crumb_help = "The breadcrumb on that page reads Home / this."
    else:
        label_help = ("The collection page's heading and tab title, its filter checkbox and its filter pill. "
                      "The homepage circle has its own label, under Navigation.")
        crumb_help = ("The breadcrumbs on this collection's page and on each of its product pages. "
                      "The shop's search matches it too.")
    return [
        {"path": "/categories/%s/label" % key, "type": "text", "label": "Name", "required": True, "maxLength": 30,
         "group": group, "help": label_help},
        {"path": "/categories/%s/crumb" % key, "type": "text", "label": "Name in breadcrumbs", "required": True,
         "maxLength": 30, "group": group, "help": crumb_help},
        {"path": "/collection_intros/%s" % key, "type": "textarea", "label": "Intro", "maxLength": 200, "group": group,
         "help": "The line under the collection page's heading."},
    ]


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
    {"path": "/strip/countdown_line", "type": "text", "label": "Top strip line", "required": True, "maxLength": 80, "group": "Top strip",
     "pattern": tokens(*RULES), "patternHelp": RULE_PATTERN_HELP,
     "help": "At the top of every page, before the time left to the same-day cutoff. " + RULE_HELP},
    {"path": "/strip/right_links", "type": "rows", "label": "Top strip links", "max": 4, "itemLabel": "label", "canAdd": True,
     "group": "Top strip", "help": "On the right of the strip. The switch to Arabic after them is code.", "fields": [
         {"path": "/label", "type": "text", "label": "Text", "required": True, "maxLength": 40,
          "pattern": tokens(*RULES), "patternHelp": RULE_PATTERN_HELP, "help": RULE_HELP},
         {"path": "/href", "type": "href", "label": "Link (empty for plain text)"},
     ]},
    {"path": "/search_placeholder", "type": "text", "label": "Search box hint", "required": True, "maxLength": 40, "group": "Header",
     "help": "Inside the search box at the top of every page."},
] + [f for key, name in COLLECTIONS for f in _collection(key, name)]
