from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.confidence.scorer import ConfidenceScorer, FieldConfidence
from app.config import Settings, get_settings
from app.extraction.extractor import Extractor
from app.ingestion.ingest import ingest_file
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.mock_provider import MockProvider
from app.routing.router import route_extraction
from app.schemas.change_order import ChangeOrderExtraction, ExtractionResult
from app.schemas.enums import ValidationResult
from app.schemas.fields import ExtractedField
from app.validation.validators import validate_extraction


def _provider(settings: Settings):
    if settings.llm_provider == "anthropic":
        return AnthropicProvider(settings.anthropic_api_key, settings.model_name)
    return MockProvider()


def _field_scores(
    extraction: ChangeOrderExtraction, source_text: str, validation_passed: bool, is_scanned: bool
) -> list[FieldConfidence]:
    scorer = ConfidenceScorer()
    return [
        scorer.score_field(
            path,
            field.evidence.quote if field.evidence else field.raw_text,
            source_text,
            field.value,
            validation_passed=validation_passed,
            is_scanned=is_scanned,
            has_ambiguity=bool(getattr(field, "ambiguous", False)),
        )
        for path, field in _iter_extracted_fields(extraction)
    ]


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


def _validation_status(path: str, report: Any) -> str:
    matching = [
        result
        for result in report.results
        if result.field_path
        and (path == result.field_path or path.startswith(f"{result.field_path}."))
    ]
    if not matching:
        return "not_checked"
    if any(not result.passed for result in matching):
        return "failed"
    if any(result.severity == "warning" for result in matching):
        return "warning"
    return "passed"


def _attach_field_metadata(
    extraction: ChangeOrderExtraction,
    scores: list[FieldConfidence],
    report: Any,
) -> None:
    fields = dict(_iter_extracted_fields(extraction))
    for score in scores:
        field = fields[score.field_path]
        field.confidence = score.overall_score
        field.validation = _validation_status(score.field_path, report)


def process_document(path: str | Path, settings: Settings | None = None) -> ExtractionResult:
    settings = settings or get_settings()
    document = ingest_file(path, settings)
    extractions = Extractor(_provider(settings)).extract(
        document.text, document.pages, document.path.name
    )
    validation_reports = [validate_extraction(item, document.text) for item in extractions]
    scorer = ConfidenceScorer()
    confidence_reports = []
    decisions = []
    for extraction, report in zip(extractions, validation_reports, strict=True):
        scores = _field_scores(
            extraction, document.text, report.failed_count == 0, document.is_scanned
        )
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
    decision = (
        decisions[0]
        if decisions and all(item == decisions[0] for item in decisions)
        else route_extraction(
            next(
                (report.overall_result for report in validation_reports if report.failed_count),
                ValidationResult.WARNING,
            ),
            min((report.overall_score for report in confidence_reports), default=0.0),
            sum(report.num_low_confidence_fields for report in confidence_reports),
        )
    )
    return ExtractionResult(
        source_file=str(document.path),
        extractions=extractions,
        validation=[report.to_dict() for report in validation_reports],
        confidence=[report.to_dict() for report in confidence_reports],
        routing_decision=decision,
    )
