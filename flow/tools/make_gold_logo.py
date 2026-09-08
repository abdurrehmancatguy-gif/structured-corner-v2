"""Paint the BGS logo art in metallic gold.

The supplied logo (assets/img/logo.png) is flat near-black artwork on a
transparent ground. Metal is not a colour, it is a gradient: a dark edge, a
rising gold, a narrow bright band where the light catches, then back down. So
this walks a vertical ramp down the artwork and keeps the original alpha as the
shape, which leaves the letterforms and the emblem exactly as drawn.

Two renditions, because one ramp cannot serve both grounds:

  logo-gold.png        for the white masthead - weighted dark, so the mass of
                       the mark stays legible against white and only a narrow
                       band goes pale.
  logo-gold-light.png  for the ink footer - the same ramp lifted, because the
                       dark end of the masthead ramp disappears into the ground.

The stops are mirrored in flow.css so the word CORNER beside the art is filled
with the same ramp and the two read as one lockup. Change them in both places
or they will drift apart.

Run from inside flow/:  python3 tools/make_gold_logo.py
"""
import pathlib
from PIL import Image

IMG = pathlib.Path("assets/img")
SRC = IMG / "logo.png"

# (position 0-1 down the artwork, colour). Anchored on the site's own gold
# tokens: --gold #a8791e and --gold-d #8a5a14 sit inside both ramps.
ON_LIGHT = [
    (0.00, (0x5E, 0x3A, 0x0C)),
    (0.16, (0x8A, 0x5A, 0x14)),
    (0.34, (0xB9, 0x8A, 0x2E)),
    (0.46, (0xEF, 0xDC, 0xA4)),
    (0.55, (0xC2, 0x93, 0x2F)),
    (0.76, (0x7E, 0x50, 0x11)),
    (1.00, (0x5A, 0x38, 0x0B)),
]
ON_DARK = [
    (0.00, (0x8A, 0x5A, 0x14)),
    (0.18, (0xB9, 0x8A, 0x2E)),
    (0.36, (0xE3, 0xC8, 0x7E)),
    (0.48, (0xF7, 0xEB, 0xC8)),
    (0.58, (0xD8, 0xB0, 0x54)),
    (0.78, (0xA0, 0x74, 0x1F)),
    (1.00, (0x8A, 0x5A, 0x14)),
]


def ramp(stops, t):
    """Colour at position t (0-1), linearly between the two stops around it."""
    if t <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return tuple(round(c0[i] + (c1[i] - c0[i]) * f) for i in range(3))
    return stops[-1][1]


def paint(src, stops, out):
    """Fill the artwork's silhouette with the ramp, keeping its alpha."""
    art = Image.open(src).convert("RGBA")
    w, h = art.size
    grad = Image.new("RGB", (1, h))
    px = grad.load()
    for y in range(h):
        px[0, y] = ramp(stops, y / (h - 1) if h > 1 else 0)
    grad = grad.resize((w, h), Image.NEAREST)

    gold = Image.new("RGBA", (w, h))
    gold.paste(grad, (0, 0))
    gold.putalpha(art.getchannel("A"))
    gold.save(out)
    return out, w, h


if __name__ == "__main__":
    if not SRC.exists():
        raise SystemExit("no %s - run this from inside flow/" % SRC)
    for stops, name in ((ON_LIGHT, "logo-gold.png"), (ON_DARK, "logo-gold-light.png")):
        out, w, h = paint(SRC, stops, IMG / name)
        print("wrote %s  %dx%d" % (out, w, h))
