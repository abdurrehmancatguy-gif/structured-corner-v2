"""Write the smaller image files the pages ask for, next to their sources.

    python3 tools/make_derivatives.py          # from flow/

Product photos are stored at 1000 px (<id>-<n>.jpg) with a 520 px card copy,
both written by the importers. Pages need three more sizes so that a phone is
never sent a desktop file:
  <id>-<n>-600.jpg        product page main image (shown at 245 to 470 px)
  <id>-<n>-card-360.jpg   product cards on phones (shown at about 166 px)
  <id>-<n>-thumb.jpg      gallery thumbnails and bag lines (51 to 108 px)
Banners get a 750 px phone copy and a 1320 px desktop copy, category photos a
216 px square (twice the largest circle), the logos a 486 px copy (three
times the phone logo, over twice the desktop one), and the scent family
photos (900x675 in assets/fam) a 450 px copy, since their tiles are 138 to
227px wide.

A copy is rewritten only when the bytes of its source, or the size and quality
it is made at, differ from the ones recorded in tools/derivatives.json, so
reruns are cheap and importers need no change. Not by date: a photo put in
place by Finder, cp -p or unzip keeps an old modification time and its copies
would never be redone. build.py reads the same record and fails when a copy is
missing or was made from an older photo, so commit it with the images.

If you change QUALITY or a size, bump DERIVATIVES in build.py as well: product
photo URLs are versioned by their original, so rewritten copies need a new salt.
"""
import hashlib
import json
import pathlib
import re
from PIL import Image

FLOW = pathlib.Path(__file__).resolve().parent.parent
IMG, CAT = FLOW / "assets" / "img", FLOW / "assets" / "cat"
FAM = FLOW / "assets" / "fam"
QUALITY = 78
# "vibe-1-600.jpg" also looks like frame 600 of "vibe-1", so a copy must never be
# taken for an original; without this a second run made copies of copies.
# Banner copies ("banner-1-1320.jpg") look like product frames the same way, so
# everything named banner- is handled by the banner branch alone.
COPIES = ("-600.jpg", "-card-360.jpg", "-thumb.jpg", "-card.jpg")
MANIFEST = FLOW / "tools" / "derivatives.json"
made = kept = 0
try:
    before = json.loads(MANIFEST.read_text())
except (OSError, ValueError):
    before = {}
record, sums = {}, {}


def rel(path):
    return path.relative_to(FLOW).as_posix()


def stale(src, dst, recipe):
    if src not in sums:
        sums[src] = hashlib.md5(src.read_bytes()).hexdigest()
    entry = [rel(src), sums[src], recipe]
    record[rel(dst)] = entry
    return not dst.exists() or before.get(rel(dst)) != entry


def jpeg(src, dst, width=None, square=None):
    global made, kept
    if not stale(src, dst, "jpeg q%d w%s s%s" % (QUALITY, width, square)):
        kept += 1
        return
    im = Image.open(src).convert("RGB")
    if square:
        s = min(im.size)
        l, t = (im.width - s) // 2, (im.height - s) // 2
        im = im.crop((l, t, l + s, t + s)).resize((square, square), Image.LANCZOS)
    elif width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    made += 1


def png(src, dst, width):
    global made, kept
    if not stale(src, dst, "png w%d" % width):
        kept += 1
        return
    im = Image.open(src).convert("RGBA")
    size = (width, round(im.height * width / im.width))
    # A logo in one colour stays that colour at every size: only its alpha is
    # resized. Lanczos over- and undershoots at the edges, which un-premultiplied
    # left a few pixels a shade off the colour (176,126,32 beside 168,121,30).
    one = {c[:3] for n, c in im.getcolors(1 << 24) or () if c[3]}
    if len(one) == 1:
        flat = Image.new("RGBA", size, one.pop() + (0,))
        flat.putalpha(im.getchannel("A").resize(size, Image.LANCZOS))
        im = flat
    else:
        im = im.convert("RGBa").resize(size, Image.LANCZOS).convert("RGBA")
    im.quantize(256, method=Image.Quantize.FASTOCTREE).save(dst, optimize=True)
    made += 1


for src in sorted(IMG.glob("*.jpg")):
    m = re.fullmatch(r"(banner-\d+)(-phone)?\.jpg", src.name)
    if m:
        jpeg(src, IMG / ("%s-phone-750.jpg" % m.group(1) if m.group(2) else "%s-1320.jpg" % m.group(1)),
             750 if m.group(2) else 1320)
    elif (re.fullmatch(r"[a-z0-9-]+-\d+\.jpg", src.name) and not src.name.endswith(COPIES)
          and not src.name.startswith("banner-")):
        stem = src.name[:-4]
        jpeg(src, IMG / (stem + "-600.jpg"), 600)
        jpeg(src, IMG / (stem + "-card-360.jpg"), 360)
        jpeg(src, IMG / (stem + "-thumb.jpg"), 160)
for src in sorted(CAT.glob("*.jpg")):
    if not src.stem.endswith("-216"):
        jpeg(src, CAT / (src.stem + "-216.jpg"), square=216)
for src in sorted(FAM.glob("*.jpg")):
    if not src.stem.endswith("-450"):
        jpeg(src, FAM / (src.stem + "-450.jpg"), 450)
for name in ("logo-gold", "logo-gold-light"):
    png(IMG / (name + ".png"), IMG / (name + "-486.png"), 486)

# Copies whose original is gone (a re-import with fewer frames) go too, or they
# would sit in assets/ referenced by nothing.
removed = 0
for folder, suffixes, ext in ((IMG, ("-600", "-card-360", "-thumb"), ".jpg"), (CAT, ("-216",), ".jpg"),
                              (FAM, ("-450",), ".jpg")):
    for suf in suffixes:
        for d in folder.glob("*" + suf + ext):
            if not (folder / (d.name[: -len(suf + ext)] + ext)).exists():
                d.unlink(); removed += 1
MANIFEST.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
print("derivatives: %d written, %d already current, %d orphans removed" % (made, kept, removed))
