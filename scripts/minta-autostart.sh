#!/bin/bash
# Minta Auto-Start (macOS/Linux)
# To enable: add this line to crontab: @reboot /path/to/minta/scripts/minta-autostart.sh
cd "$(dirname "$0")/.."
python minta_cli.py start
