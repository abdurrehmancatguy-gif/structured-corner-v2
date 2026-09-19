"""Navigation (flow/content/navigation.json): the category bar and homepage
circles (one list feeds both), the phone tab bar and the footer."""
RESOURCE = {"name": "navigation", "label": "Navigation", "kind": "document",
            "intro": "The category bar and homepage circles, the phone tab bar and the footer."}

FIELDS = [
    {"path": "/categories", "type": "rows", "label": "Category bar and homepage circles", "min": 1, "max": 10,
     "itemLabel": "label", "canAdd": False, "group": "Categories",
     "help": "One list feeds the bar under the header and the circles on the homepage.", "fields": [
         {"path": "/label", "type": "text", "label": "Label", "required": True, "maxLength": 30},
         {"path": "/href", "type": "href", "label": "Link", "required": True},
         {"path": "/tint", "type": "tint", "label": "Circle colour"},
         {"path": "/image", "type": "image", "label": "Picture", "upload": "category",
          "help": "Upload a photo, cropped square for the circle, or a cut-out: a PNG with a transparent background that "
                  "stands in the circle. The picture style below is set to match the upload."},
         {"path": "/cutout", "type": "enum", "label": "Picture style", "enum": [False, True, "wide"], "default": False,
          "enumLabels": ["Photo inside the circle", "Cut-out rising out of the circle", "Wide cut-out across the circle"],
          "help": "A cut-out needs a picture with a transparent background."},
     ]},
    {"path": "/tabs", "type": "rows", "label": "Phone tab bar", "min": 2, "max": 5, "itemLabel": "label", "canAdd": True,
     "group": "Phone tab bar", "fields": [
         {"path": "/label", "type": "text", "label": "Label (read aloud to screen readers)", "required": True, "maxLength": 20},
         {"path": "/href", "type": "href", "label": "Link", "required": True},
         {"path": "/icon", "type": "icon", "label": "Icon"},
     ]},
    {"path": "/footer", "type": "rows", "label": "Footer columns", "min": 1, "max": 5, "itemLabel": "heading", "canAdd": True,
     "group": "Footer", "fields": [
         {"path": "/heading", "type": "text", "label": "Heading", "required": True, "maxLength": 30},
         {"path": "/links", "type": "rows", "label": "Links", "max": 8, "itemLabel": "label", "canAdd": True, "fields": [
             {"path": "/label", "type": "text", "label": "Text", "required": True, "maxLength": 40},
             {"path": "/href", "type": "href", "external": True,
              "label": "Link (empty shows it as plain text)",
              "help": "A page of this shop, or the whole https address of another site, "
                      "as the sister companies are linked. A link that leaves the shop opens in its own tab."},
         ]},
     ]},
    {"path": "/main", "type": "rows", "label": "Main menu (unused)", "group": "Unused", "rendered": False,
     "notShown": "Nothing on the site reads this list; the category bar uses Categories above.", "itemLabel": "label", "canAdd": True,
     "fields": [
         {"path": "/label", "type": "text", "label": "Label", "maxLength": 30},
         {"path": "/href", "type": "href", "label": "Link"},
     ]},
]
