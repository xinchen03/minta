@echo off
:: Minta CLI wrapper — put this directory in PATH, then type "minta" anywhere
:: Usage: minta start | minta stop | minta connect | minta launch | ...
python "%~dp0\minta_cli.py" %*
