from __future__ import annotations

from pathlib import Path

from app.config import Settings, get_settings
from app.ingestion.models import IngestedDocument
from app.ingestion.pdf_handler import ingest_pdf
from app.ingestion.text_handler import ingest_text


def ingest_file(path: str | Path, settings: Settings | None = None) -> IngestedDocument:
    settings = settings or get_settings()
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Input document does not exist: {file_path}")
    if file_path.stat().st_size > settings.max_file_size_bytes:
        raise ValueError(f"Input document exceeds {settings.max_file_size_mb} MB limit")
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return ingest_pdf(file_path, settings)
    if suffix in {".txt", ".text"}:
        return ingest_text(file_path)
    if suffix == ".eml":
        raise ValueError("EML ingestion is not supported yet")
    raise ValueError(f"Unsupported document type: {suffix or '<none>'}")
