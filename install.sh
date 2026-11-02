#!/usr/bin/env bash
# Install (symlink) the Image Tools extension for the current user.
# Re-run safe. Use ./install.sh --uninstall to remove.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/src" && pwd)"
DEST="$HOME/.local/share/nautilus-python/extensions"
LINK="$DEST/nautilus_image_tools.py"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$LINK"
    echo "Removed $LINK"
    nautilus -q 2>/dev/null || true
    exit 0
fi

missing=()
dpkg -s python3-nautilus >/dev/null 2>&1 || missing+=(python3-nautilus)
command -v convert >/dev/null || command -v magick >/dev/null || missing+=(imagemagick)
command -v notify-send >/dev/null || missing+=(libnotify-bin)
if (( ${#missing[@]} )); then
    echo "Missing packages: ${missing[*]}"
    echo "Run: sudo apt install ${missing[*]}"
    exit 1
fi

mkdir -p "$DEST"
chmod +x "$SRC/image_tool.py"
ln -sfn "$SRC/nautilus_image_tools.py" "$LINK"
echo "Linked $LINK -> $SRC/nautilus_image_tools.py"

echo "Restarting Nautilus…"
nautilus -q 2>/dev/null || true
echo "Done. Right-click an image → Image Tools."
