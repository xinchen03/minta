"""Regression tests for the public server shell."""
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from main import MINTA_ENV, app
from routers.auth import get_current_user


class _User:
    id = 7


def teardown_function():
    app.dependency_overrides.clear()


def test_unknown_api_path_never_falls_back_to_spa():
    response = TestClient(app).get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not found"}


def test_production_seed_demo_is_disabled():
    if MINTA_ENV not in ("production", "prod"):
        return
    app.dependency_overrides[get_current_user] = lambda: _User()
    response = TestClient(app).post("/api/admin/seed-demo")
    assert response.status_code == 404

