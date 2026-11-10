from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.pipeline import process_document
from app.schemas.enums import RoutingDecision


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
    }
