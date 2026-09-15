"""Trace the BGS emblem into a vector outline: assets/img/logo-emblem.svg.

The emblem exists only as pictures. This follows the edge of its shape in the
supplied art (assets/img/logo.png, where the emblem is the left 505 x 505), at
twice that size for smoother edges, joins the edge into closed outlines, drops
every point a straight line can stand in for (within a fifth of a pixel at the
art's own size) and writes one even-odd path, so the holes stay holes. build.py
puts that path in the call banners and the promo tiles, where flow.css builds
the emblem from the bottom up.

    cd flow && /usr/bin/python3 tools/trace_emblem.py
"""
import pathlib

import numpy as np
from PIL import Image

SRC = "assets/img/logo.png"
OUT = "assets/img/logo-emblem.svg"
BOX = (0, 0, 505, 505)
UP = 2
EPS = 0.8    # in the traced (doubled) pixels: 0.4 of a pixel of the art


def mask():
    a = Image.open(SRC).convert("RGBA").split()[-1].crop(BOX)
    a = a.resize((a.width * UP, a.height * UP), Image.LANCZOS)
    return np.pad(np.array(a) >= 128, 1)


def edges(m):
    """Every unit edge between a pixel inside and one outside, walked with the
    inside on its right (y grows downwards): start corner -> end corners."""
    out = {}
    ys, xs = np.nonzero(m)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if not m[y - 1, x]:
            out.setdefault((x, y), []).append((x + 1, y))
        if not m[y, x + 1]:
            out.setdefault((x + 1, y), []).append((x + 1, y + 1))
        if not m[y + 1, x]:
            out.setdefault((x + 1, y + 1), []).append((x, y + 1))
        if not m[y, x - 1]:
            out.setdefault((x, y + 1), []).append((x, y))
    return out


def loops(nxt):
    """Join the edges into closed outlines. Where two edges leave one corner
    (pixels touching only at a corner) take the one that turns right."""
    found = []
    while nxt:
        start = next(iter(nxt))
        pts, cur, prev = [start], start, None
        while True:
            outs = nxt[cur]
            if len(outs) > 1 and prev is not None:
                dx, dy = cur[0] - prev[0], cur[1] - prev[1]
                right = (cur[0] - dy, cur[1] + dx)
                pick = right if right in outs else outs[0]
            else:
                pick = outs[0]
            outs.remove(pick)
            if not outs:
                del nxt[cur]
            prev, cur = cur, pick
            if cur == start:
                break
            pts.append(cur)
        found.append(pts)
    return found


def smooth(pts):
    """The pixel steps into a smooth line: the middle of each unit edge, then
    a light running average twice (reaching one pixel of the art each way)."""
    p = np.array(pts, float)
    p = (p + np.roll(p, -1, axis=0)) / 2
    for _ in range(2):
        p = (np.roll(p, 1, axis=0) + 2 * p + np.roll(p, -1, axis=0)) / 4
    return [tuple(q) for q in p.tolist()]


def simplify(pts, eps):
    """Ramer-Douglas-Peucker on a closed outline."""
    def rdp(seq):
        if len(seq) < 3:
            return seq
        a, b = np.array(seq[0], float), np.array(seq[-1], float)
        ab = b - a
        n = np.hypot(*ab)
        p = np.array(seq[1:-1], float)
        d = (np.abs(ab[0] * (p[:, 1] - a[1]) - ab[1] * (p[:, 0] - a[0])) / n if n
             else np.hypot(p[:, 0] - a[0], p[:, 1] - a[1]))
        i = int(np.argmax(d))
        if d[i] <= eps:
            return [seq[0], seq[-1]]
        left = rdp(seq[:i + 2])
        return left[:-1] + rdp(seq[i + 1:])
    far = max(range(len(pts)), key=lambda i: (pts[i][0] - pts[0][0]) ** 2 + (pts[i][1] - pts[0][1]) ** 2)
    return rdp(pts[:far + 1])[:-1] + rdp(pts[far:] + [pts[0]])[:-1]


def main():
    outs = [simplify(smooth(lp), EPS) for lp in loops(edges(mask())) if len(lp) > 12]
    d = []
    for lp in outs:
        c = ["%.1f %.1f" % ((x - 1) / UP, (y - 1) / UP) for x, y in lp]
        d.append("M" + " L".join(c) + "Z")
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d"><path fill-rule="evenodd" d="%s"/></svg>\n'
           % (BOX[2] - BOX[0], BOX[3] - BOX[1], "".join(d)))
    pathlib.Path(OUT).write_text(svg)
    print("%s: %d outlines, %d points, %d bytes" % (OUT, len(outs), sum(map(len, outs)), len(svg)))


if __name__ == "__main__":
    main()
