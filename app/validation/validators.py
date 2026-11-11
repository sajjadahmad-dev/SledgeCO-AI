"""
Validation orchestrator: runs all business rules against extracted data.

Collects results from individual rules and produces a comprehensive
validation report. Never modifies the extraction data — only annotates
it with validation results and generates warnings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.schemas.enums import ValidationResult
from app.validation.rules import (
    ValidationRuleResult,
    check_ambiguous_date,
    check_approval_completeness,
    check_change_order_type_consistency,
    check_contract_sum_progression,
    check_date_plausibility,
    check_line_items_sum,
    check_markup_calculation,
    check_pco_vs_co,
)

logger = logging.getLogger(__name__)

__all__ = ["validate_extraction", "ValidationReport"]


@dataclass
class ValidationReport:
    """Summary of all validation checks run against an extraction."""

    results: list[ValidationRuleResult] = field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    warning_count: int = 0
    overall_result: ValidationResult = ValidationResult.NOT_CHECKED

    @property
    def all_passed(self) -> bool:
        """True if no rules failed (warnings are acceptable)."""
        return self.failed_count == 0

    @property
    def has_warnings(self) -> bool:
        return self.warning_count > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for JSON output."""
        return {
            "overall_result": self.overall_result.value,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "warning_count": self.warning_count,
            "rules": [
                {
                    "rule_name": r.rule_name,
                    "passed": r.passed,
                    "message": r.message,
                    "severity": r.severity,
                    "field_path": r.field_path,
                    "details": r.details,
                }
                for r in self.results
                if r.severity != "info"  # Only include non-trivial results
            ],
        }


def _safe_decimal(value: Any) -> Decimal | None:
    """Safely extract Decimal from an ExtractedField or raw value."""
    if value is None:
        return None
    # Handle ExtractedField wrapper
    if hasattr(value, "value"):
        value = value.value
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _safe_value(field_obj: Any) -> Any:
    """Safely extract value from an ExtractedField or return raw value."""
    if field_obj is None:
        return None
    if hasattr(field_obj, "value"):
        return field_obj.value
    return field_obj


def _safe_raw_text(field_obj: Any) -> str | None:
    """Safely extract raw_text from an ExtractedField."""
    if field_obj is None:
        return None
    if hasattr(field_obj, "raw_text"):
        return field_obj.raw_text
    return str(field_obj) if field_obj is not None else None


def validate_extraction(
    extraction: Any,
    source_text: str | None = None,
) -> ValidationReport:
    """
    Run all validation rules against a ChangeOrderExtraction.

    Args:
        extraction: A ChangeOrderExtraction model instance
        source_text: Optional source document text for PCO/CO checking

    Returns:
        ValidationReport with all rule results
    """
    report = ValidationReport()
    all_results: list[ValidationRuleResult] = []

    # ---- Financial Validations ----
    financials = getattr(extraction, "financials", None)

    if financials is not None:
        # 1. Line items sum = subtotal
        line_item_amounts = []
        for item in getattr(financials, "line_items", []):
            amount = _safe_decimal(getattr(item, "amount", None))
            line_item_amounts.append(amount)

        subtotal = _safe_decimal(getattr(financials, "subtotal", None))
        all_results.append(check_line_items_sum(line_item_amounts, subtotal))

        # 2. Markup calculations
        markup_pct_val = _safe_value(getattr(financials, "markup_pct", None))
        markup_pct = float(markup_pct_val) if markup_pct_val is not None else None
        markup_amount = _safe_decimal(getattr(financials, "markup_amount", None))
        total = _safe_decimal(getattr(financials, "total", None))
        all_results.extend(check_markup_calculation(subtotal, markup_pct, markup_amount, total))

        # 3. Contract sum progression
        original = _safe_decimal(getattr(financials, "original_contract_sum", None))
        net_prev = _safe_decimal(getattr(financials, "net_previous_changes", None))
        prior = _safe_decimal(getattr(financials, "contract_sum_prior", None))
        new_sum = _safe_decimal(getattr(financials, "new_contract_sum", None))
        all_results.extend(
            check_contract_sum_progression(original, net_prev, prior, total, new_sum)
        )

    # ---- CO Type Consistency ----
    change_order = getattr(extraction, "change_order", None)
    if change_order is not None and financials is not None:
        co_type_val = _safe_value(getattr(change_order, "type", None))
        co_type_str = (
            co_type_val.value
            if hasattr(co_type_val, "value")
            else str(co_type_val)
            if co_type_val
            else None
        )
        total = _safe_decimal(getattr(financials, "total", None))
        all_results.append(check_change_order_type_consistency(co_type_str, total))

    # ---- Date Validations ----
    schedule = getattr(extraction, "schedule", None)
    if schedule is not None:
        # Revised completion date
        revised_date = _safe_value(getattr(schedule, "revised_completion_date", None))
        if revised_date is not None:
            all_results.append(
                check_date_plausibility(
                    revised_date, "revised_completion_date", "schedule.revised_completion_date"
                )
            )

        # Check for ambiguous dates
        revised_raw = _safe_raw_text(getattr(schedule, "revised_completion_date", None))
        is_ambiguous = getattr(
            getattr(schedule, "revised_completion_date", None), "_is_ambiguous", False
        )
        all_results.append(
            check_ambiguous_date(
                revised_raw,
                "revised_completion_date",
                "schedule.revised_completion_date",
                is_ambiguous,
            )
        )

    # Approval date
    approval = getattr(extraction, "approval", None)
    if approval is not None:
        approval_date = _safe_value(getattr(approval, "date", None))
        if approval_date is not None:
            all_results.append(
                check_date_plausibility(approval_date, "approval_date", "approval.date")
            )

        approval_raw = _safe_raw_text(getattr(approval, "date", None))
        is_ambiguous = getattr(getattr(approval, "date", None), "_is_ambiguous", False)
        all_results.append(
            check_ambiguous_date(approval_raw, "approval_date", "approval.date", is_ambiguous)
        )

        # Approval completeness
        status = _safe_value(getattr(approval, "status", None))
        status_str = status.value if hasattr(status, "value") else str(status) if status else None
        approved_by = _safe_value(getattr(approval, "approved_by", None))
        all_results.append(check_approval_completeness(status_str, approved_by, approval_date))

    # ---- PCO vs CO ----
    if change_order is not None:
        co_number = _safe_value(getattr(change_order, "number", None))
        is_proposed = _safe_value(getattr(change_order, "is_proposed", None))
        all_results.append(check_pco_vs_co(co_number, is_proposed, source_text))

    # ---- Summarize Results ----
    report.results = all_results
    for result in all_results:
        if result.passed:
            report.passed_count += 1
        elif result.severity == "warning":
            report.warning_count += 1
        elif result.severity == "error":
            report.failed_count += 1

    if report.failed_count > 0:
        report.overall_result = ValidationResult.FAILED
    elif report.warning_count > 0:
        report.overall_result = ValidationResult.WARNING
    else:
        report.overall_result = ValidationResult.PASSED

    logger.info(
        "Validation complete: %d passed, %d warnings, %d failed",
        report.passed_count,
        report.warning_count,
        report.failed_count,
    )

    return report
