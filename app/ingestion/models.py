from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IngestedDocument:
    path: Path
    file_type: str
    text: str
    pages: list[str]
    is_scanned: bool = False
    page_sources: list[str] | None = None
    ocr_confidences: list[float | None] | None = None
