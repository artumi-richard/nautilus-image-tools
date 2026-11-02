# Nautilus Image Tools

> ⚠️ **Vibecoded.** This was written almost entirely by an AI coding assistant
> (Claude Code) with light human direction and testing. It works on my machine
> (Ubuntu, Nautilus 46, ImageMagick 6), but it hasn't been carefully reviewed.
> Read the code before trusting it with images you care about. Originals are never
> modified, though.

Right-click image files in Nautilus (GNOME Files) → **Image Tools**:

- **Convert to** ▸ JPG / PNG / WebP
- **Resize** ▸ 1920 / 1280 / 800 px (longest edge) or 50% ▸ Keep format / as JPG / as PNG / as WebP
- **Image Details…** shows resolution, megapixels, aspect ratio, file size, DPI/print size, colour, and camera EXIF data

Works on multiple selected files. The menu appears only when every selected file is a local image.

## Behaviour

- The original file is never modified. Output goes beside it: `photo.webp`, `photo-1280.jpg`, `shot-50pct.png`, and `-1`, `-2`… are added rather than overwriting an existing file.
- Images are only shrunk, never enlarged. Images already within the size limit and in the requested format are skipped.
- EXIF rotation is applied first, then EXIF/GPS metadata is removed. The ICC colour profile is kept.
- JPG/WebP quality is 85. Transparency becomes white when converting to JPG.
- Formats that can't be written (e.g. HEIC) become JPG under "Keep format".
- Work runs in a separate process, and a desktop notification appears when it finishes.

## Install

```sh
git clone https://github.com/artumi-richard/nautilus-image-tools.git
cd nautilus-image-tools
sudo apt install python3-nautilus imagemagick libnotify-bin
./install.sh            # symlinks the extension and restarts Nautilus
./install.sh --uninstall
```

The extension is a symlink into this repo, so edits take effect after `nautilus -q`.

## Files

- `src/nautilus_image_tools.py`: nautilus-python extension (menu only)
- `src/image_tool.py`: the helper that does the work. It can also be used from the CLI:
  `image_tool.py resize --size 1280 --format webp -- *.jpg`, `image_tool.py info --text -- img.png`

Settings (sizes, formats, quality) are constants at the top of each file.

## Requirements

GNOME Files (Nautilus) 43+ with nautilus-python 4 (`python3-nautilus`), ImageMagick 6 or 7,
GTK 4 and libadwaita (`gir1.2-adw-1`) for the details window.

## License

MIT. See [LICENSE](LICENSE).
