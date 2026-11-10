"""Ingestion module: file type detection, PDF/text parsing, and document preparation."""

from app.ingestion.ingest import ingest_file
from app.ingestion.models import IngestedDocument

__all__ = ["IngestedDocument", "ingest_file"]
