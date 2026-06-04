"""File upload router — cover images, avatars, and multimodal ingestion."""
import os
import uuid
from typing import Optional
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession
from config import get_db
from routers.auth import get_current_user, User
from services.embedding_service import EmbeddingService

COVER_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist" / "assets" / "covers"
AVATAR_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "dist" / "assets" / "avatars"
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


@router.post("/ingest-image")
async def ingest_image_endpoint(
    file: UploadFile = File(...),
    extract_text: bool = Query(True, description="Run OCR to extract text from image"),
    generate_desc: bool = Query(True, description="Generate image caption"),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Upload an image for full multimodal ingestion.

    OCR → extract text. Caption → describe content.
    Result stored as ContextObject + ChromaDB vector.
    """
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"Unsupported type: {file.content_type}")
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(400, f"File too large ({len(contents)} bytes). Max 5 MB.")

    from services.multimodal_ingest import ingest_image

    emb = EmbeddingService(backend="chromadb")
    result = ingest_image(
        image_bytes=contents,
        filename=file.filename or "upload.png",
        user_id=user.id,
        db_session=db,
        embedding_service=emb,
        save_dir=str(Path(__file__).resolve().parent.parent / "data" / "raw"),
    )

    return {"ok": True, **result}


@router.post("/ingest-email")
async def ingest_email_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Upload a .eml file for email ingestion.

    Parses From/To/Subject/Body/Attachments into ContextObject + ChromaDB.
    """
    if not file.filename or not file.filename.lower().endswith((".eml", ".mht")):
        raise HTTPException(400, "Only .eml files are supported")
    contents = await file.read()
    if len(contents) > MAX_SIZE * 2:  # 10MB for emails
        raise HTTPException(400, f"File too large ({len(contents)} bytes). Max 10 MB.")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".eml", delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        from services.email_connector import ingest_email
        emb = EmbeddingService(backend="chromadb")
        result = ingest_email(
            filepath=tmp_path,
            user_id=user.id,
            db_session=db,
            embedding_service=emb,
            save_attachments_dir=str(Path(__file__).resolve().parent.parent / "data" / "raw" / "attachments"),
        )
        return {"ok": True, **result}
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
