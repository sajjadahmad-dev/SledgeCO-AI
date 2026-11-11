"""
Business rule validation for extracted Change Order data.

Each rule is a pure function that takes relevant extracted data and returns
a ValidationRuleResult. Rules never modify the input data — they only
report findings.

Design principles:
- Never silently modify conflicting financial values
- Never assume deductive CO must have negative amounts
- Preserve original values and signs from the document
- Support rounding tolerances for arithmetic checks
- Flag ambiguity rather than making assumptions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Default arithmetic tolerance for floating-point comparison
ARITHMETIC_TOLERANCE = Decimal("0.05")

# Date range for plausibility check
MIN_PLAUSIBLE_DATE = date(1990, 1, 1)
MAX_PLAUSIBLE_FUTURE_YEARS = 5


@dataclass
class ValidationRuleResult:
    """Result of a single validation rule check."""

    rule_name: str
    passed: bool
    message: str
    severity: str = "error"  # "info", "warning", "error"
    field_path: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


def check_line_items_sum(
    line_item_amounts: list[Decimal | None],
    subtotal: Decimal | None,
    tolerance: Decimal = ARITHMETIC_TOLERANCE,
) -> ValidationRuleResult:
    """
    Verify: sum(line_items) ≈ subtotal.

    We use a tolerance because documents may have rounding differences.
    Returns SKIPPED if either side is missing data.
    """
    rule_name = "line_items_sum_equals_subtotal"

    if subtotal is None:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message="Subtotal not provided; skipping line items sum check.",
            severity="info",
            field_path="financials.subtotal",
        )

    valid_amounts = [a for a in line_item_amounts if a is not None]
    if not valid_amounts:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message="No line item amounts available; skipping sum check.",
            severity="info",
            field_path="financials.line_items",
        )

    computed_sum = sum(valid_amounts, Decimal("0"))
    diff = abs(computed_sum - subtotal)

    if diff <= tolerance:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message=f"Line items sum ({computed_sum}) matches subtotal ({subtotal}).",
            severity="info",
            field_path="financials.subtotal",
            details={
                "computed_sum": str(computed_sum),
                "subtotal": str(subtotal),
                "diff": str(diff),
            },
        )

    return ValidationRuleResult(
        rule_name=rule_name,
        passed=True,
        message=(
            f"Line items sum ({computed_sum}) does not match subtotal ({subtotal}). "
            f"Difference: {diff}."
        ),
        severity="error",
        field_path="financials.subtotal",
        details={"computed_sum": str(computed_sum), "subtotal": str(subtotal), "diff": str(diff)},
    )


def check_markup_calculation(
    subtotal: Decimal | None,
    markup_pct: float | None,
    markup_amount: Decimal | None,
    total: Decimal | None,
    tolerance: Decimal = ARITHMETIC_TOLERANCE,
) -> list[ValidationRuleResult]:
    """
    Verify markup-related arithmetic:
    1. subtotal * markup_pct/100 ≈ markup_amount (if both provided)
    2. subtotal + markup_amount ≈ total (if all provided)

    Returns list of results since we check multiple relationships.
    """
    results = []

    # Check 1: markup_pct * subtotal ≈ markup_amount
    if subtotal is not None and markup_pct is not None and markup_amount is not None:
        expected_markup = subtotal * Decimal(str(markup_pct)) / Decimal("100")
        diff = abs(expected_markup - markup_amount)
        results.append(
            ValidationRuleResult(
                rule_name="markup_pct_times_subtotal",
                passed=diff <= tolerance,
                message=(
                    f"Markup calculation: {subtotal} × {markup_pct}% = {expected_markup}, "
                    f"document says {markup_amount}. Diff: {diff}."
                ),
                severity="warning" if diff <= tolerance else "error",
                field_path="financials.markup_amount",
                details={
                    "expected": str(expected_markup),
                    "actual": str(markup_amount),
                    "diff": str(diff),
                },
            )
        )

    # Check 2: subtotal + markup_amount ≈ total
    if subtotal is not None and markup_amount is not None and total is not None:
        expected_total = subtotal + markup_amount
        diff = abs(expected_total - total)
        results.append(
            ValidationRuleResult(
                rule_name="subtotal_plus_markup_equals_total",
                passed=diff <= tolerance,
                message=(
                    f"Total calculation: {subtotal} + {markup_amount} = {expected_total}, "
                    f"document says {total}. Diff: {diff}."
                ),
                severity="warning" if diff <= tolerance else "error",
                field_path="financials.total",
                details={
                    "expected": str(expected_total),
                    "actual": str(total),
                    "diff": str(diff),
                },
            )
        )

    # Check 3: If no markup, subtotal should equal total
    if subtotal is not None and total is not None and markup_amount is None and markup_pct is None:
        diff = abs(subtotal - total)
        if diff > tolerance:
            results.append(
                ValidationRuleResult(
                    rule_name="subtotal_equals_total_no_markup",
                    passed=False,
                    message=(
                        f"No markup specified but subtotal ({subtotal}) != total ({total}). "
                        f"Possible missing markup or tax. Diff: {diff}."
                    ),
                    severity="warning",
                    field_path="financials.total",
                    details={"subtotal": str(subtotal), "total": str(total), "diff": str(diff)},
                )
            )

    return results


def check_contract_sum_progression(
    original_contract_sum: Decimal | None,
    net_previous_changes: Decimal | None,
    contract_sum_prior: Decimal | None,
    co_total: Decimal | None,
    new_contract_sum: Decimal | None,
    tolerance: Decimal = ARITHMETIC_TOLERANCE,
) -> list[ValidationRuleResult]:
    """
    Verify contract sum arithmetic chain:
    1. original + net_previous ≈ contract_sum_prior
    2. contract_sum_prior + co_total ≈ new_contract_sum

    Important: We do NOT assume deductive COs must have negative totals.
    The document may represent credits with positive amounts and a "deductive" label,
    or with negative amounts. We check the arithmetic as stated in the document.
    """
    results = []

    # Check 1: original + previous = prior
    if all(
        v is not None for v in [original_contract_sum, net_previous_changes, contract_sum_prior]
    ):
        expected_prior = original_contract_sum + net_previous_changes  # type: ignore
        diff = abs(expected_prior - contract_sum_prior)  # type: ignore
        results.append(
            ValidationRuleResult(
                rule_name="original_plus_previous_equals_prior",
                passed=diff <= tolerance,
                message=(
                    f"Contract sum prior: {original_contract_sum} + {net_previous_changes} = "
                    f"{expected_prior}, document says {contract_sum_prior}. Diff: {diff}."
                ),
                severity="error" if diff > tolerance else "info",
                field_path="financials.contract_sum_prior",
                details={
                    "original": str(original_contract_sum),
                    "net_previous": str(net_previous_changes),
                    "expected_prior": str(expected_prior),
                    "actual_prior": str(contract_sum_prior),
                    "diff": str(diff),
                },
            )
        )

    # Check 2: prior + CO total = new
    if all(v is not None for v in [contract_sum_prior, co_total, new_contract_sum]):
        expected_new = contract_sum_prior + co_total  # type: ignore
        diff = abs(expected_new - new_contract_sum)  # type: ignore
        results.append(
            ValidationRuleResult(
                rule_name="prior_plus_co_equals_new",
                passed=diff <= tolerance,
                message=(
                    f"New contract sum: {contract_sum_prior} + {co_total} = "
                    f"{expected_new}, document says {new_contract_sum}. Diff: {diff}."
                ),
                severity="error" if diff > tolerance else "info",
                field_path="financials.new_contract_sum",
                details={
                    "prior": str(contract_sum_prior),
                    "co_total": str(co_total),
                    "expected_new": str(expected_new),
                    "actual_new": str(new_contract_sum),
                    "diff": str(diff),
                },
            )
        )

    return results


def check_change_order_type_consistency(
    co_type: str | None,
    co_total: Decimal | None,
) -> ValidationRuleResult:
    """
    Check if the change order type is consistent with the total amount sign.

    IMPORTANT: We do NOT enforce that deductive COs must be negative.
    Different documents represent credits differently. We only FLAG inconsistencies
    as warnings for human review — never silently modify values.
    """
    rule_name = "co_type_amount_consistency"

    if co_type is None or co_total is None:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message="CO type or total not available; skipping consistency check.",
            severity="info",
        )

    co_type_lower = co_type.lower()
    is_deductive = co_type_lower in ("deductive", "deduct", "credit")
    is_negative = co_total < 0

    if is_deductive and not is_negative:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,  # Not a failure — just a warning
            message=(
                f"Change order type is '{co_type}' but total amount is positive ({co_total}). "
                f"Verify the document's sign convention."
            ),
            severity="warning",
            field_path="financials.total",
            details={"co_type": co_type, "total": str(co_total)},
        )

    if not is_deductive and is_negative:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,  # Not a failure — just a warning
            message=(
                f"Change order type is '{co_type}' but total amount is negative ({co_total}). "
                f"Verify the document's sign convention."
            ),
            severity="warning",
            field_path="financials.total",
            details={"co_type": co_type, "total": str(co_total)},
        )

    return ValidationRuleResult(
        rule_name=rule_name,
        passed=True,
        message=f"CO type '{co_type}' is consistent with total amount sign.",
        severity="info",
    )


def check_date_plausibility(
    date_value: date | None,
    field_name: str,
    field_path: str,
) -> ValidationRuleResult:
    """Check if a date is within a plausible range."""
    rule_name = f"date_plausible_{field_name}"

    if date_value is None:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message=f"{field_name}: No date provided.",
            severity="info",
            field_path=field_path,
        )

    today = date.today()
    max_future = today + timedelta(days=MAX_PLAUSIBLE_FUTURE_YEARS * 365)

    if date_value < MIN_PLAUSIBLE_DATE:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=False,
            message=f"{field_name}: Date {date_value} is before {MIN_PLAUSIBLE_DATE}.",
            severity="error",
            field_path=field_path,
        )

    if date_value > max_future:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=False,
            message=f"{field_name}: Date {date_value} is more than {MAX_PLAUSIBLE_FUTURE_YEARS} years in the future.",
            severity="warning",
            field_path=field_path,
        )

    return ValidationRuleResult(
        rule_name=rule_name,
        passed=True,
        message=f"{field_name}: Date {date_value} is plausible.",
        severity="info",
        field_path=field_path,
    )


def check_ambiguous_date(
    raw_date_text: str | None,
    field_name: str,
    field_path: str,
    is_ambiguous: bool = False,
) -> ValidationRuleResult:
    """Flag dates with ambiguous MM/DD format."""
    rule_name = f"date_ambiguous_{field_name}"

    if raw_date_text is None:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message=f"{field_name}: No date text to check.",
            severity="info",
            field_path=field_path,
        )

    if is_ambiguous:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,  # Not a failure, but a warning
            message=(
                f"{field_name}: Date '{raw_date_text}' has ambiguous month/day format. "
                f"US format (MM/DD) assumed but verify with document context."
            ),
            severity="warning",
            field_path=field_path,
            details={"raw_text": raw_date_text, "assumed_format": "US (MM/DD/YY)"},
        )

    return ValidationRuleResult(
        rule_name=rule_name,
        passed=True,
        message=f"{field_name}: Date format is unambiguous.",
        severity="info",
        field_path=field_path,
    )


def check_pco_vs_co(
    co_number: str | None,
    is_proposed: bool | None,
    document_text: str | None = None,
) -> ValidationRuleResult:
    """
    Distinguish between Proposed Change Order (PCO) and executed Change Order (CO).

    A PCO is a proposal that hasn't been formally approved. If the document
    contains "PCO" or "Proposed" but is extracted as a final CO, flag it.
    """
    rule_name = "pco_vs_co_distinction"

    if co_number is None:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message="No CO number to check for PCO/CO distinction.",
            severity="info",
        )

    # Check if the CO number itself contains PCO
    has_pco_in_number = "pco" in co_number.lower() or "proposed" in co_number.lower()

    # Check if the document mentions PCO
    has_pco_in_text = False
    if document_text:
        text_lower = document_text.lower()
        has_pco_in_text = "proposed change order" in text_lower or "pco" in text_lower

    if (has_pco_in_number or has_pco_in_text) and not is_proposed:
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message=(
                "Document may be a Proposed Change Order (PCO) but is_proposed is not set. "
                "Verify: is this a proposal or an executed change order?"
            ),
            severity="warning",
            details={
                "co_number": co_number,
                "pco_in_number": has_pco_in_number,
                "pco_in_text": has_pco_in_text,
            },
        )

    return ValidationRuleResult(
        rule_name=rule_name,
        passed=True,
        message="PCO/CO distinction appears consistent.",
        severity="info",
    )


def check_approval_completeness(
    status: str | None,
    approved_by: str | None,
    approval_date: date | None,
) -> ValidationRuleResult:
    """Check if approval information is complete when status is 'approved'."""
    rule_name = "approval_completeness"

    if status is None or status.lower() == "unknown":
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message="Approval status is missing or could not be recognized.",
            severity="warning",
            field_path="approval",
        )

    if status.lower() in ("approved", "executed"):
        missing = []
        if not approved_by:
            missing.append("approved_by")
        if not approval_date:
            missing.append("approval_date")

        if missing:
            return ValidationRuleResult(
                rule_name=rule_name,
                passed=True,
                message=(
                    f"Approval status is '{status}' but missing: {', '.join(missing)}. "
                    f"Document may be partially signed."
                ),
                severity="warning",
                field_path="approval",
                details={"status": status, "missing_fields": missing},
            )

    if status.lower() == "pending":
        return ValidationRuleResult(
            rule_name=rule_name,
            passed=True,
            message="Approval is pending; human review is required before work proceeds.",
            severity="warning",
            field_path="approval.status",
        )

    return ValidationRuleResult(
        rule_name=rule_name,
        passed=True,
        message="Approval information is consistent.",
        severity="info",
        field_path="approval",
    )
