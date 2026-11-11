from __future__ import annotations

from pathlib import Path

from app.confidence.scorer import ConfidenceScorer
from app.config import Settings
from app.extraction.extractor import build_extraction
from app.pipeline import process_document
from app.providers.mock_provider import MockProvider
from app.schemas.enums import ApprovalStatus, RoutingDecision
from app.validation.validators import validate_extraction


def test_mock_pipeline_extracts_and_routes_sample(tmp_path: Path) -> None:
    document = tmp_path / "change-order.txt"
    document.write_text(
        "\n".join(
            [
                "Project: Demo",
                "Project Number: P-1",
                "Change Order Number: CO-1",
                "Type: Additive",
                "1. Work - $100.00",
                "Subtotal: $100.00",
                "Markup (15%): $15.00",
                "Total This Change Order: $115.00",
                "Original Contract Sum: $1,000.00",
                "Previous Change Orders Net: $0.00",
                "Contract Sum Prior to This CO: $1,000.00",
                "New Contract Sum: $1,115.00",
                "Status: Approved",
                "Approved By: Reviewer",
                "Approval Date: January 10, 2025",
            ]
        ),
        encoding="utf-8",
    )

    result = process_document(document, Settings(llm_provider="mock"))

    extraction = result.extractions[0]
    assert extraction.change_order.number.value == "CO-1"
    assert extraction.financials.total.value == 115
    assert result.routing_decision in {
        RoutingDecision.READY_FOR_REVIEW,
        RoutingDecision.NEEDS_REVIEW,
        RoutingDecision.BLOCKED,
    }


def test_parser_rejects_labels_and_approval_placeholders() -> None:
    text = """
Project Name
Downtown Office Renovation
Owner: Approval: ______ Date: ______
Contractor: ____________________
Change Order Number: CO-001
Title:
Additional lighting
Reason:
Tenant request
Scope:
Install fixtures on level 2
Subtotal: $1,200.00
"""

    record = MockProvider().extract(text)[0]

    assert record["project"]["name"] == "Downtown Office Renovation"
    assert record["parties"]["owner"]["name"] is None
    assert record["parties"]["contractor"]["name"] is None
    assert record["change_order"]["title"] == "Additional lighting"
    assert record["change_order"]["reason"] == "Tenant request"
    assert record["change_order"]["scope"] == "Install fixtures on level 2"


def test_label_only_evidence_cannot_receive_full_confidence() -> None:
    scorer = ConfidenceScorer()

    label_only = scorer.score_field(
        "project.name",
        evidence_quote="Project Name",
        source_text="Project Name",
        value="Name",
        validation_passed=True,
    )
    missing = scorer.score_field(
        "parties.owner.name",
        evidence_quote=None,
        source_text="Owner: ____________________",
        value=None,
        validation_passed=True,
    )
    document = scorer.score_document([label_only, missing])

    assert label_only.overall_score < 1.0
    assert missing.overall_score <= 0.25
    assert document.num_low_confidence_fields == 2


def test_status_extracts_token_and_preserves_explanatory_raw_text() -> None:
    text = (
        "Status: Proposed — pending written approval. Work described in this "
        "change order must not proceed until authorization is received."
    )
    record = MockProvider().extract(text)[0]
    extraction = build_extraction(record, "test.pdf", 1)

    assert record["approval"]["status"] == "proposed"
    assert extraction.approval.status.value == ApprovalStatus.PENDING
    assert extraction.approval.status.raw_text == (
        "Proposed — pending written approval. Work described in this "
        "change order must not proceed until authorization is received."
    )


def test_invalid_status_becomes_unknown_instead_of_crashing() -> None:
    extraction = build_extraction(
        {"approval": {"status": "Awaiting legal review before authorization"}},
        "test.pdf",
        1,
    )

    assert extraction.approval.status.value == ApprovalStatus.UNKNOWN
    assert extraction.approval.status.raw_text == "Awaiting legal review before authorization"
    report = validate_extraction(extraction)
    assert report.warning_count == 0


def test_passed_warning_rules_do_not_change_validation_status() -> None:
    extraction = build_extraction(
        {
            "financials": {
                "subtotal": "2400.00",
                "markup_pct": "10",
                "markup_amount": "240.00",
                "total": "2640.00",
            },
            "approval": {"status": "approved", "approved_by": "Reviewer", "date": "January 10, 2025"},
        }
    )

    report = validate_extraction(extraction)

    assert report.warning_count == 0
    assert report.overall_result.value == "passed"


def test_failed_warning_rule_changes_validation_status_to_warning() -> None:
    extraction = build_extraction(
        {
            "financials": {
                "subtotal": "2400.00",
                "total": "2500.00",
            }
        }
    )

    report = validate_extraction(extraction)

    assert report.warning_count == 1
    assert report.failed_count == 0
    assert report.overall_result.value == "warning"
