"""Test configuration and shared fixtures for SledgeCO-AI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

# Test data directory
TEST_DATA_DIR = Path(__file__).parent / "test_data"
PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def sample_text_content() -> str:
    """A simple change order in plain text format for testing."""
    return """
CHANGE ORDER

Project: Downtown Office Building Renovation
Project Number: PRJ-2024-001
Location: 123 Main Street, Suite 100, Chicago, IL 60601

Owner: Acme Development Corp
Contractor: BuildRight Construction LLC
Subcontractor: N/A

Change Order Number: CO-003
Title: Additional Electrical Work - Floor 3
Reason: Design revision per architect's supplemental instruction SI-007
Scope: Additional electrical outlets and data drops on 3rd floor east wing
Type: Additive

Line Items:
1. Install 24 additional duplex outlets - $4,800.00
2. Install 12 data/voice drops with Cat6 cabling - $3,600.00
3. Panel upgrade and circuit breakers - $1,200.00

Subtotal: $9,600.00
Markup (15%): $1,440.00
Total This Change Order: $11,040.00

Original Contract Sum: $2,450,000.00
Previous Change Orders Net: $34,500.00
Contract Sum Prior to This CO: $2,484,500.00
New Contract Sum: $2,495,540.00

Schedule Impact: 5 calendar days added
Revised Completion Date: March 15, 2025

Status: Approved
Approved By: John Smith, Project Manager
Approval Date: January 10, 2025
"""


@pytest.fixture
def sample_ground_truth() -> dict[str, Any]:
    """Ground truth for the sample text content above."""
    return {
        "project": {
            "name": "Downtown Office Building Renovation",
            "number": "PRJ-2024-001",
            "address": "123 Main Street, Suite 100, Chicago, IL 60601",
        },
        "parties": {
            "owner": {"name": "Acme Development Corp"},
            "contractor": {"name": "BuildRight Construction LLC"},
            "subcontractor": {"name": None},
        },
        "change_order": {
            "number": "CO-003",
            "title": "Additional Electrical Work - Floor 3",
            "reason": "Design revision per architect's supplemental instruction SI-007",
            "scope": "Additional electrical outlets and data drops on 3rd floor east wing",
            "type": "additive",
        },
        "financials": {
            "line_items": [
                {"description": "Install 24 additional duplex outlets", "amount": 4800.00},
                {
                    "description": "Install 12 data/voice drops with Cat6 cabling",
                    "amount": 3600.00,
                },
                {"description": "Panel upgrade and circuit breakers", "amount": 1200.00},
            ],
            "subtotal": 9600.00,
            "markup_pct": 15.0,
            "markup_amount": 1440.00,
            "total": 11040.00,
            "original_contract_sum": 2450000.00,
            "net_previous_changes": 34500.00,
            "contract_sum_prior": 2484500.00,
            "new_contract_sum": 2495540.00,
        },
        "schedule": {
            "days_added": 5,
            "revised_completion_date": "2025-03-15",
        },
        "approval": {
            "status": "approved",
            "approved_by": "John Smith, Project Manager",
            "date": "2025-01-10",
        },
    }


@pytest.fixture
def mock_settings():
    """Create settings configured for testing (mock provider, no API key)."""
    from app.config import Settings

    return Settings(
        llm_provider="mock",
        anthropic_api_key="",
        log_level="DEBUG",
        log_document_text=False,
    )
