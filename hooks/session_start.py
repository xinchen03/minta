#!/usr/bin/env python
"""SessionStart hook — auto-start all Minta services, inject Context Pack + Expert System.

On each session start:
  1. Ensure API server is running (port 8772)
  2. Check if expert rules exist; if not, compile 3 default CPGs
  3. Register Meta experts + build SME graph
  4. Fetch Context Pack with expert directory injected into Claude's context

Silent fallback if API is unreachable.
"""
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

API_KEY = os.environ.get("MINTA_API_KEY", "")
API_URL = os.environ.get("MINTA_API_URL", "http://127.0.0.1:8772")
ROOT = Path(__file__).resolve().parent.parent  # memory/
SERVER_DIR = ROOT / "server"


def _port_alive(port):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        r = sock.connect_ex(("127.0.0.1", port)) == 0
        sock.close()
        return r
    except Exception:
        return False


def _start_process(cmd, cwd, wait_port=None, label=""):
    try:
        subprocess.Popen(
            cmd,
            cwd=str(cwd),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if wait_port:
            for _ in range(20):
                time.sleep(0.5)
                if _port_alive(wait_port):
                    sys.stderr.write(f"[Minta] {label} auto-started\n")
                    return True
            sys.stderr.write(f"[Minta] WARNING: {label} start timed out\n")
            return False
        return True
    except Exception as e:
        sys.stderr.write(f"[Minta] ERROR starting {label}: {e}\n")
        return False


def _api_post(path, body, timeout=15):
    """POST to Minta API with API key auth. Returns parsed response or None."""
    if not API_KEY:
        return None
    try:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{API_URL}{path}",
            data=data,
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception as e:
        sys.stderr.write(f"[Minta] API POST {path} failed: {e}\n")
        return None


def _api_get(path, timeout=10):
    """GET from Minta API. Returns parsed response or None."""
    if not API_KEY:
        return None
    try:
        req = urllib.request.Request(
            f"{API_URL}{path}",
            headers={"X-API-Key": API_KEY},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


# ── Default CPGs (Ottawa/Canadian rules) ──
DEFAULT_CPGS = [
    ("ankle_injury", "Ottawa Ankle Rules (Stiell 1992 JAMA)",
     """Request an x-ray for a patient with traumatic ankle pain if they have any of the following:
(A) point tenderness at posterior edge or tip lateral malleolus
(B) point tenderness at posterior edge or tip medial malleolus
inability to weight bear (four steps) immediately after the injury and in the emergency department.
Request an x-ray for a patient with traumatic midfoot pain if they have any of the following:
(C) point tenderness at the base of the fifth metatarsal
(D) point tenderness at the navicular
inability to weight bear, i.e. inability to take four steps immediately after the injury and in the emergency department."""),
    ("knee_injury", "Ottawa Knee Rules (Stiell 1996 JAMA)",
     """Request a knee x-ray for a patient with acute knee injury if they have any of the following:
(A) Age 55 years or older
(B) Isolated tenderness of the patella (no bony tenderness of the knee other than the patella)
(C) Tenderness at the head of the fibula
(D) Inability to flex the knee to 90 degrees
(E) Inability to bear weight (four steps) both immediately after the injury and in the emergency department, regardless of limping."""),
    ("cervical_spine_injury", "Canadian C-Spine Rule (Stiell 2001 JAMA)",
     """The Canadian C-Spine Rule for alert (GCS=15) and stable trauma patients:
Step 1 -- High Risk Factors (any YES -> imaging required):
(A) Age 65 years or older
(B) Dangerous mechanism of injury: fall from elevation >3 feet, axial load to head, high-speed motor vehicle collision, bicycle collision
(C) Paresthesias in extremities
Step 2 -- Low Risk Factors (if NO to all -> imaging required):
(A) Simple rear-end motor vehicle collision
(B) Sitting position in the emergency department
(C) Ambulatory at any time since the injury
(D) Delayed onset of neck pain (not immediate)
(E) Absence of midline cervical-spine tenderness
Step 3 -- Neck Rotation (if any low risk factor present): If unable to actively rotate neck 45 degrees -> imaging required. If able -> rule cleared, no imaging needed."""),
]


def ensure_experts():
    """Auto-compile default CPGs if expert rules are missing or fewer than 3 domains."""
    resp = _api_get("/api/expert/productions?limit=1")
    if resp is None:
        return

    count = resp.get("count", 0)
    if count >= 10:
        # Already has rules — no need to re-compile
        return

    sys.stderr.write(f"[Minta] Expert rules low ({count}), compiling defaults...\n")
    for domain, source, cpg_text in DEFAULT_CPGS:
        # Compile
        result = _api_post("/api/expert/productions/compile", {
            "cpg_text": cpg_text, "domain": domain, "source": source,
        })
        n = result.get("count", 0) if result else 0
        sys.stderr.write(f"  {domain}: {n} rules\n")

        # Register expert
        _api_post("/api/expert/meta/experts/register", {
            "domain": domain, "title": source, "description": source,
            "cpg_source": source, "source_quality": "clinical_practice_guideline",
        })

    # Run SME analogies
    for src_domain, _, _ in DEFAULT_CPGS:
        _api_post("/api/expert/meta/analogies", {
            "source_domain": src_domain,
            "target_domains": [d for d, _, _ in DEFAULT_CPGS if d != src_domain],
        })

    sys.stderr.write(f"[Minta] Expert system initialized: {len(DEFAULT_CPGS)} domains\n")


def ensure_all():
    if not _port_alive(8772):
        _start_process(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8772"],
            cwd=SERVER_DIR, wait_port=8772, label="API server (8772)"
        )

    # Autopilot API server (port 18730) — new API with autopilot routes
    if not _port_alive(18730):
        _start_process(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "18730"],
            cwd=SERVER_DIR, wait_port=18730, label="Autopilot API (18730)"
        )

    # MCP HTTP server (port 18721) — for Claude Code tool access
    if not _port_alive(18721):
        _start_process(
            [sys.executable, "-m", "uvicorn", "minta_mcp_http:create_mcp_app", "--host", "127.0.0.1", "--port", "18721", "--factory"],
            cwd=SERVER_DIR, wait_port=18721, label="MCP HTTP (18721)"
        )


def inject_expert_context():
    """Build a lightweight expert directory snippet (~100 chars) for Context Pack."""
    resp = _api_get("/api/expert/meta/experts")
    if not resp or not resp.get("ok"):
        return ""
    experts = resp.get("data", [])
    if not experts:
        return ""
    lines = []
    for exp in experts:
        d = exp.get("domain", "")
        t = exp.get("title", d)
        rc = exp.get("rule_count", 0)
        lines.append(f"{d} ({t}, {rc} rules)")
    return "## Expert Domains: " + "; ".join(lines)


def fetch_pack():
    if not API_KEY:
        return None
    try:
        req = urllib.request.Request(
            f"{API_URL}/api/slots/pack/generate?scene=auto",
            headers={"X-API-Key": API_KEY},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("content", "")
    except Exception:
        return None


def main():
    ensure_all()

    # Upload buffered observations (counter-examples, etc.)
    try:
        from buffer import flush
        uploaded = flush(API_KEY, API_URL)
        if uploaded > 0:
            sys.stderr.write(f"[Minta] Uploaded {uploaded} buffered observations\n")
    except Exception:
        pass

    # Auto-initialize expert system if needed
    ensure_experts()

    # Fetch Context Pack with expert context
    pack = fetch_pack()
    if not pack:
        return

    pack = pack[:1500]
    sys.stdout.buffer.write(pack.encode("utf-8"))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
