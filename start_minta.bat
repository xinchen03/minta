@echo off
chcp 65001 >nul
title Minta (open) - launcher
echo ================================================
echo   Minta (open) - one-click launcher
echo   Starts the engine. Dashboard: http://localhost:8772
echo ================================================
echo.
cd /d "%~dp0"

rem -- locate python (py -3 first, then python) --
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3.10+ not found. Install from https://www.python.org/
  pause
  exit /b 1
)

echo [1/2] Checking dependencies (first run may take a minute)...
%PY% -m pip install -r requirements.txt >nul 2>nul

echo [2/2] Starting engine...
%PY% minta_cli.py start
pause
