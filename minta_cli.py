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
import signal
import socket
import urllib.request
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

# --- Editor MCP configs ---
# stdio mode (Claude, Cursor, Codex): editor spawns Minta process on demand
# HTTP mode (VS Code): requires Minta server running on localhost:18721
_MCP_STDIO = {
    "command": sys.executable,
    "args": [str(SERVER_DIR / "minta_mcp.py")],
}
_MCP_HTTP = {"url": "http://localhost:18721/mcp"}

EDITORS = {
    "claude": {
        "name": "Claude Code",
        "config_path": Path.home() / ".claude" / "settings.json",
        "mcp_key": "mcpServers",
        "entry": _MCP_STDIO,
        "launch_hint": "Run 'claude' in your terminal. Minta auto-starts on demand.",
    },
    "cursor": {
        "name": "Cursor IDE",
        "config_path": Path.home() / ".cursor" / "mcp.json",
        "mcp_key": "mcpServers",
        "entry": _MCP_STDIO,
        "launch_hint": "Open Cursor. Minta auto-starts on demand via MCP panel.",
    },
    "codex": {
        "name": "Codex CLI",
        "config_path": Path.home() / ".codex" / "mcp.json",
        "mcp_key": "mcpServers",
        "entry": _MCP_STDIO,
        "launch_hint": "Run 'codex' in your terminal. Minta auto-starts on demand.",
    },
    "vscode": {
        "name": "VS Code / Copilot",
        "config_path": Path.home() / ".vscode" / "mcp.json",
        "mcp_key": "mcpServers",
        "entry": _MCP_HTTP,
        "launch_hint": (
            "HTTP mode — run `python minta_cli.py start` first to start Minta services.\n"
            "  Then open VS Code and MCP tools will be available."
        ),
    },
}


# --- Helpers ---

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


