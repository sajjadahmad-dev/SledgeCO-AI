from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.config import Settings
from app.ingestion.pdf_handler import ingest_pdf


def test_image_only_pdf_uses_real_ocr_or_reports_missing_runtime() -> None:
    image_pdf = next(Path("data/synthetic/documents").glob("*scanned_pdf.pdf"))
    try:
        ingested = ingest_pdf(image_pdf, Settings())
    except RuntimeError as exc:
        assert "Tesseract" in str(exc)
        pytest.skip(str(exc))
    assert ingested.is_scanned is True
    assert ingested.page_sources == ["ocr"]
    assert ingested.ocr_confidences is not None


def test_mixed_pdf_preserves_text_and_ocr_page_sources(tmp_path: Path) -> None:
    scanned = next(Path("data/synthetic/documents").glob("*scanned_pdf.pdf"))
    mixed_path = tmp_path / "mixed.pdf"
    with pymupdf.open() as mixed, pymupdf.open(scanned) as source:
        text_page = mixed.new_page()
        text_page.insert_text(
            (72, 72),
            "Project: selectable page with enough text to remain a selectable text page "
            "without OCR fallback.",
        )
        image_page = mixed.new_page()
        pixmap = source[0].get_pixmap()
        image_page.insert_image(
            image_page.rect,
            stream=pixmap.tobytes("png"),
        )
        mixed.save(mixed_path)
    try:
        ingested = ingest_pdf(mixed_path, Settings())
    except RuntimeError as exc:
        assert "Tesseract" in str(exc)
        pytest.skip(str(exc))
    assert ingested.page_sources == ["text", "ocr"]
    assert ingested.ocr_confidences is not None
    assert ingested.ocr_confidences[0] is None
    assert ingested.ocr_confidences[1] is not None
