"""MySQL connection config for Minta FastAPI server.

All secrets must be set via environment variables. No hardcoded fallbacks for production.
See .env.example in the project root.
"""
import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

ROOT = Path(__file__).resolve().parent.parent  # minta-public/


def _load_or_generate(file_name: str, prefix: str = "", nbytes: int = 32) -> str:
    """Read secret from file, or generate and persist on first run."""
    secret_file = ROOT / file_name
    if secret_file.exists():
        return secret_file.read_text().strip()
    import secrets
    value = prefix + secrets.token_urlsafe(nbytes)
    secret_file.write_text(value)
    secret_file.chmod(0o600)  # owner-only
    print(f"[Minta] Generated {file_name} (persisted)", file=sys.stderr)
    return value


# ── Database ──
# Default: SQLite for zero-config local dev. Set MINTA_DATABASE_URL for MySQL/Postgres.
_DEFAULT_DB = "sqlite:///./minta.db"
DATABASE_URL = os.environ.get("MINTA_DATABASE_URL", _DEFAULT_DB)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, pool_size=1)
else:
    engine = create_engine(DATABASE_URL, pool_size=5, pool_recycle=3600)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# ── Email (SMTP) ──
SMTP_HOST = os.environ.get("MINTA_SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.environ.get("MINTA_SMTP_PORT", "465"))
SMTP_USER = os.environ.get("MINTA_SMTP_USER", "")
SMTP_PASS = os.environ.get("MINTA_SMTP_PASS", "")
SMTP_CONFIGURED = bool(SMTP_USER and SMTP_PASS)
if not SMTP_CONFIGURED:
    import warnings
    warnings.warn("SMTP not configured — email verification auto-passes. Set MINTA_SMTP_USER + MINTA_SMTP_PASS for production.")

# ── Feature flags ──
MINTA_EXPERT_ENABLED = os.environ.get("MINTA_EXPERT_ENABLED", "true").lower() in ("true", "1", "yes")
MINTA_AUTOPILOT_ENABLED = os.environ.get("MINTA_AUTOPILOT_ENABLED", "true").lower() in ("true", "1", "yes")

# ── API Key — env var or auto-generated + persisted ──
MINTA_API_KEY = os.environ.get("MINTA_API_KEY", "")
if not MINTA_API_KEY:
    MINTA_API_KEY = _load_or_generate(".minta_api_key", prefix="minta_", nbytes=32)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
