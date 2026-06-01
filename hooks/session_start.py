#!/usr/bin/env python
"""Minta SessionStart Hook — double-insurance MCP connection.

Layer 1 (auto): detect if Minta is running, inject Context Pack if ready
Layer 2 (guided): if not running, tell Claude to ask the user

Install: copy hooks/ to ~/.claude/hooks/  (or your editor's hooks directory)
"""

import json
import os
import socket
import sys
import time
import urllib.request
from pathlib import Path

API_URL = "http://127.0.0.1:8772"
MCP_URL = "http://127.0.0.1:18721/mcp"
API_KEY = os.environ.get("MINTA_API_KEY", "")

# Editor MCP configs to check
EDITOR_CONFIGS = {
    "claude": Path.home() / ".claude" / "settings.json",
    "cursor": Path.home() / ".cursor" / "mcp.json",
    "codex":  Path.home() / ".codex" / "mcp.json",
    "vscode": Path.home() / ".vscode" / "mcp.json",
}

MCP_KEY = "mcpServers"


def port_alive(port, timeout=2):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        r = s.connect_ex(("127.0.0.1", port)) == 0
        s.close()
        return r
    except Exception:
        return False


def check_mcp_configured():
    """Check if at least one editor has Minta MCP configured."""
    for name, path in EDITOR_CONFIGS.items():
        if path.exists():
            try:
                cfg = json.loads(path.read_text())
                if cfg.get(MCP_KEY, {}).get("minta"):
                    return True, name
            except Exception:
                pass
    return False, None


def check_mcp_handshake():
    """Full MCP handshake: initialize + tools/list."""
    try:
        body = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "minta-hook", "version": "1.0.0"}}
        }).encode()
        req = urllib.request.Request(MCP_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=3)
        if "result" not in json.loads(r.read()):
            return False, 0

        body2 = json.dumps({"jsonrpc": "2.0", "id": 2,
                           "method": "tools/list", "params": {}}).encode()
        req2 = urllib.request.Request(MCP_URL, data=body2,
                                      headers={"Content-Type": "application/json"})
        r2 = urllib.request.urlopen(req2, timeout=3)
        tools = json.loads(r2.read()).get("result", {}).get("tools", [])
        return True, len(tools)
    except Exception:
        return False, 0


def fetch_context_pack():
    if not API_KEY:
        return None
    try:
        req = urllib.request.Request(
            f"{API_URL}/api/slots/pack/generate?scene=auto",
            headers={"X-API-Key": API_KEY},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("content", "")
    except Exception:
        return None


def main():
    api_ok = port_alive(8772)
    mcp_ok = port_alive(18721)
    mcp_cfg_ok, cfg_editor = check_mcp_configured()
    handshake_ok, tool_count = check_mcp_handshake() if mcp_ok else (False, 0)

    # === CASE 1: Everything is ready ===
    if api_ok and mcp_ok and handshake_ok and mcp_cfg_ok:
        pack = fetch_context_pack()
        if pack:
            sys.stdout.buffer.write(pack.encode("utf-8"))
            sys.stdout.buffer.flush()
        return

    # === CASE 2: MCP config exists but services are down (user forgot to start) ===
    if mcp_cfg_ok and not api_ok:
        msg = (
            "\n[Minta Hook] Minta is NOT running.\n"
            "Tell the user:\n"
            '  "Minta services are stopped. Run `python minta_cli.py launch` and restart Claude."\n'
            "Then STOP — do NOT proceed with the conversation until Minta is running.\n"
        )
        sys.stdout.buffer.write(msg.encode("utf-8"))
        sys.stdout.buffer.flush()
        return

    # === CASE 3: Services running but MCP not configured (first-time user) ===
    if (api_ok or mcp_ok) and not mcp_cfg_ok:
        msg = (
            "\n[Minta Hook] Minta is running but MCP is not configured for any AI editor.\n"
            "Tell the user:\n"
            '  "Minta is running but your AI editor is not connected yet. '
            'Run `python minta_cli.py launch` and restart Claude."\n'
        )
        sys.stdout.buffer.write(msg.encode("utf-8"))
        sys.stdout.buffer.flush()
        return

    # === CASE 4: MCP configured + services running but handshake failed ===
    if api_ok and mcp_ok and mcp_cfg_ok and not handshake_ok:
        msg = (
            "\n[Minta Hook] MCP handshake failed — Minta services may still be starting.\n"
            "Wait 5 seconds and restart Claude. If this persists, run `python minta_cli.py verify`.\n"
        )
        sys.stdout.buffer.write(msg.encode("utf-8"))
        sys.stdout.buffer.flush()
        return

    # === CASE 5: Nothing is set up (fresh install) ===
    msg = (
        "\n[Minta Hook] Minta not detected. This is likely a first-time setup.\n"
        "Ask the user:\n"
        '  "Do you want to use Minta (AI memory engine)? It gives me persistent memory '
        'of your preferences, project context, and lessons learned."\n'
        "If the user says YES:\n"
        '  1. Tell them: "Open a terminal and run: python minta_cli.py launch"\n'
        '  2. Tell them: "Then restart Claude (close and reopen)."\n'
        "If the user says NO:\n"
        "  Proceed with the conversation normally. Minta can be set up later.\n"
        "\nIMPORTANT: Do NOT try to read Minta files or config. Just ask and follow the user's choice.\n"
    )
    sys.stdout.buffer.write(msg.encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
