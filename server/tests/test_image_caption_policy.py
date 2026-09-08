"""Image ingestion must never call a model unless the user opts in."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services import image_caption, multimodal_ingest


def test_captioning_is_off_by_default(monkeypatch):
    monkeypatch.delenv("MINTA_IMAGE_CAPTION_BACKEND", raising=False)
    monkeypatch.setattr(
        image_caption,
        "caption_local",
        lambda _data: (_ for _ in ()).throw(AssertionError("local model called")),
    )
    monkeypatch.setattr(
        image_caption,
        "caption_api",
        lambda _data, **_kwargs: (_ for _ in ()).throw(AssertionError("API called")),
    )
    assert image_caption.generate_caption(b"image") == "[No caption available]"


def test_api_mode_uses_only_minta_specific_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.delenv("MINTA_IMAGE_CAPTION_API_KEY", raising=False)
    assert image_caption.caption_api(b"image") == ""


def test_ingest_flags_skip_ocr_and_caption(tmp_path, monkeypatch):
    monkeypatch.setattr(
        multimodal_ingest,
        "extract_text_from_bytes",
        lambda _data: (_ for _ in ()).throw(AssertionError("OCR called")),
    )
    monkeypatch.setattr(
        multimodal_ingest,
        "generate_caption",
        lambda _data: (_ for _ in ()).throw(AssertionError("caption called")),
    )

    result = multimodal_ingest.ingest_image(
        b"not-a-real-image",
        "sample.png",
        user_id=1,
        save_dir=str(tmp_path),
        extract_text=False,
        generate_desc=False,
    )

    assert result["ocr_text"] == ""
    assert result["caption"] == ""
