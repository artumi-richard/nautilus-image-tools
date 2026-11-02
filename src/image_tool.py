#!/usr/bin/env python3
"""Helper for the Nautilus Image Tools extension.

Runs outside the Nautilus process so long conversions never block the file
manager and a crash here can't take Nautilus down.

Usage:
    image_tool.py convert --format jpg FILE...
    image_tool.py resize --size 1280 [--format jpg] FILE...
    image_tool.py resize --scale 50 [--format jpg] FILE...
    image_tool.py info FILE...
"""

import argparse
import math
import os
import shutil
import subprocess
import sys

QUALITY = 85
FORMATS = {"jpg": "JPG", "png": "PNG", "webp": "WebP"}
# Map source extensions onto the formats we write when "keep format" is used.
EXT_ALIASES = {"jpeg": "jpg", "jpe": "jpg", "jfif": "jpg"}

IM = shutil.which("magick") or shutil.which("convert")
IDENTIFY = [shutil.which("magick"), "identify"] if shutil.which("magick") else [shutil.which("identify")]


# --------------------------------------------------------------------------
# Conversion
# --------------------------------------------------------------------------

def notify(summary, body="", error=False):
    cmd = ["notify-send", "--app-name=Image Tools", "--icon",
           "dialog-error" if error else "image-x-generic", summary]
    if body:
        cmd.append(body)
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        print(summary, body, file=sys.stderr)


def unique_path(path, src):
    """Return path, or path with -1, -2… appended so we never clobber anything."""
    stem, ext = os.path.splitext(path)
    candidate, n = path, 1
    while os.path.exists(candidate) or os.path.abspath(candidate) == os.path.abspath(src):
        candidate = f"{stem}-{n}{ext}"
        n += 1
    return candidate


def target_format(src, requested):
    if requested:
        return requested
    ext = os.path.splitext(src)[1].lower().lstrip(".")
    ext = EXT_ALIASES.get(ext, ext)
    # Formats we can't (or shouldn't) write back, e.g. HEIC, fall back to JPG.
    return ext if ext in FORMATS or ext in ("gif", "tif", "tiff", "avif") else "jpg"


def fits_within(src, size):
    res = subprocess.run(IDENTIFY + ["-quiet", "-format", "%w %h", f"{src}[0]"],
                         capture_output=True, text=True)
    try:
        w, h = map(int, res.stdout.split())
    except ValueError:
        return False
    return max(w, h) <= size


def build_command(src, out, fmt, size, scale=None):
    single_frame = fmt in ("jpg", "png")
    cmd = [IM, f"{src}[0]" if single_frame else src]
    if not single_frame:
        cmd.append("-coalesce")
    # Apply EXIF rotation before we throw the EXIF away.
    cmd.append("-auto-orient")
    if size:
        # ">" = only ever shrink, never enlarge.
        cmd += ["-resize", f"{size}x{size}>"]
    elif scale:
        cmd += ["-resize", f"{scale}%"]
    # Drop EXIF/GPS/comments but keep the ICC profile so colours stay right.
    cmd += ["+profile", "!icc,*"]
    if fmt == "jpg":
        cmd += ["-background", "white", "-alpha", "remove", "-alpha", "off",
                "-quality", str(QUALITY), "-interlace", "Plane"]
    elif fmt == "webp":
        cmd += ["-quality", str(QUALITY)]
    cmd.append(out)
    return cmd


def process(files, fmt=None, size=None, scale=None):
    done, skipped, failed = [], [], []
    for src in files:
        out_fmt = target_format(src, fmt)
        src_ext = EXT_ALIASES.get(os.path.splitext(src)[1].lower().lstrip("."),
                                  os.path.splitext(src)[1].lower().lstrip("."))
        if src_ext == out_fmt and not scale and (not size or fits_within(src, size)):
            skipped.append(os.path.basename(src))
            continue
        stem = os.path.splitext(src)[0]
        suffix = f"-{size}" if size else (f"-{scale}pct" if scale else "")
        out = unique_path(f"{stem}{suffix}.{out_fmt}", src)
        result = subprocess.run(build_command(src, out, out_fmt, size, scale),
                                capture_output=True, text=True)
        if result.returncode == 0 and os.path.exists(out):
            done.append(os.path.basename(out))
        else:
            failed.append(f"{os.path.basename(src)}: {result.stderr.strip().splitlines()[-1:] or ['unknown error']}")
            if os.path.exists(out) and os.path.getsize(out) == 0:
                os.remove(out)

    action = f"Resized to {size}px" if size else f"Resized to {scale}%" if scale else f"Converted to {FORMATS.get(out_fmt, out_fmt.upper())}"
    if done:
        body = done[0] if len(done) == 1 else f"{len(done)} images"
        if skipped:
            body += f"\nSkipped {len(skipped)} (no change needed)"
        notify(action, body)
    elif skipped and not failed:
        why = f"Already {size}px or smaller" if size else "Already in that format"
        notify("Nothing to do", f"{why}: " + ", ".join(skipped))
    if failed:
        notify(f"{len(failed)} image(s) failed", "\n".join(failed), error=True)
    return 1 if failed else 0


