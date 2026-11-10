from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.pipeline import process_document
from app.routing.router import route_extraction
from app.schemas.enums import RoutingDecision, ValidationResult


def test_fields_have_evidence_and_individual_confidence() -> None:
    result = process_document(
        Path("data/synthetic/documents/co_001_clean_txt.txt"),
        Settings(llm_provider="mock"),
    )
    extraction = result.extractions[0]
    assert extraction.project.name.evidence is not None
    assert extraction.project.name.evidence.page == 1
    assert "Project:" in extraction.project.name.evidence.quote
    assert 0.0 <= extraction.project.name.confidence <= 1.0
    assert extraction.project.name.validation in {"passed", "warning", "failed", "not_checked"}
    assert extraction.financials.total.validation in {"passed", "warning", "failed", "not_checked"}
    scored_paths = {
        item["field_path"] for item in result.confidence[0]["field_scores"]
    }
    assert "project.name" in scored_paths
    assert "financials.total" in scored_paths
    assert len(scored_paths) >= 20


def test_routing_never_returns_financial_approval() -> None:
    assert RoutingDecision.READY_FOR_REVIEW.value == "ready_for_review"
    assert "approved" not in {decision.value for decision in RoutingDecision}


def test_routing_covers_all_review_states() -> None:
    assert (
        route_extraction(ValidationResult.PASSED, 0.9, 0)
        == RoutingDecision.READY_FOR_REVIEW
    )
    assert (
        route_extraction(ValidationResult.WARNING, 0.9, 0)
        == RoutingDecision.NEEDS_REVIEW
    )
    assert (
        route_extraction(ValidationResult.FAILED, 0.9, 0)
        == RoutingDecision.BLOCKED
    )
