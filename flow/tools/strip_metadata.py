"""Strip metadata from every image and video the site publishes.

    python3 tools/strip_metadata.py            # from flow/
    python3 tools/strip_metadata.py --check    # report only, change nothing

Nothing is re-compressed, so no quality is lost:
- JPEG: the EXIF, XMP, IPTC, comment and other application blocks are cut out
  of the file; the picture data is copied as it is. JFIF and a colour profile
  stay (the profile decides how the colours look).
- PNG: text, time and EXIF chunks are dropped; a colour profile is kept.
- MP4: remuxed with ffmpeg (-c copy): the container's tags, the encoder names,
  the track handler names and the x264 settings the encoder writes into the
  video stream (an SEI unit) are removed; the frames are untouched.

Run tools/make_derivatives.py and build.py after it: the originals' bytes
change, so their copies are re-recorded and every ?v= moves.
"""
import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile

FLOW = pathlib.Path(__file__).resolve().parent.parent
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
KEEP_JPEG = {0xE0}                      # APP0 (JFIF); APP2 kept only when it is an ICC profile
DROP_PNG = {b"tEXt", b"zTXt", b"iTXt", b"eXIf", b"tIME"}


def jpeg_clean(b):
    out, i, dropped = bytearray(b[:2]), 2, []
    while i < len(b) - 1:
        if b[i] != 0xFF:
            return None, []            # not a marker where one should be: leave the file alone
        m = b[i + 1]
        if m == 0xDA:                   # start of scan: the rest is picture data
            out += b[i:]
            return bytes(out), dropped
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            out += b[i:i + 2]
            i += 2
            continue
        n = struct.unpack(">H", b[i + 2:i + 4])[0]
        seg = b[i:i + 2 + n]
        body = b[i + 4:i + 2 + n]
        keep = (0xE0 <= m <= 0xEF and (m in KEEP_JPEG or (m == 0xE2 and body.startswith(b"ICC_PROFILE")))) \
            or not (0xE0 <= m <= 0xEF or m == 0xFE)
        if keep:
            out += seg
        else:
            dropped.append("COM" if m == 0xFE else "APP%d" % (m - 0xE0))
        i += 2 + n
    return bytes(out), dropped


def png_clean(b):
    out, i, dropped = bytearray(b[:8]), 8, []
    while i < len(b):
        n = struct.unpack(">I", b[i:i + 4])[0]
        t = b[i + 4:i + 8]
        chunk = b[i:i + 12 + n]
        if t in DROP_PNG:
            dropped.append(t.decode("latin1"))
        else:
            out += chunk
        i += 12 + n
        if t == b"IEND":
            break
    return bytes(out), dropped


def mp4_tags(p):
    j = json.loads(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format_tags:stream_tags",
                                   "-of", "json", str(p)], capture_output=True, text=True).stdout or "{}")
    tags = {k: v for k, v in j.get("format", {}).get("tags", {}).items()
            if k not in ("major_brand", "minor_version", "compatible_brands")}
    for s in j.get("streams", []):
        tags.update({"stream." + k: v for k, v in s.get("tags", {}).items() if k != "language"})
    return tags


def mp4_clean(p):
    fd, tmp = tempfile.mkstemp(suffix=".mp4", dir=str(p.parent))
    os.close(fd)
    r = subprocess.run([FFMPEG, "-nostdin", "-y", "-v", "error", "-i", str(p), "-map", "0", "-c", "copy",
                        "-bsf:v", "filter_units=remove_types=6", "-map_metadata", "-1", "-map_chapters", "-1",
                        "-metadata:s:v:0", "handler_name=", "-metadata:s:v:0", "encoder=",
                        "-fflags", "+bitexact", "-movflags", "+faststart", tmp], capture_output=True, text=True)
    if r.returncode:
        os.unlink(tmp)
        raise SystemExit("ffmpeg failed on %s: %s" % (p, r.stderr[-400:]))
    os.replace(tmp, str(p))


def main():
    check = "--check" in sys.argv
    changed = 0
    for p in sorted((FLOW / "assets").rglob("*")):
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in (".jpg", ".jpeg", ".png"):
            b = p.read_bytes()
            new, dropped = (jpeg_clean if ext != ".png" else png_clean)(b)
            if new and dropped and new != b:
                print("%-50s %s" % (p.relative_to(FLOW), ", ".join(sorted(set(dropped)))))
                changed += 1
                if not check:
                    p.write_bytes(new)
        elif ext == ".mp4":
            tags = mp4_tags(p)
            if tags:
                print("%-50s %s" % (p.relative_to(FLOW), ", ".join(sorted(tags))))
                changed += 1
                if not check:
                    mp4_clean(p)
    print("%d file(s) %s" % (changed, "carry metadata" if check else "cleaned"))


if __name__ == "__main__":
    main()
