from __future__ import annotations

from app.schemas.enums import RoutingDecision, ValidationResult


def route_extraction(
    validation_result: ValidationResult,
    confidence_score: float,
    low_confidence_fields: int,
) -> RoutingDecision:
    if validation_result == ValidationResult.FAILED or confidence_score < 0.35:
        return RoutingDecision.BLOCKED
    if (
        validation_result == ValidationResult.WARNING
        or low_confidence_fields > 0
        or confidence_score < 0.75
    ):
        return RoutingDecision.NEEDS_REVIEW
    return RoutingDecision.READY_FOR_REVIEW
