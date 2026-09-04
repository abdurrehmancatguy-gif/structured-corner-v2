#!/usr/bin/env python3
"""
Import the re-edited product shots from "oud and bakhoor/edited /".

These PNGs replace the earlier photography for nine products. Each product's
four shots are listed here in DISPLAY ORDER: the lone bottle first (the card's
default and the gallery's opening frame), the shot WITH THE BOX second (shown
when the card is hovered), then the lifestyle frames. Which numbered file is
the lone bottle and which is the box was read off a contact sheet, product by
product, because the numbering is not consistent (Edward's lone is 2, Soleil's
box is 1, Vibe's box is 3).

Product images live only in content/products.json (the content layer the admin
reads); nothing is hardcoded into the templates. Re-run overwrites the nine
products' image lists and their derivatives, leaving every other product alone.
"""
import json, pathlib, subprocess, shutil, os, sys

FLOW = pathlib.Path(__file__).resolve().parent.parent
SRC  = pathlib.Path("/Users/ajoomama/Desktop/oud and bakhoor/edited ")
OUT  = FLOW / "assets" / "img"
CONTENT = FLOW / "content" / "products.json"
SQUARE, CARD, QUALITY = 1000, 520, 82

# product id -> its four source files, IN DISPLAY ORDER [lone, box, rest...]
ORDER = {
    "amore": ["Amore 1 301 (1).png", "Amore 2 301 (1).png", "Amore 3 301 (1).png", "Amore 4 301 (1).png"],
    "barcelona": ["Barcelona 1 301 (1).png", "Barcelona 2 301 (1).png", "Barcelona 3 301 (1).png", "Barcelona 4 301 (1).png"],
    "be-mine": ["Be Mine 1 301 (1).png", "Be mine 2 301 (2) (1).png", "Be mine 3 301 (1).png", "Be mine 4 301 (1).png"],
    "edward-the-black-prince": ["Edward 2 (1)301.png", "Edward 3 301 (1).png", "Edward 1 301 (1).png", "Edward 4 301 (1).png"],
    "majlis-oud": ["Majlis oud 1 301 (1).png", "Majlis Oud 2 301.png", "Majlis oud 3 301 (1).png", "Majilis oud 4 301 (1).png"],
    "pride-of-arabia": ["pride of arabia 1 301 (1).png", "Pride of arabia 2 301 (1).png", "Pride of arabia 3 301 (1).png", "Pride of arabia 4 301 (1).png"],
    "soleil-frais": ["Solei 2 301 (1).png", "Solei 1 301 (1).png", "Solei 3 301 (1).png", "solei 4 301.. (1).png"],
    "suit-up": ["Suit up 1 301 (1).png", "suit up 2 301 (1).png", "Suit up 3 301 (1).png", "Suit up 4  301(1).png"],
    "vibe": ["Vibe 1 301 (1).png", "Vibe 3 301 (1).png", "Vibe 2 301 (1).png", "Vibe4 301 (1).png"],
    # recovered from a chat paste (see tools/recover_pasted_velvet.py); lone bottle,
    # then the shot with the BGS box, then the two lifestyle frames.
    "velvet-spell": ["Velvet Spell 1 lone 301.webp", "Velvet Spell 2 box 301.webp",
                     "Velvet Spell 3 301.webp", "Velvet Spell 4 301.webp"],
}


def sh(*a):
    subprocess.run(a, check=True, capture_output=True)


def square(src, dst, size):
    tmp = dst.with_suffix(".tmp.jpg")
    shutil.copy2(src, tmp)
    sh("sips", "-s", "format", "jpeg", str(tmp))
    sh("sips", "-Z", str(size), str(tmp))          # fit longest side -> size (square source stays whole)
    sh("sips", "-c", str(size), str(size), str(tmp))
    sh("sips", "-s", "format", "jpeg", "-s", "formatOptions", str(QUALITY), str(tmp), "--out", str(dst))
    tmp.unlink(missing_ok=True)


def main():
    if not SRC.exists():
        sys.exit("source folder not found: %s" % SRC)
    products = json.loads(CONTENT.read_text())
    dry = "--dry-run" in sys.argv

    # optional whitelist: any non-flag args restrict the run to those product ids
    # (so re-importing one product doesn't churn the others' derivatives)
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    plan = {pid: files for pid, files in ORDER.items() if not want or pid in want}
    if want:
        unknown = [a for a in want if a not in ORDER]
        if unknown:
            sys.exit("not in ORDER: %s" % ", ".join(unknown))

    # verify every source file exists before touching anything
    missing = [(pid, f) for pid, files in plan.items() for f in files if not (SRC / f).exists()]
    if missing:
        for pid, f in missing:
            print("MISSING:", pid, "->", f)
        sys.exit("aborting: %d source files not found" % len(missing))

    for pid, files in plan.items():
        if pid not in products:
            print("skip (no such product):", pid); continue
        if dry:
            print("%-26s %d shots -> %s-1..%d" % (pid, len(files), pid, len(files))); continue
        # drop the product's old derivatives, then write the new ordered set
        for old in OUT.glob(pid + "-*.jpg"):
            old.unlink()
        names = []
        for i, f in enumerate(files, 1):
            full = OUT / ("%s-%d.jpg" % (pid, i))
            card = OUT / ("%s-%d-card.jpg" % (pid, i))
            square(SRC / f, full, SQUARE)
            square(SRC / f, card, CARD)
            names.append(full.name)
        products[pid]["images"] = names
        print("%-26s -> %s" % (pid, ", ".join(names)))

    if not dry:
        CONTENT.write_text(json.dumps(products, indent=2, ensure_ascii=False) + "\n")
        print("updated products.json for %d products" % len(plan))


if __name__ == "__main__":
    main()
