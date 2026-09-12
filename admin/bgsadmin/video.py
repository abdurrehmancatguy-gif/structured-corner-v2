"""Films for the homepage row (docs/PLAN.md security_model item 9).

A film is only probed when it is staged; the transcode takes longer than a
request should, so it runs as a background job when the film is attached.
ffprobe and ffmpeg always get an argv list, never a shell, and are told the
container (-f mov) and allowed the file protocol alone, so a crafted file
cannot send them to a playlist, a concat list, another file or the network.
"""
import json
import os
import subprocess

from PIL import Image

from . import media
from .errors import ApiError

PROBE_TIMEOUT = 20
TRANSCODE_TIMEOUT = 180
MAX_SECONDS = 30
MIN_W, MIN_H = 540, 960


def _bad(message, code="bad_video", details=None):
    return ApiError(422, code, message, details)


def tool(app, name):
    path = (app.probes or {}).get(name)
    if not path:
        raise ApiError(503, "tool_missing", "Films cannot be uploaded: %s is not installed on this computer." % name)
    return path


def _run(argv, timeout, what):
    try:
        return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise _bad("%s took longer than %d s and was stopped." % (what, timeout), "video_timeout")


def _check(p, message):
    if p.returncode != 0:
        tail = [l for l in p.stderr.decode("utf-8", "replace").splitlines() if l.strip()][-1:]
        raise _bad(message, "video_failed", {"tool": tail[0][:300] if tail else ""})


def _rotation(stream):
    """Phones store portrait films as landscape frames plus a rotation."""
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                return int(round(abs(float(sd["rotation"])))) % 360
            except (TypeError, ValueError):
                return 0
    try:
        return int(round(abs(float((stream.get("tags") or {}).get("rotate", 0))))) % 360
    except (TypeError, ValueError):
        return 0


def _duration(info, stream):
    for v in ((info.get("format") or {}).get("duration"), stream.get("duration")):
        try:
            d = float(v)
        except (TypeError, ValueError):
            continue
        if d > 0:
            return d
    return None


def probe(ffprobe, path):
    """One H.264 or HEVC stream, portrait, at least 540x960, at most 30 s."""
    argv = [ffprobe, "-v", "error", "-protocol_whitelist", "file", "-f", "mov", "-print_format", "json",
            "-show_format", "-show_streams", str(path)]
    p = _run(argv, PROBE_TIMEOUT, "Reading the film")
    try:
        info = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
    except ValueError:
        info = {}
    if p.returncode != 0 or not info.get("streams"):
        raise _bad("The film could not be read. Export it again as an MP4 (H.264 or HEVC) and retry.")
    vids = [s for s in info["streams"] if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")]
    if len(vids) != 1:
        raise _bad("The file needs exactly one video track; it has %d." % len(vids))
    v = vids[0]
    if v.get("codec_name") not in ("h264", "hevc"):
        raise _bad("The film is encoded as %s; export it as H.264 or HEVC." % (v.get("codec_name") or "an unknown codec"))
    w, h = int(v.get("width") or 0), int(v.get("height") or 0)
    if _rotation(v) % 180 == 90:
        w, h = h, w
    if h <= w:
        raise _bad("The row shows films upright (9:16); this one is %dx%d, landscape or square." % (w, h), "not_portrait")
    if w < MIN_W or h < MIN_H:
        raise _bad("A film needs to be at least %dx%d; this one is %dx%d." % (MIN_W, MIN_H, w, h), "too_small")
    dur = _duration(info, v)
    if dur is None:
        raise _bad("The film's length could not be read. Export it again and retry.")
    # a container can round a 30 s film up by a frame or two
    if dur > MAX_SECONDS + 0.05:
        raise _bad("A film can be at most %d s long; this one is %.1f s. Trim it first." % (MAX_SECONDS, dur), "too_long")
    if dur < 1:
        raise _bad("The film is shorter than a second.", "too_short")
    return {"width": w, "height": h, "duration": round(dur, 2), "codec": v["codec_name"]}


def dimensions(ffprobe, path):
    """Width, height and length for the library list, without the upload
    rules; Nones when the file cannot be read."""
    try:
        p = subprocess.run([ffprobe, "-v", "error", "-protocol_whitelist", "file", "-f", "mov", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height:format=duration", "-of", "json", str(path)],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=PROBE_TIMEOUT)
        j = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
        s = (j.get("streams") or [{}])[0]
        d = float((j.get("format") or {}).get("duration") or 0)
        return s.get("width"), s.get("height"), round(d, 2) if d > 0 else None
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError):
        return None, None, None


def stage(app, path, dest_base):
    """Check an uploaded film and keep it as the staged master. It is not
    re-encoded here: that happens when it is attached."""
    ffprobe = tool(app, "ffprobe")
    tool(app, "ffmpeg")
    with open(path, "rb") as f:
        media.check_magic(f.read(64), "video/mp4")
    info = probe(ffprobe, path)
    os.replace(str(path), "%s.mp4" % dest_base)
    return dict(info, ext="mp4")


def transcode(app, src, out, log):
    """The house film (540x960, 30 fps, H.264 High, no sound, faststart), its
    metadata stripped the way tools/strip_metadata.py does it, and a 480x854
    poster cut at 0.5 s. Returns the two finished files, both in out."""
    ffmpeg, ffprobe = tool(app, "ffmpeg"), tool(app, "ffprobe")
    raw, clean, frame, still = out / "transcoded.mp4", out / "film.mp4", out / "still.png", out / "still.jpg"
    log("Converting the film to 540x960 at 30 frames a second.")
    _check(_run([ffmpeg, "-nostdin", "-protocol_whitelist", "file", "-f", "mov", "-i", str(src), "-an", "-t", "30",
                 "-vf", "scale=540:960:force_original_aspect_ratio=increase,crop=540:960",
                 "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30",
                 "-b:v", "650k", "-maxrate", "900k", "-bufsize", "1300k", "-movflags", "+faststart", str(raw)],
                TRANSCODE_TIMEOUT, "Converting the film"), "The film could not be converted.")
    log("Removing the encoder's settings and the file's tags.")
    _check(_run([ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file", "-f", "mov", "-i", str(raw),
                 "-map", "0", "-c", "copy", "-bsf:v", "filter_units=remove_types=6", "-map_metadata", "-1",
                 "-map_chapters", "-1", "-metadata:s:v:0", "handler_name=", "-metadata:s:v:0", "encoder=",
                 "-fflags", "+bitexact", "-movflags", "+faststart", str(clean)],
                TRANSCODE_TIMEOUT, "Cleaning the film"), "The film's metadata could not be removed.")
    log("Cutting the poster at 0.5 s.")
    _check(_run([ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file", "-f", "mov", "-ss", "0.5",
                 "-i", str(clean), "-frames:v", "1", "-vf", "scale=480:854", str(frame)],
                PROBE_TIMEOUT, "Cutting the poster"), "The poster could not be cut from the film.")
    with Image.open(frame) as im:
        im.convert("RGB").save(still, "JPEG", quality=media.QUALITY, optimize=True, progressive=True)
    info = probe(ffprobe, clean)
    if (info["width"], info["height"]) != (MIN_W, MIN_H):
        raise _bad("The converted film came out %dx%d instead of 540x960." % (info["width"], info["height"]), "video_failed")
    return clean, still
