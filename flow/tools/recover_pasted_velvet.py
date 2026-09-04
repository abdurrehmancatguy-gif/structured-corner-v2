#!/usr/bin/env python3
"""
Recover the four Velvet Spell shots that were pasted into the chat session
rather than saved to disk. Pasted images are stored as base64 inside the
session transcript (.jsonl), so we can pull them back out as real files.

We find the paste by its accompanying text ("do not hardcode", "the 4 i
pasted") instead of a hard-coded line number, then write each image block out.
Point TRANSCRIPT at the session .jsonl and run; the files land next to this
script's OUT and are then renamed/classified by hand (lone vs box) before
import_new_edits.py picks them up.
"""
import json, base64, pathlib, sys

TRANSCRIPT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
OUT = pathlib.Path(__file__).resolve().parent / "_recovered"
MARKERS = ("do not hardcode", "the 4 i pasted", "lone product")
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def text_of(content):
    return " ".join(b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text")


def main():
    if not TRANSCRIPT or not TRANSCRIPT.exists():
        sys.exit("usage: recover_pasted_velvet.py <session.jsonl>")
    OUT.mkdir(exist_ok=True)
    n = 0
    for line in TRANSCRIPT.read_text().splitlines():
        try:
            msg = (json.loads(line).get("message") or {})
        except Exception:
            continue
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        imgs = [b for b in content if isinstance(b, dict) and b.get("type") == "image"]
        if len(imgs) < 4:
            continue
        if not any(m in text_of(content).lower() for m in MARKERS):
            continue
        for i, b in enumerate(imgs, 1):
            src = b.get("source", {})
            if src.get("type") != "base64":
                continue
            ext = EXT.get(src.get("media_type", ""), "png")
            (OUT / ("velvet_paste_%d.%s" % (i, ext))).write_bytes(
                base64.b64decode(src["data"]))
            n += 1
        break
    print("recovered %d images to %s" % (n, OUT))


if __name__ == "__main__":
    main()
