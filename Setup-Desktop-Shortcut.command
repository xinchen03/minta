#!/bin/bash
# Minta Desktop Setup (macOS/Linux) — double-click to install
DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP="$HOME/Desktop"

# Copy launcher to desktop
cp "$DIR/Start-Minta.sh" "$DESKTOP/Start-Minta.sh"
chmod +x "$DESKTOP/Start-Minta.sh"

echo "✅ Minta launcher added to Desktop"
echo "   Double-click Start-Minta.sh, then open your AI."
