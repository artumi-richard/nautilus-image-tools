"""Nautilus extension: right-click → Image Tools on image files.

Only builds the menu; all real work is done by image_tool.py in a separate
process so Nautilus never blocks.
"""

import os
import shutil
import subprocess

import gi

try:
    gi.require_version("Nautilus", "4.0")
except ValueError:
    pass
from gi.repository import GObject, Nautilus

HELPER = os.path.join(os.path.dirname(os.path.realpath(__file__)), "image_tool.py")
PYTHON = shutil.which("python3") or "/usr/bin/python3"

FORMATS = [("jpg", "JPG"), ("png", "PNG"), ("webp", "WebP")]
SIZES = [1920, 1280, 800]
SCALES = [50]


def _paths(files):
    out = []
    for f in files:
        if f.is_directory() or not f.get_mime_type().startswith("image/"):
            return None
        loc = f.get_location()
        path = loc.get_path() if loc else None
        if not path:
            return None
        out.append(path)
    return out


def _run(args):
    subprocess.Popen([PYTHON, HELPER] + args, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


class ImageToolsMenu(GObject.GObject, Nautilus.MenuProvider):
    def _item(self, name, label, args, paths):
        item = Nautilus.MenuItem(name=f"ImageTools::{name}", label=label)
        item.connect("activate", lambda *_: _run(args + ["--"] + paths))
        return item

    def get_file_items(self, *args):
        files = args[-1]  # nautilus-python 3 passes (window, files); 4 passes (files)
        paths = _paths(files) if files else None
        if not paths:
            return []

        top = Nautilus.MenuItem(name="ImageTools::Top", label="Image Tools")
        menu = Nautilus.Menu()
        top.set_submenu(menu)

        # Convert to ▸
        conv = Nautilus.MenuItem(name="ImageTools::Convert", label="Convert to")
        conv_menu = Nautilus.Menu()
        conv.set_submenu(conv_menu)
        for fmt, label in FORMATS:
            conv_menu.append_item(self._item(f"Convert{fmt}", label,
                                             ["convert", "--format", fmt], paths))
        menu.append_item(conv)

        # Resize ▸ 1920px ▸ Keep format / JPG / PNG / WebP
        res = Nautilus.MenuItem(name="ImageTools::Resize", label="Resize")
        res_menu = Nautilus.Menu()
        res.set_submenu(res_menu)
        for size in SIZES:
            s_item = Nautilus.MenuItem(name=f"ImageTools::Resize{size}", label=f"{size} px")
            s_menu = Nautilus.Menu()
            s_item.set_submenu(s_menu)
            s_menu.append_item(self._item(f"Resize{size}keep", "Keep format",
                                          ["resize", "--size", str(size)], paths))
            for fmt, label in FORMATS:
                s_menu.append_item(self._item(f"Resize{size}{fmt}", f"as {label}",
                                              ["resize", "--size", str(size), "--format", fmt], paths))
            res_menu.append_item(s_item)
        for pct in SCALES:
            p_item = Nautilus.MenuItem(name=f"ImageTools::Scale{pct}", label=f"{pct}%")
            p_menu = Nautilus.Menu()
            p_item.set_submenu(p_menu)
            p_menu.append_item(self._item(f"Scale{pct}keep", "Keep format",
                                          ["resize", "--scale", str(pct)], paths))
            for fmt, label in FORMATS:
                p_menu.append_item(self._item(f"Scale{pct}{fmt}", f"as {label}",
                                              ["resize", "--scale", str(pct), "--format", fmt], paths))
            res_menu.append_item(p_item)
        menu.append_item(res)

        menu.append_item(self._item("Info", "Image Details…", ["info"], paths))
        return [top]

    def get_background_items(self, *args):
        return []
