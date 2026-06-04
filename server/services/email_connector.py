"""Email (.eml) ingestion — zero dependencies, Python stdlib only.

Parses .eml files into structured facts for Minta memory pipeline.
Extracts: From, To, Subject, Date, Body (plain+HTML), Attachments.
"""
from __future__ import annotations
import email
import email.policy
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def parse_eml(filepath: str) -> Dict:
    """Parse a .eml file into structured fields.

    Returns dict with keys: message_id, from_addr, to_addr, subject,
    date, body_text, body_html, attachment_count, attachment_names.
    """
    with open(filepath, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.default)

    # Headers
    from_addr = str(msg.get("From", ""))
    to_addr = str(msg.get("To", ""))
    subject = str(msg.get("Subject", ""))
    date_str = str(msg.get("Date", ""))
    message_id = str(msg.get("Message-ID", uuid.uuid4().hex[:12]))

    # Parse date
    parsed_date = None
    if date_str:
        try:
            from email.utils import parsedate_to_datetime
            parsed_date = parsedate_to_datetime(date_str).isoformat()
        except Exception:
            parsed_date = date_str

    # Body
    body_text = ""
    body_html = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))

            if "attachment" in disposition:
                filename = part.get_filename()
                if filename:
                    payload = part.get_payload(decode=True)
                    attachments.append({
                        "filename": filename,
                        "content_type": content_type,
                        "size": len(payload) if payload else 0,
                        "data": payload,
                    })
            elif content_type == "text/plain" and not body_text:
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="replace")
            elif content_type == "text/html" and not body_html:
                payload = part.get_payload(decode=True)
                if payload:
                    body_html = payload.decode("utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body_text = payload.decode("utf-8", errors="replace")

    return {
        "message_id": message_id,
        "from_addr": from_addr,
        "to_addr": to_addr,
        "subject": subject,
        "date": parsed_date or datetime.now(timezone.utc).isoformat(),
        "body_text": body_text[:5000],
        "body_html": body_html[:10000] if body_html else "",
        "attachment_count": len(attachments),
        "attachment_names": [a["filename"] for a in attachments],
        "_attachments": attachments,  # internal use
    }


def ingest_email(
    filepath: str,
    user_id: int,
    db_session=None,
    embedding_service=None,
    save_attachments_dir: str = "data/raw/attachments",
) -> Dict:
    """Parse .eml and ingest into Minta memory pipeline.

    1. Parse .eml → structured fields
    2. Save attachments to disk
    3. Create ContextObject → SQLite/MySQL
    4. Embed → ChromaDB vector index
    """
    parsed = parse_eml(filepath)

    # Save attachments
    saved_attachments = []
    for att in parsed.pop("_attachments", []):
        if att["data"]:
            os.makedirs(save_attachments_dir, exist_ok=True)
            att_path = os.path.join(save_attachments_dir, att["filename"])
            with open(att_path, "wb") as f:
                f.write(att["data"])
            saved_attachments.append(att_path)

    # Build memory record
    title = f"[Email] {parsed['subject'][:80]}"
    body_parts = [
        f"From: {parsed['from_addr']}",
        f"To: {parsed['to_addr']}",
        f"Date: {parsed['date']}",
        "",
        parsed["body_text"],
    ]
    if saved_attachments:
        body_parts.append(f"\nAttachments: {', '.join(parsed['attachment_names'])}")

    body = "\n".join(body_parts)
    memory_id = uuid.uuid4().hex[:16]

    # Save to DB
    if db_session:
        try:
            from models.context_object import ContextObject

            obj = ContextObject(
                id=memory_id,
                user_id=user_id,
                type="task_note",
                title=title,
                summary=f"Email from {parsed['from_addr']}: {parsed['subject'][:120]}",
                body=body,
                tags=["email", "multimodal"],
                source="document",
                status="active",
                confidence=4,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db_session.add(obj)
            db_session.commit()
        except Exception as e:
            logger.error(f"DB save failed for email {filepath}: {e}")
            if db_session:
                db_session.rollback()

    # Embed
    if embedding_service:
        try:
            emb_text = f"{title} {parsed['body_text'][:300]}"
            embedding_service.embed(emb_text)
        except Exception as e:
            logger.error(f"Embedding failed for {filepath}: {e}")

    return {
        "memory_id": memory_id,
        "title": title,
        "from": parsed["from_addr"],
        "subject": parsed["subject"],
        "date": parsed["date"],
        "attachment_count": len(saved_attachments),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
