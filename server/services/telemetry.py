"""Optional anonymous usage heartbeat (PostHog capture).

Consent model: default-ON with clean opt-out. Disable via `MINTA_TELEMETRY=0`
in .env, or by writing 0 to runtime/.telemetry_consent. The consent file is
authoritative — an explicit opt-out there wins over an env opt-in.
`MINTA_TELEMETRY_POSTHOG_KEY` holds the public PostHog project key (public by
design — event-send only, never data read).

Privacy invariant: ONLY metadata is sent — install id / version / OS / event
name. NEVER memory content, queries, messages or usage text. All failures are
silent (log-only): metrics must never affect the engine.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import threading
import time
import uuid
from pathlib import Path

logger = logging.getLogger("minta.telemetry")

# Repo-root runtime dir (same place the install-id file goes on the user's box).
_RUNTIME = Path(__file__).resolve().parent.parent.parent / "runtime"
_INSTALL_ID_FILE = _RUNTIME / ".minta_install_id"

# US cloud project (default). Override for EU runs via MINTA_TELEMETRY_HOST.
_CAPTURE_URL = os.environ.get(
    "MINTA_TELEMETRY_HOST", "https://us.i.posthog.com/capture")


_CONSENT_FILE = _RUNTIME / ".telemetry_consent"


def consent_set() -> bool | None:
    """File-based consent: None = not asked; True/False = user's choice."""
    try:
        val = _CONSENT_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return val == "1"


def set_consent(enabled: bool) -> None:
    _CONSENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CONSENT_FILE.write_text("1" if enabled else "0", encoding="utf-8")


def _enabled() -> bool:
    """File-based consent is authoritative; env opt-out honored; DEFAULT ON."""
    fc = consent_set()
    if fc is not None:
        return fc
    env = os.environ.get("MINTA_TELEMETRY", "").strip().lower()
    if env:
        return env not in ("0", "false", "off", "no")
    return True


# Public capture key (event-send only, public by design). Fallback so the
# default-ON heartbeat actually ships on fresh installs without .env setup.
_DEFAULT_KEY = "phc_AY3tBursmTQMZLkGn9QKz75o6feyJCKuTWnruh9dLB5q"


def _key() -> str:
    return os.environ.get("MINTA_TELEMETRY_POSTHOG_KEY", _DEFAULT_KEY).strip()


def install_id() -> str:
    """Stable per-machine id (uuid hex, persisted in runtime/)."""
    override = os.environ.get("MINTA_TELEMETRY_INSTALL_ID", "").strip()
    if override:
        return override
    if not _INSTALL_ID_FILE.exists():
        _INSTALL_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        _INSTALL_ID_FILE.write_text(uuid.uuid4().hex, encoding="utf-8")
    return _INSTALL_ID_FILE.read_text(encoding="utf-8").strip()


def _version() -> str:
    try:
        root = _RUNTIME.parent
        ver = root / "VERSION"
        if ver.exists():
            return ver.read_text(encoding="utf-8").strip()
        pkg = root / "package.json"
        if pkg.exists():
            return json.loads(pkg.read_text(encoding="utf-8")).get("version", "dev")
    except Exception:
        pass
    return "dev"


def _post(event: str, properties: dict | None = None) -> None:
    if not (_enabled() and _key()):
        return
    try:
        import requests
        payload = {
            "api_key": _key(),
            "event": event,
            "distinct_id": install_id(),
            "properties": {
                "app": "minta",
                "version": _version(),
                "os": platform.system(),
            } | (properties or {}),
        }
        r = requests.post(_CAPTURE_URL, json=payload, timeout=5)
        if r.status_code >= 300:
            logger.warning("telemetry post → %s %s", r.status_code, r.text[:120])
    except Exception:
        logger.debug("telemetry skipped (silent)", exc_info=True)


def heartbeat(properties: dict | None = None) -> None:
    _post("heartbeat", properties)


def start_daily_loop() -> None:
    """Daemon thread: one heartbeat at engine start, then every 24h."""
    def _loop():
        heartbeat({"source": "engine_start"})
        while True:
            time.sleep(24 * 3600)
            heartbeat({"source": "daily"})
    threading.Thread(target=_loop, daemon=True, name="minta-telemetry").start()
