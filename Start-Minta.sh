#!/bin/bash
# Minta Silent Starter — double-click (or run) to start Minta in background
# macOS:  chmod +x this file, then double-click in Finder
# Linux:  chmod +x this file, then double-click in file manager
#
# Auto-start on boot:
#   Linux:  cp this file to ~/.config/autostart/
#   macOS:  cp com.minta.starter.plist to ~/Library/LaunchAgents/

# Start-Minta.sh is at the repo root. Use its own directory.
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
nohup python minta_cli.py start > /dev/null 2>&1 &
disown
