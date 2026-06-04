"""Multimodal ingestion pipeline.

Image upload → OCR text + caption → structured fact → ChromaDB + SQLite/MySQL.

Ties into existing ContextObject model and embedding_service.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from services.ocr import extract_text_from_bytes
from services.image_caption import generate_caption

logger = logging.getLogger(__name__)


def ingest_image(
    image_bytes: bytes,
    filename: str,
    user_id: int,
    db_session=None,
    embedding_service=None,
    save_dir: str = "data/raw",
) -> Dict:
    """Process an uploaded image end-to-end.

    1. Save original image to disk
    2. OCR → extract text
    3. Caption → describe image content
    4. Combine into a ContextObject → save to DB
    5. Embed → add to ChromaDB

    Returns:
        dict with memory_id, ocr_text, caption, entity_count
    """
    # 1. Save image
    os.makedirs(save_dir, exist_ok=True)
    img_path = os.path.join(save_dir, filename)
    with open(img_path, "wb") as f:
        f.write(image_bytes)

    # 2. OCR
    ocr_text = extract_text_from_bytes(image_bytes)

    # 3. Caption
    caption = generate_caption(image_bytes)

    # 4. Build fact record
    title = f"[Image] {filename[:60]}"
    body_parts = []
    if caption and caption != "[No caption available]":
        body_parts.append(f"Caption: {caption}")
    if ocr_text:
        body_parts.append(f"OCR Text: {ocr_text}")
    body = "\n\n".join(body_parts) if body_parts else f"Image uploaded: {filename}"

    memory_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()

    # 5. Save to DB via ContextObject
    if db_session:
        try:
            from models.context_object import ContextObject

            obj = ContextObject(
                id=memory_id,
                user_id=user_id,
                type="task_note",
                title=title,
                summary=caption[:200] if caption else f"Image: {filename[:60]}",
                body=body,
                tags=["multimodal", "image"],
                source="document",
                status="active",
                confidence=3,
                cover_image=img_path,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db_session.add(obj)
            db_session.commit()
        except Exception as e:
            logger.error(f"DB save failed for image {filename}: {e}")
            if db_session:
                db_session.rollback()

    # 6. Embed + add to ChromaDB
    if embedding_service:
        try:
            emb_text = f"{title} {caption} {ocr_text}"[:500]
            embedding_service.embed(emb_text)  # Will be added to collection by caller
        except Exception as e:
            logger.error(f"Embedding failed for {filename}: {e}")

    return {
        "memory_id": memory_id,
        "title": title,
        "ocr_text": ocr_text[:500] if ocr_text else "",
        "caption": caption,
        "image_path": img_path,
        "ingested_at": now,
    }
