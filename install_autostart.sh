#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
APPLICATIONS_DIR="$HOME/.local/share/applications"
AUTOSTART_FILE="$AUTOSTART_DIR/artwall.desktop"
APPLICATION_FILE="$APPLICATIONS_DIR/artwall.desktop"

mkdir -p "$AUTOSTART_DIR" "$APPLICATIONS_DIR"

cat > "$AUTOSTART_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=artwall
Comment=Cambia el wallpaper con obras de museo y muestra un icono en la bandeja
Exec=$SCRIPT_DIR/run.sh tray
Terminal=false
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
EOF

cat > "$APPLICATION_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=artwall
Comment=Cambia el wallpaper con obras de museo y muestra un icono en la bandeja
Exec=$SCRIPT_DIR/run.sh tray
Icon=$SCRIPT_DIR/artwall-tray.svg
Terminal=false
StartupNotify=true
Categories=Utility;
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR"
fi

echo "Autostart instalado en: $AUTOSTART_FILE"
echo "Lanzador del menu instalado en: $APPLICATION_FILE"
echo "Se ejecutara al iniciar sesion con el modo bandeja."
