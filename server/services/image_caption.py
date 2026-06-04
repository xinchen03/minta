"""Image captioning — generates text descriptions for images.

Dual mode:
- local: BLIP (salesforce/blip-image-captioning-base), ~1GB, CPU workable
- api: GPT-4o-mini / Qwen-VL via OpenAI-compatible API (faster, higher quality)

Auto-falls back: local model if available, else API if key present.
"""
from __future__ import annotations
import base64
import logging
import os
from io import BytesIO
from typing import Optional

logger = logging.getLogger(__name__)

_local_model = None
_local_processor = None


def _get_local_model():
    global _local_model, _local_processor
    if _local_model is None:
        try:
            from transformers import BlipProcessor, BlipForConditionalGeneration
            _local_processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-base")
            _local_model = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-base")
            logger.info("BLIP captioning model loaded (CPU)")
        except ImportError:
            logger.warning("transformers not installed. BLIP unavailable.")
        except Exception as e:
            logger.warning(f"BLIP load failed: {e}")
    return _local_model, _local_processor


def caption_local(image_bytes: bytes) -> str:
    """Generate caption using local BLIP model."""
    model, processor = _get_local_model()
    if model is None:
        return ""

    try:
        from PIL import Image
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        inputs = processor(img, return_tensors="pt")
        out = model.generate(**inputs, max_new_tokens=50)
        caption = processor.decode(out[0], skip_special_tokens=True)
        return caption.strip()
    except Exception as e:
        logger.error(f"BLIP caption failed: {e}")
        return ""


def caption_api(image_bytes: bytes, api_key: str = None,
                base_url: str = None, model: str = "gpt-4o-mini") -> str:
    """Generate caption using OpenAI-compatible Vision API."""
    if api_key is None:
        api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("No API key for vision captioning")
        return ""

    try:
        import requests
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        url = base_url or "https://api.openai.com/v1/chat/completions"

        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image in one sentence. Focus on what information it contains: text, UI elements, people, objects, or scenes. Be concise."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
            "max_tokens": 100,
            "temperature": 0,
        }

        resp = requests.post(url, json=payload, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        else:
            logger.warning(f"Vision API error: {resp.status_code} {resp.text[:200]}")
            return ""
    except Exception as e:
        logger.error(f"Vision API call failed: {e}")
        return ""


def generate_caption(image_bytes: bytes) -> str:
    """Auto-select caption method: local BLIP first, fallback to API."""
    caption = caption_local(image_bytes)
    if caption:
        return f"[BLIP] {caption}"

    caption = caption_api(image_bytes)
    if caption:
        return f"[Vision API] {caption}"

    return "[No caption available]"
