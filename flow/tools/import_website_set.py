"""Import the "BGS Corner Website" photography set.

Supersedes the earlier imports for the 24 products it covers. Run it against
the delivered folder (unzip first); the source is never modified.

    python3 tools/import_website_set.py <folder>            # from flow/
    python3 tools/import_website_set.py <folder> --dry-run

WHY THIS DOES NOT CROP
----------------------
Nearly every file in this set is already 1254x1254. The older importer resizes
the long side to 2x the target and centre-crops, which on an already-square
source zooms into the middle and clips the bottle. Straight resize, no crop.
The odd one that is not square (Bakhoor 2.3 is 1176x1337) is trimmed to a
centred square first, so it is not squashed.

FRAME ORDER
-----------
Frame one is the bare product and frame two is the shot with the box. The
delivered numbering does not always agree, so FRAME_ORDER corrects the four
sets where it does not. Without it a re-import would silently put a lifestyle
shot or a second box in the gallery's second slot.

BAKHOOR TINS
------------
The five bakhoor products are named after their tins, "Bakhoor 1" to
"Bakhoor 5", as printed on the labels. "Bakhoor 2", "Bakhoor 4" and "Bakhoor 5"
files match those names on their own; the files spelt "Bukhoor" are mapped in
BAKHOOR_MAP, read off the labels in the photos. The set has no closed shot of
tin 4; the owner sent one separately, so add it to the folder as
"Bakhoor 4.1.jpeg" before a re-import or tin 4 loses its first frame.

WHAT IT REFUSES TO GUESS
------------------------
"Ciao", which is a product with photography and no entry in products.json, and
"Gift box 2", which shows an Amore/Vibe/Be Mine trio that could belong to more
than one set. They are listed as not mapped and left alone.
"""
import json
import os
import pathlib
import re
import sys
from PIL import Image

FLOW = pathlib.Path(__file__).resolve().parent.parent
OUT = FLOW / "assets" / "img"
CONTENT = FLOW / "content" / "products.json"

FULL, CARD, QUALITY = 1000, 520, 72

# Filename label -> product id, for labels that differ from the product name.
ALIAS = {
    "solei": "soleil-frais",                  # spelling differs from the sheet
    "edward": "edward-the-black-prince",
    "dessertbreeze": "desert-breeze",         # one s in the sheet
    "majilisoud": "majlis-oud",               # transposed in some filenames
    "magnolia": "magnolia-veil",
    "magnoila": "magnolia-veil",              # transposed
    "hisandher": "his-and-hers-duo",
    "beminewhitebackgroundwithbox": "be-mine",
}
# Filename label -> bakhoor product id, for the "Bukhoor" spellings. Checked
# against the tin label in each photo.
BAKHOOR_MAP = {
    "Bukhoor white": "bakhoor-1",             # white tin, label BAKHOOR 1
    "Bukhoor": "bakhoor-3",                   # blue tin, label BAKHOOR 3
    "Bukhoor Blue": "bakhoor-3",              # blue tin, label BAKHOOR 3
}

# Frame order, 1-based, for the sets where the delivered numbering does not put
# the bare product first and the shot with the box second. Read off contact
# sheets of the imported frames - there is no pattern to infer, the box lands on
# frame 4 for Be Mine, 3 for Edward, 1 for Soleil Frais, and both 1 and 2 for
# Desert Breeze. Everything not listed here already arrives in that order.
FRAME_ORDER = {
    "be-mine":                 [1, 4, 2, 3],
    "edward-the-black-prince": [2, 3, 1, 4],
    "soleil-frais":            [2, 1, 3, 4],
    # EDITED set (2026-09-11): no bare single bottle, so the 6 ml + 3 ml pair
    # leads, then the box, the desert scene and the flat-lay. Counted after
    # the duplicate box shot is dropped (see same_picture).
    "desert-breeze":           [4, 1, 2, 3],
}

# Frames the owner has taken off the site, by file name, so a re-import of the
# same set leaves them out too.
SKIP = {
    "Imperial Crown 3.301 (1) (1).png",   # the cocktail glass, removed 2026-09-11
}

# Frames left out because another file already shows them, by file name,
# chosen by eye. same_picture() below only points out candidates: it scores the
# two Majlis box shots as alike although one has "Dehn Al Oud 12 ML" printed on
# the box base, and no pixel threshold separates that pair from a real
# duplicate.
DUPLICATES = {
    "Dessert Breeze 2 301 (1) (2).png",   # the same box shot exported twice
    "Majlis Oud 2.301 (1) (2).png",       # box base printed "Dehn Al Oud 12 ML";
                                          # the plain one is kept until the owner
                                          # says which box art is current
}

# Two exports of one frame look alike to within this mean grey-level
# difference (out of 255) on a 32x32 thumbnail. Measured on the EDITED set:
# its duplicate box shots differ by under 2, distinct frames by over 20.
SAME = 6


def same_picture(a, b):
    ta = list(Image.open(a).convert("L").resize((32, 32), Image.BILINEAR).getdata())
    tb = list(Image.open(b).convert("L").resize((32, 32), Image.BILINEAR).getdata())
    return sum(abs(x - y) for x, y in zip(ta, tb)) / len(ta) < SAME