# --- Commands ---

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
        logfile = ROOT / "logs" / f"{name.replace(' ', '_').lower()}.log"
        logfile.parent.mkdir(exist_ok=True)
        fh = open(str(logfile), "w")
        proc = subprocess.Popen(
            [python, "-m", "uvicorn"] + args + ["--host", "127.0.0.1", "--port", str(port)],
            cwd=str(SERVER_DIR),
            creationflags=flags,
            stdout=fh,
            stderr=fh,
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
            logfile = ROOT / "logs" / f"{name.replace(' ', '_').lower()}.log"
            print(f"  [{name}] FAILED to start on :{port}")
            if logfile.exists():
                tail = logfile.read_text(errors="replace")[-500:]
                print(f"    Last 500 chars of log:\n{tail}")

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


def cmd_verify():
    """End-to-end health check: services, API, MCP, login."""
    print("[Minta] Running full verification...\n")

    ok = 0
    total = 0

    # 1. Check ports
    print("--- Services ---")
    for name, port, _ in SERVICES:
        total += 1
        alive = port_alive(port)
        if alive:
            print(f"  [OK] {name} (:{port})")
            ok += 1
        else:
            print(f"  [FAIL] {name} (:{port}) — NOT RUNNING")
    print()

    # 2. Check API endpoint
    print("--- API ---")
    for label, url in [("Ping", "http://localhost:8772/ping"),
                       ("API Docs", "http://localhost:8772/docs")]:
        total += 1
        try:
            r = urllib.request.urlopen(url, timeout=5)
            if r.status == 200:
                print(f"  [OK] {label} ->{url}")
                ok += 1
            else:
                print(f"  [FAIL] {label} ->{url} (HTTP {r.status})")
        except Exception as e:
            print(f"  [FAIL] {label} ->{url} ({e})")
    print()

    # 3. Check MCP endpoint
    print("--- MCP ---")
    total += 1
    try:
        body = json.dumps({"jsonrpc": "2.0", "id": 1,
                          "method": "tools/list", "params": {}}).encode()
        req = urllib.request.Request("http://localhost:18721/mcp",
                                     data=body,
                                     headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=5)
        resp = json.loads(r.read())
        tools = resp.get("result", {}).get("tools", [])
        tool_names = [t["name"] for t in tools]
        if tool_names:
            print(f"  [OK] MCP responding — {len(tools)} tools available")
            print(f"      Core: {', '.join(t for t in tool_names if not t.startswith('minta_expert_'))}")
            ok += 1
        else:
            print(f"  [FAIL] MCP responding but 0 tools — check config")
    except Exception as e:
        print(f"  [FAIL] MCP not reachable ({e})")
    print()

    # 4. Check MCP configs
    print("--- Editor Configs ---")
    for key, info in EDITORS.items():
        total += 1
        cfg = _read_json(info["config_path"])
        minta_entry = cfg.get(info["mcp_key"], {}).get("minta")
        if minta_entry:
            print(f"  [OK] {info['name']} ->{info['config_path']}")
            ok += 1
        else:
            print(f"  [FAIL] {info['name']} — no Minta entry in {info['config_path']}")
    print()

    print(f"--- Result: {ok}/{total} checks passed ---")
    if ok == total:
        print("  Minta is fully operational.")
        print("  Open your AI editor and start using Minta tools.")
    else:
        missing = total - ok
        print(f"  {missing} check(s) failed. Run 'minta launch' to fix.")

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


# --- Connect ---

def _register_hook_entry(cfg: dict, hook_event: str, script_name: str, python: str, hooks_dst: Path) -> bool:
    """Register a hook in settings.json if not already present. Returns True if added."""
    hook_script = str(hooks_dst / script_name)
    if hook_event not in cfg.get("hooks", {}):
        cfg.setdefault("hooks", {})[hook_event] = []
    already = any(
        h.get("command", "").endswith(script_name)
        for entry in cfg["hooks"][hook_event]
        for h in (entry.get("hooks", []) if isinstance(entry, dict) else [])
    )
    if not already:
        cfg["hooks"][hook_event].append({
            "hooks": [{
                "type": "command",
                "command": f"{python} {hook_script}",
            }]
        })
        return True
    return False


def _install_hooks():
    """Copy hooks to ~/.claude/hooks/ AND register all Minta hooks in settings.json.

    Registered hooks:
      - SessionStart:       check Minta connection + inject Context Pack
      - PostToolUse:        detect correction signals → counter-example inbox
      - PostToolUseFailure: auto-mark failed tool calls as counter-examples
      - Stop:               trigger slot reflection at session end
    """
    hooks_src = ROOT / "hooks"
    hooks_dst = Path.home() / ".claude" / "hooks"
    if not hooks_src.is_dir():
        return

    hooks_dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    for f in hooks_src.iterdir():
        if f.suffix == ".py":
            dst = hooks_dst / f.name
            dst.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            copied += 1
    if copied:
        print(f"  [OK] {copied} hooks installed -> {hooks_dst}")

    python = find_python()
    claude_config = Path.home() / ".claude" / "settings.json"
    cfg = _read_json(claude_config)

    # Register all 4 hooks (idempotent — skips if already present)
    registered = []
    if _register_hook_entry(cfg, "SessionStart", "session_start.py", python, hooks_dst):
        registered.append("SessionStart")
    if _register_hook_entry(cfg, "PostToolUse", "post_tool_use.py", python, hooks_dst):
        registered.append("PostToolUse")
    if _register_hook_entry(cfg, "PostToolUseFailure", "post_tool_failure.py", python, hooks_dst):
        registered.append("PostToolUseFailure")
    if _register_hook_entry(cfg, "Stop", "stop_reflect.py", python, hooks_dst):
        registered.append("Stop")

    if registered:
        _write_json(claude_config, cfg)
        print(f"  [OK] Hooks registered: {', '.join(registered)}")


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

    # Claude Code: also write .mcp.json (newer Claude Code prefers this over settings.json)
    if editor_key == "claude" or editor_key == "all":
        mcp_json = _read_json(Path.home() / ".mcp.json")
        mcp_json.setdefault("mcpServers", {})["minta"] = info["entry"]
        _write_json(Path.home() / ".mcp.json", mcp_json)
        print(f"  [OK] Claude Code -> {Path.home() / '.mcp.json'}")

        _install_hooks()

    return True


def cmd_connect(target: str = "claude"):
    """Configure MCP for one or all AI editors."""
    if target == "all":
        print("[Minta] Configuring ALL editors:\n")
        for key in EDITORS:
            _setup_editor(key)
        print(f"\n[Minta] All editors configured.")
        print("  stdio editors (Claude, Cursor, Codex): auto-start on demand.")
        print("  HTTP editor (VS Code): run 'minta start' first.")
        print("  Restart your AI editor to pick up the new config.")
    else:
        info = EDITORS[target]
        mode = "stdio (auto-start)" if "command" in info["entry"] else "HTTP"
        print(f"[Minta] Configuring {info['name']} ({mode}):\n")
        if _setup_editor(target):
            print(f"\n  {EDITORS[target]['launch_hint']}")


# --- Launch ---

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

    # --- 3. Verify MCP handshake (critical: Claude silently drops tools if init fails) ---
    print()
    print("  Verifying MCP handshake...", end=" ", flush=True)
    mcp_ok = False
    for attempt in range(10):
        try:
            # Full MCP init handshake: initialize -> list tools
            body = json.dumps({"jsonrpc": "2.0", "id": 1,
                              "method": "initialize",
                              "params": {"protocolVersion": "2024-11-05",
                                         "capabilities": {},
                                         "clientInfo": {"name": "minta-verify", "version": "1.0.0"}}}).encode()
            req = urllib.request.Request("http://localhost:18721/mcp",
                                         data=body,
                                         headers={"Content-Type": "application/json"})
            r = urllib.request.urlopen(req, timeout=3)
            init_resp = json.loads(r.read())
            if "result" in init_resp:
                body2 = json.dumps({"jsonrpc": "2.0", "id": 2,
                                   "method": "tools/list", "params": {}}).encode()
                req2 = urllib.request.Request("http://localhost:18721/mcp",
                                              data=body2,
                                              headers={"Content-Type": "application/json"})
                r2 = urllib.request.urlopen(req2, timeout=3)
                tools_resp = json.loads(r2.read())
                n = len(tools_resp.get("result", {}).get("tools", []))
                print(f"{n} tools confirmed.")
                mcp_ok = True
                break
        except Exception:
            time.sleep(1)
    if not mcp_ok:
        print("FAILED!")
        print()
        print("  WARNING: MCP handshake failed. Your AI may not see Minta tools.")
        print("  This usually means port 18721 isn't ready yet.")
        print("  Wait a few seconds and restart your AI.")
    else:
        print("  MCP handshake OK - your AI will see all tools on restart.")

    # --- Per-editor restart instructions ---
    RESTART_HINTS = {
        "claude":  "Close terminal ->open new terminal ->run 'claude'",
        "cursor":  "Restart Cursor (Cmd+Q / Alt+F4 then reopen)",
        "codex":   "Close terminal ->open new terminal ->run 'codex'",
        "vscode":  "Reload VS Code (Ctrl+Shift+P ->'Developer: Reload Window')",
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

    print("  +--------------------------------------------------+")
    print("  |  CRITICAL: MCP loads at editor startup.         |")
    print("  |  Always run 'minta start' BEFORE opening your   |")
    print("  |  AI editor — or use 'minta launch' which does   |")
    print("  |  both for you.                                  |")
    print("  +--------------------------------------------------+")
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


# --- Main ---

def _print_help():
    print("Minta CLI -- Personal Context Layer")
    print()
    print("Usage: python minta_cli.py <command> [options]")
    print()
    print("Commands:")
    print("  python minta_cli.py init                  First-time setup")
    print("  python minta_cli.py start                 Start all services")
    print("  python minta_cli.py stop                  Stop all services")
    print("  python minta_cli.py status                Check service health")
    print("  python minta_cli.py verify                Full end-to-end check (services + MCP + editors)")
    print()
    print("  python minta_cli.py connect               Configure Claude Code MCP (default)")
    print("  python minta_cli.py connect --cursor      Configure Cursor IDE MCP")
    print("  python minta_cli.py connect --codex       Configure Codex CLI MCP")
    print("  python minta_cli.py connect --vscode      Configure VS Code / Copilot MCP")
    print("  python minta_cli.py connect --all         Configure all supported editors")
    print()
    print("  python minta_cli.py launch                Start + configure ALL AI editors (recommended)")
    print("  python minta_cli.py launch --claude       Start + configure Claude Code only")
    print("  python minta_cli.py launch --cursor       Start + configure Cursor IDE only")
    print("  python minta_cli.py launch --codex        Start + configure Codex CLI only")
    print("  python minta_cli.py launch --vscode       Start + configure VS Code only")
    print()
    print("Pro tip: run 'python minta_cli.py launch' once -> restart your AI -> connected forever.")
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
    elif cmd == "verify":
        cmd_verify()
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
