"""Container entrypoint for the public Minta service.

Creates a persistent random JWT secret on first boot when the operator did
not provide one. The value stays inside the /data volume and is never printed.
"""
import os
import secrets
import sys
from pathlib import Path


def _ensure_persistent_secret(env_name: str, file_name: str,
                              prefix: str = "", nbytes: int = 48) -> None:
    if os.environ.get(env_name):
        return

    data_dir = Path(os.environ.get("MINTA_DATA_DIR", "/data"))
    data_dir.mkdir(parents=True, exist_ok=True)
    secret_file = data_dir / file_name

    if secret_file.exists():
        value = secret_file.read_text(encoding="utf-8").strip()
    else:
        value = prefix + secrets.token_urlsafe(nbytes)
        secret_file.write_text(value, encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except OSError:
            pass

    if not value:
        raise RuntimeError("Persistent JWT secret is empty")
    os.environ[env_name] = value


def _ensure_jwt_secret() -> None:
    _ensure_persistent_secret("MINTA_JWT_SECRET", ".minta_jwt_secret")


if __name__ == "__main__":
    _ensure_jwt_secret()
    os.execv(sys.executable, [sys.executable, "run.py"])
