from __future__ import annotations

from enum import StrEnum


class ChangeOrderType(StrEnum):
    ADDITIVE = "additive"
    DEDUCTIVE = "deductive"
    ZERO_COST = "zero_cost"
    UNKNOWN = "unknown"


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class ValidationResult(StrEnum):
    NOT_CHECKED = "not_checked"
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class RoutingDecision(StrEnum):
    READY_FOR_REVIEW = "ready_for_review"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
