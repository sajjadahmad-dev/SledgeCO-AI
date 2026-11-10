from __future__ import annotations

from pathlib import Path

from app.ingestion.models import IngestedDocument


def ingest_text(path: Path) -> IngestedDocument:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        import chardet

        detected = chardet.detect(raw).get("encoding") or "latin-1"
        text = raw.decode(detected, errors="replace")
    return IngestedDocument(path, "txt", text, [text], False)
