"""The Inventory, Bulk editor and Import and export screens: read for the
rules every admin screen follows, and rendered in headless Chrome against a
temporary clone to see that each one draws from the shop's own data.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_bulk_screens.py'

Typing, the grid's keys, pasting and the saves need a live browser session
and are not covered here; test_bulk.py covers the server side of the saves.
"""
import os
import pathlib
import re
import sys
import tempfile
import unittest

from box import Box

ADMIN = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ADMIN / "devtools"))
import dom_diff  # noqa: E402

PORT = int(os.environ.get("ADMIN_BULK_UI_PORT", "4772"))
SCREENS = ("inventory", "bulk", "import")
SOURCES = ["ui/screens/%s.js" % s for s in SCREENS] + ["ui/lib/bulk.js"] + ["ui/css/%s.css" % s for s in SCREENS]


class SourceRules(unittest.TestCase):
    def test_nothing_is_built_from_markup_or_styled_inline(self):
        for rel in SOURCES:
            src = (ADMIN / rel).read_text(encoding="utf-8")
            for bad in ("innerHTML", "outerHTML", "insertAdjacentHTML", "style=", "<style", "document.write"):
                self.assertNotIn(bad, src, rel)
            self.assertNotIn(chr(0x2014), src, rel)
            self.assertNotIn(chr(0x2015), src, rel)

    def test_each_screen_loads_its_own_stylesheet(self):
        for name in SCREENS:
            src = (ADMIN / "ui" / "screens" / (name + ".js")).read_text(encoding="utf-8")
            self.assertIn('useCss("%s")' % name, src)
            self.assertTrue((ADMIN / "ui" / "css" / (name + ".css")).is_file(), name)

    def test_no_photo_or_video_is_named_in_the_screens(self):
        for rel in SOURCES:
            src = (ADMIN / rel).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[\w-]+\.(?:jpg|png|webp|mp4)\b", src), rel)


@unittest.skipUnless(os.path.exists(dom_diff.CHROME), "headless Chrome is not installed")
class Rendered(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="screens-"))
        cls.products = cls.b.content("products")

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def page(self, address):
        dom = dom_diff.dump("http://localhost:%d/admin/%s" % (PORT, address), 1280, self.tmp)
        return dom, "\n".join(dom_diff.visible(dom))

    def test_inventory_lists_the_tracked_products_only(self):
        dom, text = self.page("#/inventory")
        self.assertIn("Inventory | BGS Corner admin", text)
        for d in self.products.values():
            label = "Stock for " + d["name"]
            if d.get("stock") is None:
                self.assertNotIn(label + "\n", text + "\n", d["name"])
            else:
                self.assertIn(label, text)
        self.assertEqual(text.count("Low stock"), sum(1 for d in self.products.values()
                                                       if d.get("stock") is not None and d["stock"] <= 5))

    def test_bulk_editor_draws_a_grid_row_per_product(self):
        dom, text = self.page("#/bulk")
        self.assertIn('role="grid"', dom)
        self.assertEqual(dom.count('role="rowheader"'), len(self.products))
        for head in ("Title", "Status", "Price (AED)", "Size 1 (AED)", "Stock", "Position"):
            self.assertIn(head, text)
        self.assertNotIn("Not built yet", text)
        self.assertEqual(dom.count('tabindex="0" data-r='), 1, "one cell in the tab order")

    def test_import_screen_counts_the_products_and_starts_at_step_one(self):
        dom, text = self.page("#/import")
        self.assertIn("%d products in all." % len(self.products), text)
        for words in ("Export all products", "Choose a file", "Review the check", "Apply or cancel", "CSV file"):
            self.assertIn(words, text)
        self.assertIn('aria-current="step"', dom)
        self.assertNotIn("[object", text)


if __name__ == "__main__":
    unittest.main()