# --------------------------------------------------------------------------
# Image details
# --------------------------------------------------------------------------

# identify format fields, one per line, read from the first frame.
INFO_FIELDS = [
    ("format", "%m"),
    ("width", "%w"),
    ("height", "%h"),
    ("colorspace", "%[colorspace]"),
    ("depth", "%z"),
    ("alpha", "%A"),
    ("xres", "%x"),
    ("yres", "%y"),
    ("units", "%U"),
    ("orientation", "%[orientation]"),
    ("icc", "%[icc:description]"),
    ("date", "%[EXIF:DateTimeOriginal]"),
    ("make", "%[EXIF:Make]"),
    ("model", "%[EXIF:Model]"),
    ("lens", "%[EXIF:LensModel]"),
    ("exposure", "%[EXIF:ExposureTime]"),
    ("fnumber", "%[EXIF:FNumber]"),
    ("iso", "%[EXIF:PhotographicSensitivity]"),
    ("iso_old", "%[EXIF:ISOSpeedRatings]"),
    ("focal", "%[EXIF:FocalLength]"),
    ("gps", "%[EXIF:GPSLatitude]"),
]


def human_size(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


def rational(value):
    """EXIF rationals look like '1/250' or '28/10'."""
    try:
        if "/" in value:
            a, b = value.split("/", 1)
            return float(a) / float(b)
        return float(value)
    except (ValueError, ZeroDivisionError):
        return None


def aspect_ratio(w, h):
    g = math.gcd(w, h)
    rw, rh = w // g, h // g
    if rw <= 32 and rh <= 32:
        return f"{rw}:{rh}"
    return f"{w / h:.2f}:1"


def read_info(path):
    fmt = "\n".join(f for _, f in INFO_FIELDS)
    res = subprocess.run(IDENTIFY + ["-quiet", "-format", fmt, f"{path}[0]"],
                         capture_output=True, text=True)
    if res.returncode != 0:
        return None, res.stderr.strip() or "Could not read image"
    values = res.stdout.split("\n")
    raw = {k: (values[i].strip() if i < len(values) else "") for i, (k, _) in enumerate(INFO_FIELDS)}

    frames = subprocess.run(IDENTIFY + ["-quiet", "-format", "x", path],
                            capture_output=True, text=True).stdout.count("x")

    w, h = int(raw["width"]), int(raw["height"])
    rows = []
    rows.append(("Format", raw["format"]))
    dims = f"{w} × {h} pixels"
    if raw["orientation"] in ("RightTop", "LeftBottom", "LeftTop", "RightBottom"):
        dims += f"  (shown rotated: {h} × {w})"
    rows.append(("Resolution", dims))
    mp = w * h / 1_000_000
    rows.append(("Megapixels", f"{mp:.1f} MP" if mp >= 0.1 else f"{mp:.2f} MP"))
    rows.append(("Aspect ratio", aspect_ratio(w, h)))
    size = os.path.getsize(path)
    rows.append(("File size", human_size(size) if size < 1024 else f"{human_size(size)}  ({size:,} bytes)"))

    xres = rational(raw["xres"].split()[0]) if raw["xres"] else None
    unit = "DPI" if "Inch" in raw["units"] else ("dots/cm" if "Centimeter" in raw["units"] else "")
    if xres and xres > 1 and unit:
        rows.append(("Print density", f"{xres:g} {unit}"))
        if unit == "DPI":
            rows.append(("Print size", f'{w / xres:.1f}" × {h / xres:.1f}"  ({w / xres * 2.54:.1f} × {h / xres * 2.54:.1f} cm)'))

    colour = raw["colorspace"]
    if raw["depth"]:
        colour += f", {raw['depth']}-bit"
    if raw["alpha"].lower() in ("true", "blend"):
        colour += ", with transparency"
    rows.append(("Colour", colour))
    if raw["icc"]:
        rows.append(("Colour profile", raw["icc"]))
    if frames > 1:
        rows.append(("Frames", str(frames)))

    if raw["date"]:
        d = raw["date"]
        rows.append(("Taken", d[:10].replace(":", "-") + d[10:]))
    camera = " ".join(x for x in (raw["make"], raw["model"]) if x)
    if raw["make"] and raw["model"].startswith(raw["make"]):
        camera = raw["model"]
    if camera:
        rows.append(("Camera", camera))
    if raw["lens"]:
        rows.append(("Lens", raw["lens"]))
    exposure = []
    exp = rational(raw["exposure"]) if raw["exposure"] else None
    if exp:
        exposure.append(f"1/{round(1 / exp)} s" if exp < 1 else f"{exp:g} s")
    fn = rational(raw["fnumber"]) if raw["fnumber"] else None
    if fn:
        exposure.append(f"f/{fn:.1f}")
    iso = raw["iso"] or raw["iso_old"]
    if iso:
        exposure.append(f"ISO {iso}")
    fl = rational(raw["focal"]) if raw["focal"] else None
    if fl:
        exposure.append(f"{fl:g} mm")
    if exposure:
        rows.append(("Exposure", "  ·  ".join(exposure)))
    if raw["gps"]:
        rows.append(("Location", "Contains GPS coordinates"))
    return rows, None


def show_info(files):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gio, Gtk

    def on_activate(app):
        win = Adw.ApplicationWindow(application=app)
        win.set_title("Image Details" if len(files) == 1 else f"Image Details ({len(files)} images)")
        win.set_default_size(520, 640 if len(files) == 1 else 720)

        page = Adw.PreferencesPage()
        for path in files:
            group = Adw.PreferencesGroup(title=os.path.basename(path).replace("&", "&amp;"))
            group.set_description(os.path.dirname(path))

            if len(files) == 1:
                pic = Gtk.Picture.new_for_filename(path)
                pic.set_can_shrink(True)
                pic.set_content_fit(Gtk.ContentFit.CONTAIN)
                pic.set_size_request(-1, 220)
                pic.set_margin_bottom(12)
                group.add(pic)

            rows, err = read_info(path)
            if err:
                row = Adw.ActionRow(title="Error", subtitle=err)
                group.add(row)
            for label, value in rows or []:
                row = Adw.ActionRow(title=label, subtitle=value.replace("&", "&amp;"))
                row.add_css_class("property")
                row.set_subtitle_selectable(True)
                group.add(row)
            page.add(group)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        toolbar.set_content(page)
        win.set_content(toolbar)

        esc = Gtk.ShortcutController()
        esc.add_shortcut(Gtk.Shortcut.new(Gtk.ShortcutTrigger.parse_string("Escape"),
                                          Gtk.CallbackAction.new(lambda *a: win.close() or True)))
        win.add_controller(esc)
        win.present()

    app = Adw.Application(application_id="uk.artumi.ImageTools.Details",
                          flags=Gio.ApplicationFlags.NON_UNIQUE)
    app.connect("activate", on_activate)
    return app.run([sys.argv[0]])


# --------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert")
    c.add_argument("--format", required=True, choices=FORMATS)
    c.add_argument("files", nargs="+")
    r = sub.add_parser("resize")
    how = r.add_mutually_exclusive_group(required=True)
    how.add_argument("--size", type=int, help="longest edge in pixels (never enlarges)")
    how.add_argument("--scale", type=int, help="percentage, e.g. 50")
    r.add_argument("--format", choices=FORMATS)
    r.add_argument("files", nargs="+")
    i = sub.add_parser("info")
    i.add_argument("files", nargs="+")
    i.add_argument("--text", action="store_true", help="print to terminal instead of a window")
    args = p.parse_args()

    if args.cmd == "info":
        if args.text:
            for f in args.files:
                rows, err = read_info(f)
                print(f"== {f}")
                print(err or "\n".join(f"{k:>15}: {v}" for k, v in rows))
            return 0
        return show_info(args.files)
    if not IM:
        notify("ImageMagick not found", "Install the imagemagick package", error=True)
        return 1
    if args.cmd == "convert":
        return process(args.files, fmt=args.format)
    return process(args.files, fmt=args.format, size=args.size, scale=args.scale)


if __name__ == "__main__":
    sys.exit(main())
