#!/usr/bin/env python
"""Minta CLI — one command to manage Minta services.

Usage:
    minta start               Start all services (API, Autopilot, MCP HTTP)
    minta stop                Stop all services
    minta status              Check service health
    minta connect [--editor]  Auto-configure MCP for AI editors
    minta launch [--editor]   Start services + configure + show launch info
    minta init                First-time setup wizard

Supported editors:
    --claude   Claude Code (default)
    --cursor   Cursor IDE
    --codex    Codex CLI
    --vscode   VS Code / GitHub Copilot
    --all      Configure all of the above
"""
import os
import sys
import time
import json
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT / "server"
PID_FILE = ROOT / ".minta_pids.json"

SERVICES = [
    ("Data API", 8772, ["main:app"]),
    ("Autopilot", 18730, ["main:app"]),
    ("MCP HTTP", 18721, ["minta_mcp_http:create_mcp_app", "--factory"]),
]

PROCS = []

# ── Editor MCP configs ──
# Each entry: (name, config_path, needs_type_field)
EDITORS = {
    "claude": {
        "name": "Claude Code",
        "config_path": Path.home() / ".claude" / "settings.json",
        "mcp_key": "mcpServers",
        "entry": {"type": "http", "url": "http://localhost:18721/mcp"},
        "launch_hint": "Run 'claude' in your terminal.",
    },
    "cursor": {
        "name": "Cursor IDE",
        "config_path": Path.home() / ".cursor" / "mcp.json",
        "mcp_key": "mcpServers",
        "entry": {"url": "http://localhost:18721/mcp"},
        "launch_hint": "Open Cursor and check the MCP panel (Ctrl+Shift+P → 'MCP: List Tools').",
    },
    "codex": {
        "name": "Codex CLI",
        "config_path": Path.home() / ".codex" / "mcp.json",
        "mcp_key": "mcpServers",
        "entry": {"url": "http://localhost:18721/mcp"},
        "launch_hint": "Run 'codex' in your terminal.",
    },
    "vscode": {
        "name": "VS Code / Copilot",
        "config_path": Path.home() / ".vscode" / "mcp.json",
        "mcp_key": "mcpServers",
        "entry": {"url": "http://localhost:18721/mcp"},
        "launch_hint": (
            "Add this to your project's .vscode/mcp.json, then open VS Code.\n"
            "  Or copy to ~/.vscode/mcp.json for global use."
        ),
    },
}


# ── Helpers ──

