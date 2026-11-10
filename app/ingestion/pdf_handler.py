from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

from app.config import Settings
from app.ingestion.models import IngestedDocument


def ingest_pdf(path: Path, settings: Settings) -> IngestedDocument:
    with pymupdf.open(path) as document:
        pages = [page.get_text("text") for page in document]
        page_sources: list[str] = []
        ocr_confidences: list[float | None] = []
        for index, text in enumerate(pages):
            if len(text.strip()) >= settings.min_text_chars_per_page:
                page_sources.append("text")
                ocr_confidences.append(None)
                continue
            image = _render_page(document[index], settings.scan_render_dpi)
            ocr_text, confidence = _ocr_image(
                image,
                settings.ocr_language,
                settings.ocr_timeout_seconds,
                settings.tesseract_cmd,
            )
            pages[index] = ocr_text
            page_sources.append("ocr")
            ocr_confidences.append(confidence)
    is_scanned = any(source == "ocr" for source in page_sources)
    return IngestedDocument(
        path,
        "pdf",
        "\n\n".join(pages),
        pages,
        is_scanned,
        page_sources,
        ocr_confidences,
    )


def _render_page(page: pymupdf.Page, dpi: int) -> Image.Image:
    matrix = pymupdf.Matrix(dpi / 72, dpi / 72)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _ocr_image(
    image: Image.Image,
    language: str,
    timeout_seconds: int,
    tesseract_cmd: str = "",
) -> tuple[str, float | None]:
    try:
        import pytesseract
        from pytesseract import Output
    except ImportError as exc:
        raise RuntimeError(
            "OCR requires pytesseract and a Tesseract executable. "
            "Install the OCR optional dependencies and Tesseract."
        ) from exc
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    try:
        data = pytesseract.image_to_data(
            image,
            lang=language,
            output_type=Output.DICT,
            timeout=timeout_seconds,
        )
        text = pytesseract.image_to_string(
            image,
            lang=language,
            timeout=timeout_seconds,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract executable was not found. Install Tesseract and add it to PATH."
        ) from exc
    except (pytesseract.TesseractError, OSError) as exc:
        detail = str(exc) or exc.__class__.__name__
        raise RuntimeError(f"Tesseract OCR failed: {detail}") from exc
    confidences = [
        float(value)
        for value in data["conf"]
        if str(value).strip() not in {"", "-1"} and float(value) >= 0
    ]
    return text, sum(confidences) / len(confidences) / 100 if confidences else None
