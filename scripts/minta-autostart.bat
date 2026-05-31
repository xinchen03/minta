@echo off
REM Minta Auto-Start
REM To enable: copy a shortcut of this file to shell:startup
REM (Win+R → shell:startup → paste shortcut)
cd /d "%~dp0.."
python minta_cli.py start
