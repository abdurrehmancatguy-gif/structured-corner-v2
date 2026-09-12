"""The scent quiz (flow/content/quiz.json).

build.py prints the questions and their answers on quiz.html. shop.js scores
a visitor's answers against the profiles and writes the result, reading what
each answer looks for, the profiles and the result's words from
window.BGS_QUIZ. An answer's key is what joins its button to what it looks
for, so keys never change, and with them the set of questions and answers:
their words, the facets and the profiles are what the admin edits.
"""
KEY = ("An answer's key joins it to what it looks for, so it cannot change: questions and "
       "answers can be reworded, but not added, removed or moved.")
KIND = "Fixed: the result's title is the chosen scent family and feel, so each question keeps what its answers name."
# {n} once, {total} as often as wanted, and no other braces
STEP = r"(?=.*\{n\})(?!.*\{n\}.*\{n\})[^{}]*(?:\{(?:n|total)\}[^{}]*)*"
SCORE = r"[^{}]*(?:\{(?:shared|total)\}[^{}]*)*"

RESOURCE = {"name": "quiz", "label": "Scent quiz", "kind": "document",
            "intro": "The questions on the quiz page, what each answer looks for, and the sprays a visitor can be "
                     "matched with. The match is the profile sharing the most facets with the answers."}

FIELDS = [
    {"path": "/page/crumb", "type": "text", "label": "Breadcrumb", "required": True, "maxLength": 60, "group": "Page"},
    {"path": "/page/step_label", "type": "text", "label": "Step line", "required": True, "maxLength": 80, "group": "Page",
     "pattern": STEP, "patternHelp": "Keep {n} once, where the question number goes; {total} is the number of questions.",
     "help": "Above each question. {n} becomes the question number and {total} the number of questions."},
    {"path": "/page/back", "type": "text", "label": "Back button", "required": True, "maxLength": 30, "group": "Page"},
    {"path": "/questions", "type": "rows", "label": "Questions", "canAdd": False, "itemLabel": "title", "group": "Questions",
     "fields": [
         {"path": "/title", "type": "text", "label": "Question", "required": True, "maxLength": 80},
         {"path": "/columns", "type": "enum", "label": "Answers shown in", "enum": [1, 2],
          "enumLabels": ["One column", "Two columns"], "help": "Phones always show one column."},
         {"path": "/kind", "type": "enum", "label": "Its answer names",
          "enum": ["occasion", "tone", "family", "sillage", "season"],
          "enumLabels": ["The occasion", "The feel", "The scent family", "How far it carries", "The season"],
          "readonly": KIND},
         {"path": "/options", "type": "rows", "label": "Answers", "canAdd": False, "itemLabel": "label", "fields": [
             {"path": "/key", "type": "text", "label": "Key", "required": True, "readonly": KEY},
             {"path": "/label", "type": "text", "label": "Answer", "required": True, "maxLength": 50},
             {"path": "/sub", "type": "text", "label": "Small line", "maxLength": 60},
         ]},
     ]},
    {"path": "/answers", "type": "rows", "label": "What each answer looks for", "canAdd": False, "itemLabel": "key",
     "group": "Matching", "fields": [
         {"path": "/key", "type": "text", "label": "Answer key", "required": True, "readonly": KEY},
         {"path": "/facets", "type": "tags", "label": "Facets it looks for", "max": 8, "maxRepeat": 2, "itemMaxLength": 24,
          "help": "A facet listed twice counts twice."},
         {"path": "/label", "type": "text", "label": "Named in the result as", "maxLength": 40},
     ]},
    {"path": "/profiles", "type": "rows", "label": "Result profiles", "canAdd": True, "min": 1, "max": 40,
     "itemLabel": "product", "group": "Matching",
     "help": "The result is the profile sharing the most facets with the answers; on a tie, the one higher in the list. "
             "A product that is not published is left out.",
     "fields": [
         {"path": "/product", "type": "product-ref", "label": "Product", "required": True},
         {"path": "/notes", "type": "textarea", "label": "Declared aroma facets", "required": True, "maxLength": 200,
          "help": "Shown with the match. Its name, price and barcode come from the product."},
         {"path": "/facets", "type": "tags", "label": "Facets", "min": 1, "max": 12, "itemMaxLength": 24},
     ]},
    {"path": "/result/eyebrow", "type": "text", "label": "Small heading", "required": True, "maxLength": 40, "group": "Result"},
    {"path": "/result/title_fallback", "type": "text", "label": "Title when the family answer names nothing",
     "required": True, "maxLength": 40, "group": "Result"},
    {"path": "/result/heading", "type": "text", "label": "Heading above the match", "required": True, "maxLength": 60, "group": "Result"},
    {"path": "/result/notes_label", "type": "text", "label": "Notes label", "required": True, "maxLength": 40, "group": "Result"},
    {"path": "/result/barcode_label", "type": "text", "label": "Barcode label", "required": True, "maxLength": 40, "group": "Result"},
    {"path": "/result/score_label", "type": "text", "label": "Match strength label", "required": True, "maxLength": 40, "group": "Result"},
    {"path": "/result/score", "type": "text", "label": "Match strength", "required": True, "maxLength": 60, "group": "Result",
     "pattern": SCORE, "patternHelp": "Use only {shared} and {total} in braces.",
     "help": "{shared} becomes the number of facets the answers and the match have in common, {total} the number the answers asked for."},
    {"path": "/result/see_label", "type": "text", "label": "Button to the product", "required": True, "maxLength": 30, "group": "Result"},
    {"path": "/result/retake_label", "type": "text", "label": "Retake button", "required": True, "maxLength": 30, "group": "Result"},
    {"path": "/result/note", "type": "textarea", "label": "Note under the match", "required": True, "maxLength": 400,
     "group": "Result", "help": "Says where the facets come from."},
    {"path": "/result/unnamed", "type": "text", "label": "Name when no profile's product is on sale", "required": True,
     "maxLength": 40, "group": "Result"},
    {"path": "/result/unnamed_slot", "type": "text", "label": "Note beside that name", "maxLength": 60, "group": "Result"},
]
