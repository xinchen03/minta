"""OCR service — lightweight text extraction from images.

Uses EasyOCR (CPU-friendly, Chinese + English).
Fallback: PaddleOCR if EasyOCR not installed.
Zero API calls. All local.
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        try:
            import easyocr
            _reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            logger.info("EasyOCR reader initialized (CPU, zh+en)")
        except ImportError:
            logger.warning("EasyOCR not installed. Install: pip install easyocr")
    return _reader


def extract_text(image_path: str) -> str:
    """Extract all text from an image. Returns concatenated text blocks."""
    reader = _get_reader()
    if reader is None:
        return ""

    try:
        results = reader.readtext(image_path)
        lines = []
        for bbox, text, confidence in results:
            if confidence > 0.4:
                lines.append(text.strip())
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"OCR failed for {image_path}: {e}")
        return ""


def extract_text_from_bytes(image_bytes: bytes, save_path: Optional[str] = None) -> str:
    """Extract text from image bytes. Optionally save to disk."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        text = extract_text(tmp_path)
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(image_bytes)
        return text
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
