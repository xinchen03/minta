"""Tests for zero-config container secret initialization."""
import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("docker_entrypoint", ROOT / "docker_entrypoint.py")
docker_entrypoint = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(docker_entrypoint)


def test_generates_and_reuses_persistent_jwt_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("MINTA_JWT_SECRET", raising=False)
    monkeypatch.setenv("MINTA_DATA_DIR", str(tmp_path))

    docker_entrypoint._ensure_jwt_secret()
    first = os.environ["MINTA_JWT_SECRET"]
    assert len(first) >= 48
    assert (tmp_path / ".minta_jwt_secret").read_text(encoding="utf-8") == first

    monkeypatch.delenv("MINTA_JWT_SECRET", raising=False)
    docker_entrypoint._ensure_jwt_secret()
    assert os.environ["MINTA_JWT_SECRET"] == first
