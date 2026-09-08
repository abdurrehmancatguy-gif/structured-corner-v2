"""Import the "BGS Corner Website" photography set.

Supersedes the earlier imports for the 24 products it covers. Run it against
the delivered folder (unzip first); the source is never modified.

    python3 tools/import_website_set.py <folder>            # from flow/
    python3 tools/import_website_set.py <folder> --dry-run

WHY THIS DOES NOT CROP
----------------------
Every file in this set is already 1254x1254. The older importer resizes the
long side to 2x the target and centre-crops, which on an already-square source
zooms into the middle and clips the bottle. Straight resize, no crop.

WHAT IT REFUSES TO GUESS
------------------------
The bakhoor tins are labelled by tin number ("BGS BAKHOOR 1", "BGS BAKHOOR 3")
and come in a blue and a white finish - two SKUs' worth of photography for five
named products (Shay, Compodi, Mattar, Falah, Philippine). Nothing in the
filenames says which tin is which product, so BAKHOOR_MAP stays empty and those
five keep what they have. Same for "Ciao", which is a product with photography
and no entry in products.json, and "Gift box 2", which shows an Amore/Vibe/Be
Mine trio that could belong to more than one set. Wrong tin on the wrong product
is worse than no new tin.
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
# Tin number -> product id. Empty on purpose; see the module docstring.
BAKHOOR_MAP = {}


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
        products[pid]["images"] = names
        print("  %-24s %d" % (pid, len(names)))

    CONTENT.write_text(json.dumps(products, indent=2, ensure_ascii=False) + "\n")
    print("\nwrote %d files, removed %d orphaned, updated products.json" % (written, removed))


if __name__ == "__main__":
    main()
