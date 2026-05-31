"""File upload router — cover images and avatars."""
import os
import uuid
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from routers.auth import get_current_user, User

COVER_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "public" / "assets" / "covers"
AVATAR_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "public" / "assets" / "avatars"
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_SIZE = 5 * 1024 * 1024  # 5 MB

router = APIRouter(prefix="/api/upload", tags=["upload"])


def _save_upload(contents: bytes, filename: Optional[str], upload_dir: Path) -> str:
    ext = ".png"
    if filename and "." in filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            ext = ".png"

    name = f"{uuid.uuid4().hex[:12]}{ext}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    (upload_dir / name).write_bytes(contents)

    prefix = "avatars" if "avatars" in str(upload_dir) else "covers"
    return f"/assets/{prefix}/{name}"


@router.post("/cover")
async def upload_cover(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported type: {file.content_type}")
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(400, f"File too large ({len(contents)} bytes). Max 5 MB.")
    url = _save_upload(contents, file.filename, COVER_DIR)
    return {"path": url, "filename": url.rsplit("/", 1)[-1]}


@router.post("/avatar")
async def upload_avatar(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported type: {file.content_type}")
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(400, f"File too large ({len(contents)} bytes). Max 5 MB.")
    url = _save_upload(contents, file.filename, AVATAR_DIR)
    return {"path": url, "filename": url.rsplit("/", 1)[-1]}