def port_alive(port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", port)) == 0
        sock.close()
        return result
    except Exception:
        return False


def all_services_ready() -> bool:
    return all(port_alive(port) for _, port, _ in SERVICES)


def save_pids():
    pids = {name: proc.pid for name, proc in PROCS if proc.poll() is None}
    if pids:
        PID_FILE.write_text(json.dumps(pids))


def find_python() -> str:
    """Find a Python 3.9+ interpreter."""
    return sys.executable


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _read_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# ── Commands ──

def cmd_start():
    """Start all Minta services in background."""
    if PID_FILE.exists():
        try:
            old = json.loads(PID_FILE.read_text())
            still_alive = {k: v for k, v in old.items() if _pid_running(v)}
            if still_alive:
                print(f"[Minta] Already running: {list(still_alive.keys())}")
                print("  Use 'minta stop' first to restart.")
                return
        except Exception:
            pass

    python = find_python()
    print(f"[Minta] Using Python: {python}")
    print(f"[Minta] Starting services...\n")

    for name, port, args in SERVICES:
        if port_alive(port):
            print(f"  [{name}] :{port} already in use -- skipping")
            continue
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            [python, "-m", "uvicorn"] + args + ["--host", "127.0.0.1", "--port", str(port)],
            cwd=str(SERVER_DIR),
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        PROCS.append((name, proc))
        time.sleep(1)

    # Wait for ports
    for name, port, args in SERVICES:
        for _ in range(10):
            if port_alive(port):
                print(f"  [{name}] Ready on :{port}")
                break
            time.sleep(0.5)
        else:
            print(f"  [{name}] WARNING: did not respond on :{port}")

    save_pids()
    print(f"\n[Minta] All services started. Dashboard: http://localhost:8772")
    print(f"[Minta] PID file: {PID_FILE}")


def cmd_stop():
    """Stop all Minta services."""
    if not PID_FILE.exists():
        print("[Minta] No PID file found -- nothing to stop.")
        return

    try:
        pids = json.loads(PID_FILE.read_text())
    except Exception:
        print("[Minta] Corrupt PID file -- removing.")
        PID_FILE.unlink(missing_ok=True)
        return

    for name, pid in pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  [{name}] stopped (pid={pid})")
        except ProcessLookupError:
            print(f"  [{name}] already gone")
        except Exception as e:
            print(f"  [{name}] error: {e}")

    PID_FILE.unlink(missing_ok=True)
    print("[Minta] All services stopped.")


def cmd_status():
    """Check health of all Minta services."""
    print("[Minta] Service Status:\n")
    all_ok = True
    for name, port, _ in SERVICES:
        alive = port_alive(port)
        status = "RUNNING" if alive else "STOPPED"
        icon = "[OK]" if alive else "[FAIL]"
        if not alive:
            all_ok = False
        print(f"  {icon} {name} (:{port}) -- {status}")
    print()
    if all_ok:
        print("All services healthy. Dashboard: http://localhost:8772")
    else:
        print("Some services are down. Run 'minta start' to restart.")


def cmd_init():
    """First-time setup wizard."""
    print("=" * 50)
    print("  Minta -- Personal Context Layer")
    print("  First-time Setup")
    print("=" * 50)
    print()

    py = find_python()
    print(f"  Python: {py}")
    print()

    deps_ok = True
    for dep in ["chromadb", "sentence_transformers", "sklearn"]:
        try:
            subprocess.run([py, "-c", f"import {dep}"], capture_output=True, timeout=10)
            print(f"  [OK] {dep}")
        except Exception:
            print(f"  [MISS] {dep} -- run: pip install {dep}")
            deps_ok = False

    if not deps_ok:
        print("\n  Install missing dependencies:")
        print(f"    {py} -m pip install chromadb sentence-transformers scikit-learn")
        return

    print()
    print("  Ready! Run 'minta start' to begin.")
    print("  Dashboard: http://localhost:8772")


# ── Connect ──

def _setup_editor(editor_key: str) -> bool:
    """Configure MCP for a single editor. Returns True on success."""
    if editor_key not in EDITORS:
        print(f"[Minta] Unknown editor: {editor_key}")
        print(f"  Supported: {', '.join(EDITORS.keys())}, all")
        return False

    info = EDITORS[editor_key]
    cfg = _read_json(info["config_path"])
    cfg.setdefault(info["mcp_key"], {})["minta"] = info["entry"]
    _write_json(info["config_path"], cfg)

    print(f"  [OK] {info['name']} -> {info['config_path']}")
    return True


def cmd_connect(target: str = "claude"):
    """Configure MCP for one or all AI editors."""
    if not all_services_ready():
        print("[Minta] WARNING: Services are not running.")
        print("  Run 'minta start' first, or use 'minta launch' instead.")
        print()

    mcp_url = "http://localhost:18721/mcp"

    if target == "all":
        print(f"[Minta] Configuring ALL editors for {mcp_url}:\n")
        for key in EDITORS:
            _setup_editor(key)
        print(f"\n[Minta] All editors configured — restart your AI to connect.")
    else:
        print(f"[Minta] Configuring {EDITORS[target]['name']} for {mcp_url}:\n")
        if _setup_editor(target):
            print(f"\n  {EDITORS[target]['launch_hint']}")


# ── Launch ──

def cmd_launch(target: str = "all"):
    """Start services + configure MCP + show launch instructions.

    By default, configures ALL supported editors so the user's AI just works.
    Use --claude / --cursor / --codex / --vscode for a single editor.
    """
    pack_domain = None
    if "--pack" in sys.argv:
        idx = sys.argv.index("--pack")
        if idx + 1 < len(sys.argv):
            pack_domain = sys.argv[idx + 1]

    print("=" * 50)
    print("  Minta Launch")
    print("  AI Memory Engine — https://github.com/xinchen03/minta")
    print("=" * 50)
    print()

    # 1. Ensure services are running
    if all_services_ready():
        print("[1/2] Services already running.\n")
    else:
        print("[1/2] Starting services...\n")
        cmd_start()
        if not all_services_ready():
            print("\n[Minta] ERROR: Failed to start services.")
            print("  Check logs or run 'minta start' manually.")
            return
        print()

    # 2. Configure MCP for target editor(s)
    editors_to_config = list(EDITORS.keys()) if target == "all" else [target]
    configured = []

    print(f"[2/2] Configuring MCP...\n")
    for key in editors_to_config:
        if _setup_editor(key):
            configured.append(key)

    if not configured:
        print("\n[Minta] WARNING: No editors configured.")
        return

    # ── Per-editor restart instructions ──
    RESTART_HINTS = {
        "claude":  "Close terminal → open new terminal → run 'claude'",
        "cursor":  "Restart Cursor (Cmd+Q / Alt+F4 then reopen)",
        "codex":   "Close terminal → open new terminal → run 'codex'",
        "vscode":  "Reload VS Code (Ctrl+Shift+P → 'Developer: Reload Window')",
    }

    print()
    print("-" * 50)
    print("  MCP configured. Now restart your AI:")
    print()
    for key in configured:
        info = EDITORS[key]
        print(f"  {info['name']}:")
        print(f"     {RESTART_HINTS[key]}")
        print()

    print("  ╔══════════════════════════════════════════════╗")
    print("  ║  CRITICAL: MCP loads at editor startup.     ║")
    print("  ║  Always run 'minta start' BEFORE opening    ║")
    print("  ║  your AI editor — or use this 'minta launch'║")
    print("  ║  which does both for you.                   ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  Dashboard: http://localhost:8772")
    print("  MCP:       http://localhost:18721/mcp")
    print()
    print("  Quick start next time:")
    if sys.platform == "win32":
        print("    Double-click Start-Minta.vbs, then open your AI.")
    else:
        print("    ./Start-Minta.sh, then open your AI.")
    print("-" * 50)


# ── Main ──

def _print_help():
    print("Minta CLI -- Personal Context Layer")
    print()
    print("Commands:")
    print("  minta init                  First-time setup")
    print("  minta start                 Start all services")
    print("  minta stop                  Stop all services")
    print("  minta status                Check service health")
    print()
    print("  minta connect               Configure Claude Code MCP (default)")
    print("  minta connect --cursor      Configure Cursor IDE MCP")
    print("  minta connect --codex       Configure Codex CLI MCP")
    print("  minta connect --vscode      Configure VS Code / Copilot MCP")
    print("  minta connect --all         Configure all supported editors")
    print()
    print("  minta launch                Start + configure ALL AI editors (recommended)")
    print("  minta launch --claude       Start + configure Claude Code only")
    print("  minta launch --cursor       Start + configure Cursor IDE only")
    print("  minta launch --codex        Start + configure Codex CLI only")
    print("  minta launch --vscode       Start + configure VS Code only")
    print()
    print("Pro tip: run 'minta launch' once → restart your AI → connected forever.")
    print("         On reboot: double-click Start-Minta, then open your AI.")
    print()
    print("Dashboard: http://localhost:8772")


def _parse_target(default: str = "claude") -> str:
    """Parse --editor flag from command line."""
    editor_flags = {"--claude": "claude", "--cursor": "cursor",
                    "--codex": "codex", "--vscode": "vscode", "--all": "all"}
    for arg in sys.argv[2:]:
        if arg in editor_flags:
            return editor_flags[arg]
    return default


def main():
    if len(sys.argv) < 2:
        _print_help()
        return

    cmd = sys.argv[1]

    if cmd == "init":
        cmd_init()
    elif cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "status":
        cmd_status()
    elif cmd == "connect":
        target = _parse_target()
        cmd_connect(target)
    elif cmd == "launch":
        target = _parse_target(default="all")
        cmd_launch(target)
    elif cmd in ("--help", "-h", "help"):
        _print_help()
    else:
        print(f"Unknown command: {cmd}")
        _print_help()


if __name__ == "__main__":
    main()
