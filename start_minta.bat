@echo off
setlocal
title Minta (open) launcher
cd /d "%~dp0"

rem -- find python: prefer py -3, then python --
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [ERROR] Python 3.10+ not found. Get it at https://www.python.org/
  pause
  exit /b 1
)

rem -- skip engine start if 8772 already serving --
set "CODE="
for /f "delims=" %%a in ('curl -s -o nul -w "%%{http_code}" http://localhost:8772/ping 2^>nul') do set "CODE=%%a"
if "%CODE%"=="200" (
  echo [OK] Minta engine already running.
) else (
  echo [1/2] Installing dependencies - first run only...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 echo [WARN] dependency install reported errors - continuing.
  echo [2/2] Starting engine...
  start "Minta engine" %PY% minta_cli.py start
  timeout /t 6 /nobreak >nul
)
start "" http://localhost:8772

:menu
echo.
echo ==================================================
echo   Pick your editor (connect once, then it always works):
echo     1) Claude Code
echo     2) Codex CLI
echo     3) DeepSeek Harness (dsh)
echo     4) Cursor
echo     5) Done (dashboard only)
echo ==================================================
set /p CH=Choice [1-5]:
if "%CH%"=="1" (
  %PY% minta_cli.py connect --claude
  where claude >nul 2>nul
  if not errorlevel 1 start "" claude
  if errorlevel 1 echo [hint] claude CLI not found - install Claude Code, then rerun.
)
if "%CH%"=="2" (
  %PY% minta_cli.py connect --codex
  where codex >nul 2>nul
  if not errorlevel 1 start "" codex
  if errorlevel 1 echo [hint] codex CLI not found - install Codex, then rerun.
)
if "%CH%"=="3" (
  dsh plugin --profile web add @xxinchen/dsh-plugin
  where npx >nul 2>nul
  if not errorlevel 1 start "" cmd /k npx @deepseek-ai/dsh web
  if errorlevel 1 echo [hint] Node.js needed - install from https://nodejs.org
)
if "%CH%"=="4" (
  %PY% minta_cli.py connect --cursor
  echo [OK] Cursor config written - open Cursor and start using it.
)
if "%CH%"=="5" (
  echo Done. Dashboard: http://localhost:8772
  pause
  exit /b 0
)
goto menu
