from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.confidence.scorer import ConfidenceScorer, FieldConfidence
from app.config import Settings, get_settings
from app.extraction.extractor import Extractor
from app.ingestion.ingest import ingest_file
from app.providers.gemini_provider import GeminiProvider
from app.providers.mock_provider import MockProvider
from app.routing.router import route_extraction
from app.schemas.change_order import ChangeOrderExtraction, ExtractionResult
from app.schemas.enums import ValidationResult
from app.schemas.fields import ExtractedField
from app.validation.validators import validate_extraction

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Clear, user-facing pipeline failure (instead of silently returning empty output)."""


def _provider(settings: Settings):
    name = (settings.llm_provider or "").strip().lower()
    if name == "gemini":
        return GeminiProvider()
    if name == "mock":
        logger.warning("Using MockProvider: output is NOT extracted from the document")
        return MockProvider()
    raise PipelineError(f"Unknown llm_provider {settings.llm_provider!r}; use gemini or mock")


def _iter_extracted_fields(value: Any, path: str = ""):
    if isinstance(value, ExtractedField):
        yield path, value
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_extracted_fields(item, f"{path}[{index}]")
        return
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            child_path = f"{path}.{name}" if path else name
            yield from _iter_extracted_fields(getattr(value, name), child_path)


def _path_matches(path: str, result_path: str) -> bool:
    # "line_items" must match "line_items[0].amount" as well as "total.value"
    return path == result_path or path.startswith((f"{result_path}.", f"{result_path}["))


def _validation_status(path: str, report: Any) -> str:
    matching = [r for r in report.results if r.field_path and _path_matches(path, r.field_path)]
    if not matching:
        return "not_checked"
    if any(not r.passed for r in matching):
        return "failed"
    if any(r.severity == "warning" for r in matching):
        return "warning"
    return "passed"


def _field_scores(
    extraction: ChangeOrderExtraction, source_text: str, report: Any, is_scanned: bool
) -> list[FieldConfidence]:
    scorer = ConfidenceScorer()
    scores: list[FieldConfidence] = []
    for path, field in _iter_extracted_fields(extraction):
        if field.value is None or field.value == "":
            continue  # missing field: nothing to score, must not count as "low confidence"
        status = _validation_status(path, report)
        scores.append(
            scorer.score_field(
                path,
                field.evidence.quote if field.evidence else None,
                source_text,
                field.raw_text or field.value,   # <- printed text, not the normalized value
                validation_passed=status != "failed",
                is_scanned=is_scanned,
                has_ambiguity=bool(getattr(field, "ambiguous", False)),
            )
        )
    return scores


def _attach_field_metadata(
    extraction: ChangeOrderExtraction, scores: list[FieldConfidence], report: Any
) -> None:
    fields = dict(_iter_extracted_fields(extraction))
    for score in scores:
        field = fields[score.field_path]
        field.confidence = score.overall_score
        field.validation = _validation_status(score.field_path, report)


def process_document(path: str | Path, settings: Settings | None = None) -> ExtractionResult:
    settings = settings or get_settings()
    provider = _provider(settings)
    document = ingest_file(path, settings)

    if not (document.text or "").strip():
        raise PipelineError(
            "No text could be read from the document (scanned PDF or empty file). "
            "OCR or a vision-capable model is needed."
        )

    extractions = Extractor(provider).extract(document.text, document.pages, document.path.name)
    if not extractions:
        raise PipelineError("Extractor returned no change orders; check the provider output and prompt.")

    scorer = ConfidenceScorer()
    validation_reports = [validate_extraction(item, document.text) for item in extractions]
    confidence_reports = []
    decisions = []
    for extraction, report in zip(extractions, validation_reports, strict=True):
        scores = _field_scores(extraction, document.text, report, document.is_scanned)
        _attach_field_metadata(extraction, scores, report)
        confidence = scorer.score_document(scores)
        confidence_reports.append(confidence)
        decisions.append(
            route_extraction(
                report.overall_result,
                confidence.overall_score,
                confidence.num_low_confidence_fields,
            )
        )

    if all(item == decisions[0] for item in decisions):
        decision = decisions[0]
    else:  # several change orders disagree -> route on the most conservative aggregate
        decision = route_extraction(
            next((r.overall_result for r in validation_reports if r.failed_count), ValidationResult.WARNING),
            min(r.overall_score for r in confidence_reports),
            sum(r.num_low_confidence_fields for r in confidence_reports),
        )

    return ExtractionResult(
        source_file=str(document.path),
        extractions=extractions,
        validation=[r.to_dict() for r in validation_reports],
        confidence=[r.to_dict() for r in confidence_reports],
        routing_decision=decision,
    )
