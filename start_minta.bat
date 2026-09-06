@echo off
chcp 65001 >nul
title Minta (open) - one-click
echo ================================================
echo   Minta (open) - one-click launcher
echo   Start engine + pick your editor. Data stays local.
echo ================================================
echo.
cd /d "%~dp0"

rem -- locate python (py -3 first, then python) --
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo [ERROR] Python 3.10+ not found. Install from https://www.python.org/
  pause & exit /b 1
)

rem -- engine: skip if 8772 already up --
set "CODE="
call set "CODE=%%curl -s -o nul -w "%%{http_code}" http://localhost:8772/ping%%"
if "%CODE%"=="200" (
  echo   [OK] Minta engine already running.
) else (
  echo [1/2] Checking dependencies (first run may take a minute)...
  %PY% -m pip install -r requirements.txt >nul 2>nul
  echo [2/2] Starting engine...
  start "Minta engine" %PY% minta_cli.py start
  timeout /t 6 /nobreak >nul
)
start "" http://localhost:8772

:menu
echo.
echo  ================================================
echo   Pick your editor (connect once, then always works):
echo     1) Claude Code
echo     2) Codex CLI
echo     3) DeepSeek Harness (dsh)
echo     4) Cursor
echo     5) 只要看板 / Exit
echo  ================================================
set /p CH=选择 [1-5]: 
if "%CH%"=="1" (
  %PY% minta_cli.py connect --claude
  where claude >nul 2>nul && ( start "" claude ) || echo   [提示] 没找到 claude 命令:装好 Claude Code 后重开本窗口.
)
if "%CH%"=="2" (
  %PY% minta_cli.py connect --codex
  where codex >nul 2>nul && ( start "" codex ) || echo   [提示] 没找到 codex 命令.
)
if "%CH%"=="3" (
  dsh plugin --profile web add @xxinchen/dsh-plugin
  where npx >nul 2>nul && ( start "" cmd /k npx @deepseek-ai/dsh web ) || echo   [提示] 需要 Node.js:install from nodejs.org
)
if "%CH%"=="4" (
  %PY% minta_cli.py connect --cursor
  echo   [OK] 已写入 Cursor 配置,打开 Cursor 直接使用.
)
if "%CH%"=="5" (
  echo   Done. Dashboard: http://localhost:8772  (可关本窗口, 引擎在后台运行)
  pause & exit /b 0
)
echo.
goto menu