def label_and_index(filename):
    """Strip the export noise and split "Golden bloom3 .301 (1) (1)" into
       ("Golden bloom", 3). The (n) suffixes are duplicate markers from the
       download, the bare 301 is a batch tag, and some names glue the frame
       number to the last word."""
    s = filename[:-4]
    s = re.sub(r"\(\d+\)", " ", s)                    # (1) (1) download markers
    s = s.replace(".", " ")                           # "2.301", "3." , "301.."
    s = re.sub(r"([A-Za-z])(\d)", r"\1 \2", s)        # "bloom3" -> "bloom 3"
    s = re.sub(r"\b301\b", " ", s)                    # batch tag, after the dots
    s = re.sub(r"\s+", " ", s).strip()
    m = re.search(r"\b(\d+)\b\s*$", s) or re.search(r"\b(\d+)\b", s)
    if not m:
        return s, None
    return (s[:m.start()] + " " + s[m.end():]).strip(), int(m.group(1))


def resize(src, dst, size):
    im = Image.open(src)
    if im.mode in ("RGBA", "LA", "P"):
        flat = Image.new("RGB", im.size, (255, 255, 255))
        im = im.convert("RGBA")
        flat.paste(im, mask=im.getchannel("A"))
        im = flat
    else:
        im = im.convert("RGB")
    w, h = im.size
    if w != h:
        s = min(w, h)
        im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    im.resize((size, size), Image.LANCZOS).save(
        dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)


def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not argv:
        sys.exit("usage: import_website_set.py <folder> [--dry-run]")
    src = pathlib.Path(argv[0])
    if not src.is_dir():
        sys.exit("not a folder: %s" % src)
    dry = "--dry-run" in sys.argv

    products = json.loads(CONTENT.read_text())
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    by_name = {norm(v["name"]): k for k, v in products.items()}

    groups, unmapped = {}, {}
    for fn in sorted(os.listdir(src)):
        if not fn.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        if fn in SKIP:
            print("  skipped %s (taken off the site)" % fn)
            continue
        if fn in DUPLICATES:
            print("  skipped %s (listed in DUPLICATES)" % fn)
            continue
        label, idx = label_and_index(fn)
        pid = by_name.get(norm(label)) or ALIAS.get(norm(label)) or BAKHOOR_MAP.get(label)
        if pid and pid in products:
            # sort on the frame number, then the filename, so same-numbered
            # variants stay adjacent and in a stable order
            groups.setdefault(pid, []).append(((idx if idx is not None else 99), fn))
        else:
            unmapped.setdefault(label, []).append(fn)

    print("%d products <- %d files" % (len(groups), sum(len(v) for v in groups.values())))
    if unmapped:
        print("\nnot mapped, left alone:")
        for label in sorted(unmapped):
            print("  %-32s %d file(s)" % (label, len(unmapped[label])))
    absent = [k for k, v in products.items() if v.get("published") and k not in groups]
    print("\npublished products this set does not cover: %d" % len(absent))
    for k in absent:
        print("  %-22s %s" % (k, products[k]["category"]))

    # Some frames were exported twice under different names. Look-alikes are
    # reported, not dropped: check them by eye and list real ones in DUPLICATES.
    for pid in sorted(groups):
        seen = []
        for idx, fn in sorted(groups[pid]):
            twin = next((k for k in seen if same_picture(src / fn, src / k)), None)
            if twin:
                print("  %-24s CHECK %s looks like %s" % (pid, fn, twin))
            seen.append(fn)

    if dry:
        print()
        for pid in sorted(groups):
            print("  %-24s %d" % (pid, len(groups[pid])))
        return

    OUT.mkdir(parents=True, exist_ok=True)
    written = removed = 0
    for pid in sorted(groups):
        files = [fn for _, fn in sorted(groups[pid])]
        names = []
        for i, fn in enumerate(files, 1):
            full = OUT / ("%s-%d.jpg" % (pid, i))
            resize(src / fn, full, FULL)
            resize(src / fn, OUT / ("%s-%d-card.jpg" % (pid, i)), CARD)
            names.append(full.name)
            written += 2
        # An earlier set may have left more frames than this one supplies; those
        # files would otherwise sit in assets/img/ referenced by nothing.
        for stale in sorted(OUT.glob("%s-*.jpg" % pid)):
            m = re.match(re.escape(pid) + r"-(\d+)(-card)?\.jpg$", stale.name)
            if m and int(m.group(1)) > len(files):
                stale.unlink()
                removed += 1
        order = FRAME_ORDER.get(pid)
        note = ""
        if order and sorted(order) == list(range(1, len(names) + 1)):
            names = [names[i - 1] for i in order]
            note = "  reordered"
        elif order:
            # a frame was added, skipped or listed as a duplicate since the
            # order was read off the contact sheets, so it no longer fits
            note = "  WARNING: FRAME_ORDER has %d frames, the set %d; delivered order kept" % (
                len(order), len(names))
        products[pid]["images"] = names
        print("  %-24s %d%s" % (pid, len(names), note))

    CONTENT.write_text(json.dumps(products, indent=2, ensure_ascii=False) + "\n")
    print("\nwrote %d files, removed %d orphaned, updated products.json" % (written, removed))


if __name__ == "__main__":
    main()
