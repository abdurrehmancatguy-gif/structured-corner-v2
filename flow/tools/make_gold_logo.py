"""Build the BGS CORNER lockup in metallic gold.

The supplied art (assets/img/logo.png) is flat near-black: emblem + "BGS", and
nothing else. CORNER used to be live HTML text beside it, which never matched —
the art is set in a condensed serif and the CSS fallback stack could only offer
Times New Roman, ~7% wider per letter, on a baseline guessed with a magic
translate. Drawing the word into the art instead makes cap height and baseline
exact by construction, and identical on every device.

Bodoni 72 Bold is the closest face on the machine: inked width 1.9% off the
art's, stem weight 1.5% off. Measured, not guessed — see the constants below.

Metal is a gradient, not a colour, so the ramp runs down the finished lockup
and the original alpha stays as the shape. Two renditions, because one ramp
cannot serve both grounds:

  logo-gold.png        white masthead - weighted dark, so the mark holds
  logo-gold-light.png  ink footer - lifted, since the dark end vanishes there

macOS only (it needs the system Bodoni). Output is committed, so it runs on
demand, not at build time.

Run from inside flow/:  python3 tools/make_gold_logo.py
"""
import json
import pathlib
from PIL import Image, ImageDraw, ImageFont

IMG = pathlib.Path("assets/img")
SRC = IMG / "logo.png"
FONT = "/System/Library/Fonts/Supplemental/Bodoni 72.ttc"
FONT_INDEX = 2  # Bold. Index 1 is Bold Italic.

# Geometry read off logo.png, in its own pixels. The word is placed against
# these, so it lands on the art's baseline rather than near it.
ART_H = 505       # full artwork height, set by the emblem
BGS_CAP = 310     # cap height of the B, y101 to y410
BGS_BASE = 410    # baseline, the flat foot of the B
BGS_RIGHT = 1339  # right edge of the S
GAP = 77          # emblem's right edge (502) to the B (579): the lockup's own spacing

# Stops down the artwork. Anchored on the site's gold tokens: --gold #a8791e
# and --gold-d #8a5a14 both sit inside each ramp. Mirrored nowhere else now
# that the word is part of the image.
ON_LIGHT = [(0.00, (0x5E, 0x3A, 0x0C)), (0.16, (0x8A, 0x5A, 0x14)),
            (0.34, (0xB9, 0x8A, 0x2E)), (0.46, (0xEF, 0xDC, 0xA4)),
            (0.55, (0xC2, 0x93, 0x2F)), (0.76, (0x7E, 0x50, 0x11)),
            (1.00, (0x5A, 0x38, 0x0B))]
ON_DARK = [(0.00, (0x8A, 0x5A, 0x14)), (0.18, (0xB9, 0x8A, 0x2E)),
           (0.36, (0xE3, 0xC8, 0x7E)), (0.48, (0xF7, 0xEB, 0xC8)),
           (0.58, (0xD8, 0xB0, 0x54)), (0.78, (0xA0, 0x74, 0x1F)),
           (1.00, (0x8A, 0x5A, 0x14))]


def fitted_font():
    """Bodoni 72 Bold at whatever size puts its cap height on the art's."""
    size = 300
    for _ in range(30):
        f = ImageFont.truetype(FONT, size, index=FONT_INDEX)
        probe = Image.new("L", (size * 8, size * 3))
        ImageDraw.Draw(probe).text((10, size), "H", font=f, fill=255)
        box = probe.getbbox()
        cap = box[3] - box[1]
        if abs(cap - BGS_CAP) <= 1:
            return f
        size = round(size * BGS_CAP / cap)
    raise SystemExit("could not match cap height with %s" % FONT)


def lockup(word):
    """The art with `word` set after it, on its baseline, as one alpha mask."""
    art = Image.open(SRC).convert("RGBA")
    font = fitted_font()
    x = BGS_RIGHT + GAP
    # getbbox is where the glyphs actually ink relative to the anchor, so the
    # left sidebearing does not eat into the gap.
    left, _, right, _ = font.getbbox(word)
    out = Image.new("RGBA", (x - left + right + 4, ART_H), (0, 0, 0, 0))
    out.paste(art, (0, 0), art)
    # "ls" anchors on the baseline, which is the whole point of the exercise.
    ImageDraw.Draw(out).text((x - left, BGS_BASE), word, font=font,
                             fill=(8, 0, 16, 255), anchor="ls")
    return out


def paint(shape, stops, out):
    """Fill the lockup's silhouette with the ramp, keeping its alpha."""
    w, h = shape.size
    col = Image.new("RGB", (1, h))
    px = col.load()
    for y in range(h):
        t = y / (h - 1) if h > 1 else 0
        if t <= stops[0][0]:
            px[0, y] = stops[0][1]
            continue
        for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
            if t <= p1:
                f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
                px[0, y] = tuple(round(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
                break
        else:
            px[0, y] = stops[-1][1]

    gold = Image.new("RGBA", (w, h))
    gold.paste(col.resize((w, h), Image.NEAREST), (0, 0))
    gold.putalpha(shape.getchannel("A"))
    gold.save(out)
    return out


if __name__ == "__main__":
    if not SRC.exists():
        raise SystemExit("no %s - run this from inside flow/" % SRC)
    word = json.loads(pathlib.Path("content/settings.json").read_text())["brand"]["suffix"]
    shape = lockup(word)
    for stops, name in ((ON_LIGHT, "logo-gold.png"), (ON_DARK, "logo-gold-light.png")):
        paint(shape, stops, IMG / name)
        print("wrote %s  %dx%d  (BGS %s)" % (IMG / name, shape.width, shape.height, word))
