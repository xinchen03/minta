"""Minta FastAPI server — main entry point."""
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, Request, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from routers import inbox, context_objects, upload, skills, auth, api_keys, verification, comments, admin, user_data, slots, session as session_router
from routers.autopilot import router as autopilot_router
from routers.experiment import router as experiment_router
from routers.lifecycle import router as lifecycle_router
from routers.debt import router as debt_router
import models.bandit_state
import models.context_retrieval_log
import models.graph_edge
import models.task_reward_log
import models.slot
import models.archived_item
import models.inference_log as _inference_log_model
import models.audit_log as _audit_log_model
import models.session as _session_model
from config import engine, Base

Base.metadata.create_all(bind=engine)

# ── Environment ──
MINTA_ENV = os.environ.get("MINTA_ENV", "production").lower()

# ── Logging ──
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"minta-{datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    filename=str(log_file),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

app = FastAPI(
    title="Minta API",
    version="0.2.0-public",
    docs_url=None if MINTA_ENV in ("production", "prod") else "/docs",
    redoc_url=None,
)

# ── Startup: Expert CPGs + Auto-Scan Scheduler ──
@app.on_event("startup")
def _on_startup():
    """Initialize Expert CPGs and start lifecycle auto-scan scheduler."""
    _ensure_default_experts()
    _start_auto_scanner()


@app.on_event("shutdown")
def _on_shutdown():
    """Gracefully stop background schedulers."""
    from services.lifecycle_auto_scanner import stop_scheduler
    stop_scheduler()


def _start_auto_scanner():
    try:
        from services.lifecycle_auto_scanner import start_scheduler
        start_scheduler()
        print("[Minta] Lifecycle auto-scan scheduler started", file=sys.stderr)
    except Exception as e:
        print(f"[Minta] Auto-scan init failed: {e}", file=sys.stderr)


def _ensure_default_experts():
    """Expert system is a Pro feature — not included in the public release."""
    logging.info("Expert system: Pro feature, skipped in public version")

# ── Request body size limit (10 MB) ──
from fastapi import Request as _FRequest
@app.middleware("http")
async def limit_request_size(request: _FRequest, call_next):
    max_size = 10 * 1024 * 1024  # 10 MB
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > max_size:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed = f"{(time.time() - start) * 1000:.0f}ms"
    logging.info(f"{request.method} {request.url.path} | {response.status_code} | {elapsed}")
    return response

# CORS: default strict (production-safe). Dev can set MINTA_ENV=development for permissive.
if MINTA_ENV in ("production", "prod"):
    cors_origins = os.environ.get("MINTA_CORS_ORIGINS", "http://localhost:8772")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Security headers
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if MINTA_ENV in ("production", "prod"):
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"  # fallback for older browsers
    else:
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.include_router(inbox.router)
app.include_router(experiment_router)
app.include_router(autopilot_router)
app.include_router(context_objects.router)
app.include_router(upload.router)
app.include_router(skills.router)
app.include_router(auth.router)
app.include_router(api_keys.router)
app.include_router(verification.router)
app.include_router(comments.router)
app.include_router(admin.router)
app.include_router(user_data.router)
app.include_router(slots.router)
app.include_router(session_router.router)
app.include_router(lifecycle_router)
app.include_router(debt_router)

# ── Auto-scan endpoints (registered at app level to avoid cache issues) ──
from services.lifecycle_auto_scanner import get_state, set_enabled, set_interval
from routers.auth import get_current_user

@app.get("/api/lifecycle/auto-scan/status")
def _auto_scan_status(user = Depends(get_current_user)):
    """Get auto-scan configuration and last run info."""
    return {"ok": True, **get_state()}

@app.post("/api/lifecycle/auto-scan/toggle")
def _auto_scan_toggle(enabled: bool = Query(True), user = Depends(get_current_user)):
    """Enable or disable the automatic lifecycle scan scheduler."""
    return {"ok": True, **set_enabled(enabled)}

@app.post("/api/lifecycle/auto-scan/interval")
def _auto_scan_interval(hours: int = Query(24, ge=1, le=168), user = Depends(get_current_user)):
    """Change the auto-scan interval (1 hour to 7 days)."""
    return {"ok": True, **set_interval(hours)}


@app.get("/ping")
def ping():
    return {"ok": True}


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


# ── Demo: Story page ──
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


@app.get("/story")
async def serve_story():
    """Serve the interactive demo story page."""
    story_path = TEMPLATES_DIR / "story.html"
    if story_path.exists():
        return FileResponse(str(story_path))
    return {"error": "Story page not found."}


@app.post("/api/admin/seed-demo")
def seed_demo_data(user = Depends(get_current_user)):
    """Seed demo data into the database. One-time setup for showcase."""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "seed_demo.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(Path(__file__).resolve().parent),
        )
        return {"ok": True, "output": result.stdout, "stderr": result.stderr}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Production: serve built frontend ──
DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = DIST_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # SPA fallback: serve index.html for any unmatched route
        index = DIST_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built. Run: cd web && npm run build"}
 
