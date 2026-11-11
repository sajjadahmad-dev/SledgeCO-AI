"""
Multi-signal confidence scoring for extracted Change Order fields.

Design principles:
- Transparent: each signal is independently computed and visible
- Weighted: initial scoring uses interpretable weighted averages
- Calibratable: when sufficient labeled data exists, fit a logistic
  regression model to produce calibrated probabilities
- Honest: never claim higher confidence than evidence supports

Signals:
1. evidence_match   — fuzzy match of evidence quote in source text
2. format_validity  — does the value match expected format patterns?
3. arithmetic_check — did related validation rules pass?
4. scan_quality     — text density / quality indicator for the page
5. ambiguity_flag   — any ambiguity detected (date format, sign, etc.)?
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.extraction.normalizer import normalize_amount

logger = logging.getLogger(__name__)

__all__ = ["ConfidenceScorer", "FieldConfidence", "DocumentConfidence"]


# Default weights for weighted average scoring
# These are interpretable starting points, not trained values
DEFAULT_WEIGHTS = {
    "evidence_match": 0.30,
    "format_validity": 0.15,
    "arithmetic_check": 0.25,
    "scan_quality": 0.10,
    "ambiguity_penalty": 0.20,
}


@dataclass
class FieldConfidence:
    """Confidence breakdown for a single extracted field."""

    field_path: str
    overall_score: float = 0.0

    # Individual signal scores (0.0 to 1.0)
    evidence_match: float = 0.0
    format_validity: float = 1.0  # assume valid unless proven otherwise
    arithmetic_check: float = 1.0  # assume passed unless related rule failed
    scan_quality: float = 1.0  # assume good unless scan detected
    ambiguity_penalty: float = 0.0  # 0 = no ambiguity, 1 = ambiguous

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_path": self.field_path,
            "overall_score": round(self.overall_score, 4),
            "signals": {
                "evidence_match": round(self.evidence_match, 4),
                "format_validity": round(self.format_validity, 4),
                "arithmetic_check": round(self.arithmetic_check, 4),
                "scan_quality": round(self.scan_quality, 4),
                "ambiguity_penalty": round(self.ambiguity_penalty, 4),
            },
        }


@dataclass
class DocumentConfidence:
    """Confidence summary for the entire document extraction."""

    overall_score: float = 0.0
    field_scores: list[FieldConfidence] = field(default_factory=list)
    min_field_score: float = 0.0
    max_field_score: float = 0.0
    mean_field_score: float = 0.0
    num_low_confidence_fields: int = 0
    low_confidence_threshold: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 4),
            "min_field_score": round(self.min_field_score, 4),
            "max_field_score": round(self.max_field_score, 4),
            "mean_field_score": round(self.mean_field_score, 4),
            "num_low_confidence_fields": self.num_low_confidence_fields,
            "field_scores": [f.to_dict() for f in self.field_scores],
        }


class ConfidenceScorer:
    """
    Computes confidence scores for extracted fields using weighted signals.

    Phase 1: Transparent weighted average with interpretable weights.
    Phase 2 (future): LogisticRegression calibration when sufficient
    labeled data is available.
    """

    def __init__(self, weights: dict[str, float] | None = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        # Normalize weights to sum to 1.0
        total = sum(self.weights.values())
        if total > 0:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def score_field(
        self,
        field_path: str,
        evidence_quote: str | None = None,
        source_text: str | None = None,
        value: Any = None,
        expected_format: str | None = None,
        validation_passed: bool | None = None,
        is_scanned: bool = False,
        has_ambiguity: bool = False,
    ) -> FieldConfidence:
        """
        Compute confidence for a single field.

        Args:
            field_path: Dotted path to the field (e.g., "financials.total")
            evidence_quote: The evidence quote from extraction
            source_text: The source document text to match against
            value: The extracted value
            expected_format: Optional regex/format hint for validation
            validation_passed: Result of related validation rule
            is_scanned: Whether the page was scanned (affects quality signal)
            has_ambiguity: Whether any ambiguity was detected
        """
        fc = FieldConfidence(field_path=field_path)

        # Signal 1: Evidence match
        fc.evidence_match = self._compute_evidence_match(evidence_quote, source_text, value)

        # Signal 2: Format validity
        fc.format_validity = self._compute_format_validity(value, expected_format)

        # Signal 3: Arithmetic check
        if value is None:
            fc.arithmetic_check = 0.0
        elif validation_passed is not None:
            fc.arithmetic_check = 1.0 if validation_passed else 0.0
        else:
            fc.arithmetic_check = 0.5  # Unknown → neutral

        # Signal 4: Scan quality
        fc.scan_quality = 0.7 if is_scanned else 1.0

        # Signal 5: Ambiguity
        fc.ambiguity_penalty = 1.0 if has_ambiguity else 0.0

        # Compute weighted score
        fc.overall_score = self._weighted_score(fc)
        if value is None:
            fc.overall_score = min(fc.overall_score, 0.25)
        elif fc.evidence_match == 0.0:
            fc.overall_score = min(fc.overall_score, 0.4)

        return fc

    def score_document(
        self,
        field_scores: list[FieldConfidence],
        low_confidence_threshold: float = 0.7,
    ) -> DocumentConfidence:
        """
        Aggregate field-level scores into a document-level confidence.

        The overall document score is the minimum of:
        - Mean field confidence (average quality)
        - Adjusted score penalizing low-confidence fields
        """
        dc = DocumentConfidence(
            field_scores=field_scores,
            low_confidence_threshold=low_confidence_threshold,
        )

        if not field_scores:
            return dc

        scores = [f.overall_score for f in field_scores]
        dc.min_field_score = min(scores)
        dc.max_field_score = max(scores)
        dc.mean_field_score = sum(scores) / len(scores)
        dc.num_low_confidence_fields = sum(1 for s in scores if s < low_confidence_threshold)

        # Document score: weighted combination of mean and min
        # A single very low field pulls overall score down
        dc.overall_score = 0.7 * dc.mean_field_score + 0.3 * dc.min_field_score

        # Penalty for many low-confidence fields
        if dc.num_low_confidence_fields > 0:
            penalty = min(dc.num_low_confidence_fields * 0.05, 0.3)
            dc.overall_score = max(0.0, dc.overall_score - penalty)

        logger.info(
            "Document confidence: %.3f (mean=%.3f, min=%.3f, low_fields=%d)",
            dc.overall_score,
            dc.mean_field_score,
            dc.min_field_score,
            dc.num_low_confidence_fields,
        )

        return dc

    def _compute_evidence_match(
        self, evidence_quote: str | None, source_text: str | None, value: Any = None
    ) -> float:
        """
        Compute fuzzy match score between evidence quote and source text.
        Uses rapidfuzz for efficient fuzzy string matching.
        """
        if value is None or not evidence_quote or not source_text:
            return 0.0

        value_text = str(value).strip()
        if not value_text:
            return 0.0
        quote_folded = evidence_quote.casefold().strip()
        value_folded = value_text.casefold()
        numeric_value = normalize_amount(value_text)
        numeric_matches = False
        if numeric_value is not None:
            numeric_matches = any(
                candidate in evidence_quote
                for candidate in {format(numeric_value, "f"), f"{numeric_value:,.2f}"}
            )
        if not numeric_matches and value_folded in quote_folded and quote_folded != value_folded:
            prefix = quote_folded.rsplit(value_folded, 1)[0].rstrip()
            if prefix and prefix[-1].isalnum():
                return 0.0
        try:
            from rapidfuzz import fuzz

            # The quote must contain the extracted value; matching a label alone
            # is not evidence for the value.
            if not numeric_matches:
                score = fuzz.partial_ratio(value_text.lower(), evidence_quote.lower())
            else:
                score = 100
            if score < 90:
                return 0.0
            score = fuzz.partial_ratio(evidence_quote.lower(), source_text.lower())
            return score / 100.0  # Normalize to 0-1
        except ImportError:
            # Fallback: simple substring check
            if value_text.lower() in evidence_quote.lower() and evidence_quote.lower() in source_text.lower():
                return 1.0
            return 0.0

    def _compute_format_validity(self, value: Any, expected_format: str | None) -> float:
        """Check if the value matches expected format patterns."""
        if value is None:
            return 0.5  # No value → neutral

        if expected_format is None:
            return 1.0  # No format expectation → assume valid

        import re

        try:
            if re.match(expected_format, str(value)):
                return 1.0
            return 0.3  # Format mismatch but value exists
        except re.error:
            return 0.5  # Invalid regex → neutral

    def _weighted_score(self, fc: FieldConfidence) -> float:
        """Compute the weighted average score from individual signals."""
        score = (
            self.weights.get("evidence_match", 0) * fc.evidence_match
            + self.weights.get("format_validity", 0) * fc.format_validity
            + self.weights.get("arithmetic_check", 0) * fc.arithmetic_check
            + self.weights.get("scan_quality", 0) * fc.scan_quality
            + self.weights.get("ambiguity_penalty", 0) * (1.0 - fc.ambiguity_penalty)
        )
        return max(0.0, min(1.0, score))  # Clamp to [0, 1]
