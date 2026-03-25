#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.config/autostart"
TARGET_FILE="$TARGET_DIR/artwall.desktop"

mkdir -p "$TARGET_DIR"

cat > "$TARGET_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=artwall
Comment=Cambia el wallpaper con obras de museo y muestra un icono en la bandeja
Exec=python3 $SCRIPT_DIR/artwall.py tray
Terminal=false
X-GNOME-Autostart-enabled=true
Categories=Utility;
EOF

echo "Autostart instalado en: $TARGET_FILE"
echo "Se ejecutara al iniciar sesion con el modo bandeja."
