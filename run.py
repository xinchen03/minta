#!/usr/bin/env python
"""Minta — one-click launcher for all three services.

Starts:
  - 8772  Data API + Frontend
  - 18730 Autopilot API
  - 18721 MCP HTTP Server

Press Ctrl+C to stop all services.
"""
import os
import sys
import time
import socket
import signal
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER_DIR = ROOT / "server"
PROCS = []


def port_alive(port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("127.0.0.1", port)) == 0
        sock.close()
        return result
    except Exception:
        return False


def start_service(name: str, port: int, args: list):
    if port_alive(port):
        print(f"  [{name}] port {port} already in use — skipping")
        return

    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn"] + args + ["--host", "127.0.0.1", "--port", str(port)],
        cwd=str(SERVER_DIR),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    PROCS.append((name, proc))

    # Wait for port
    for _ in range(15):
        time.sleep(0.5)
        if port_alive(port):
            print(f"  [{name}] started on :{port}")
            return
    print(f"  [{name}] WARNING: did not respond on :{port}")


def cleanup(sig=None, frame=None):
    print("\n[Minta] Shutting down...")
    for name, proc in PROCS:
        try:
            proc.terminate()
        except Exception:
            pass
    for name, proc in PROCS:
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
    print("[Minta] All services stopped.")
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    print("=" * 50)
    print("  Minta — Personal Context Layer")
    print("  http://localhost:8772")
    print("=" * 50)

    start_service("Data API", 8772, ["main:app"])
    start_service("Autopilot", 18730, ["main:app"])
    start_service("MCP HTTP", 18721, ["minta_mcp_http:create_mcp_app", "--factory"])

    print("\n[Minta] All services ready. Press Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
