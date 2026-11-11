#!/usr/bin/env bash
# Builds a .deb (Debian 12+/Ubuntu 22.04+) from the PyInstaller output in dist/artilody-rlv-creator
set -euo pipefail
VERSION="${1:?version}"
ARCH="${2:-amd64}"
PKG=artilody-rlv-creator
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$ROOT/build/deb/${PKG}_${VERSION}_${ARCH}"
rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" "$STAGE/opt/$PKG" "$STAGE/usr/bin" "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/512x512/apps" "$STAGE/usr/share/doc/$PKG"
cp -a "$ROOT/dist/$PKG/." "$STAGE/opt/$PKG/"
ln -s "/opt/$PKG/$PKG" "$STAGE/usr/bin/$PKG"
cp "$ROOT/rlvcreator/resources/icon.png" "$STAGE/usr/share/icons/hicolor/512x512/apps/$PKG.png"
cp "$ROOT/LICENSE" "$STAGE/usr/share/doc/$PKG/copyright"
cat > "$STAGE/usr/share/applications/$PKG.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Artilody RLV Creator
GenericName=Real Life Video Creator
Comment=Create Real Life Videos (MP4 + GPX + XML) from GoPro recordings
Exec=$PKG %F
Icon=$PKG
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
MimeType=video/mp4;
StartupWMClass=artilody-rlv-creator
DESK
SIZE=$(du -sk "$STAGE/opt" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<CTRL
Package: $PKG
Version: $VERSION
Section: video
Priority: optional
Architecture: $ARCH
Installed-Size: $SIZE
Depends: libc6 (>= 2.35), libgl1, libegl1, libfontconfig1, libfreetype6, libdbus-1-3, libxkbcommon0, libxkbcommon-x11-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render-util0, libxcb-shape0, libxcb-xfixes0, libxcb-xkb1, libx11-xcb1, libpulse0
Maintainer: Artilody <noreply@github.com>
Homepage: https://github.com/shenphenchoedron-hue/Artilody-RLV-Creator
Description: Real Life Video creator for GoPro recordings
 Extracts GPS data from GoPro videos, lets you cut away unwanted parts
 (video and GPS stay in sync, with undo/redo) and exports an RLV:
 MP4 (H.265/HEVC, 1080p, 30 fps), GPX track and XML description.
CTRL
cat > "$STAGE/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q /usr/share/icons/hicolor || true
exit 0
POST
chmod 755 "$STAGE/DEBIAN/postinst"
find "$STAGE/opt" -type d -exec chmod 755 {} +
mkdir -p "$ROOT/release"
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$ROOT/release/${PKG}_${VERSION}_${ARCH}.deb"
echo "built release/${PKG}_${VERSION}_${ARCH}.deb"
