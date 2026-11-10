from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CalibrationMetrics:
    ece: float
    brier_score: float
    sample_count: int
    split_sizes: dict[str, int]
    reliability_bins: list[dict[str, float | int]]
    calibrated_method: str = "heuristic"
    calibrated_ece: float | None = None
    calibrated_brier_score: float | None = None
    logistic_ece: float | None = None
    logistic_brier_score: float | None = None


def _expected_calibration_error(scores: Sequence[float], labels: Sequence[int]) -> float:
    total = 0.0
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        selected = [
            (score, label)
            for score, label in zip(scores, labels, strict=True)
            if lower <= score < lower + 0.2
        ]
        if selected:
            confidence = sum(score for score, _ in selected) / len(selected)
            accuracy = sum(label for _, label in selected) / len(selected)
            total += abs(confidence - accuracy) * len(selected)
    return total / len(scores)


def evaluate_calibration(
    scores: Sequence[float],
    labels: Sequence[bool],
    *,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> CalibrationMetrics | None:
    if len(scores) != len(labels):
        raise ValueError("Confidence scores and labels must have equal lengths")
    if len(scores) < 30:
        return None
    indices = list(range(len(scores)))
    random.Random(0).shuffle(indices)
    shuffled_scores = [scores[index] for index in indices]
    shuffled_labels = [labels[index] for index in indices]
    split_train = int(len(scores) * train_fraction)
    split_validation = split_train + int(len(scores) * validation_fraction)
    test_scores = list(shuffled_scores[split_validation:])
    test_labels = [int(label) for label in shuffled_labels[split_validation:]]
    if not test_scores:
        return None
    bins: list[dict[str, float | int]] = []
    for lower in (0.0, 0.2, 0.4, 0.6, 0.8):
        selected = [
            (score, label)
            for score, label in zip(test_scores, test_labels, strict=True)
            if lower <= score < lower + 0.2
        ]
        if selected:
            confidence = sum(score for score, _ in selected) / len(selected)
            accuracy = sum(label for _, label in selected) / len(selected)
            bins.append(
                {
                    "lower": lower,
                    "upper": lower + 0.2,
                    "mean_confidence": confidence,
                    "empirical_accuracy": accuracy,
                    "count": len(selected),
                }
            )
    ece = sum(
        abs(float(item["mean_confidence"]) - float(item["empirical_accuracy"])) * int(item["count"])
        for item in bins
    ) / len(test_scores)
    brier = sum((score - label) ** 2 for score, label in zip(test_scores, test_labels, strict=True)) / len(test_scores)
    metrics = CalibrationMetrics(
        ece=ece,
        brier_score=brier,
        sample_count=len(test_scores),
        split_sizes={
            "train": split_train,
            "validation": split_validation - split_train,
            "test": len(test_scores),
        },
        reliability_bins=bins,
    )
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import brier_score_loss

        train_scores = [[score] for score in shuffled_scores[:split_train]]
        train_labels = [int(label) for label in shuffled_labels[:split_train]]
        validation_scores = [[score] for score in shuffled_scores[split_train:split_validation]]
        validation_labels = [int(label) for label in shuffled_labels[split_train:split_validation]]
        if len(set(train_labels)) == 2 and validation_scores:
            model = LogisticRegression(random_state=0)
            model.fit(train_scores, train_labels)
            validation_predictions = model.predict_proba(validation_scores)[:, 1]
            validation_brier = brier_score_loss(validation_labels, validation_predictions)
            test_predictions = model.predict_proba([[score] for score in test_scores])[:, 1]
            calibrated_brier = brier_score_loss(test_labels, test_predictions)
            calibrated_ece = _expected_calibration_error(test_predictions, test_labels)
            metrics = CalibrationMetrics(
                **{
                    **metrics.__dict__,
                    "calibrated_method": (
                        "logistic_regression" if validation_brier <= brier else "heuristic"
                    ),
                    "calibrated_ece": calibrated_ece,
                    "calibrated_brier_score": calibrated_brier,
                    "logistic_ece": calibrated_ece,
                    "logistic_brier_score": calibrated_brier,
                }
            )
    except ImportError:
        pass
    return metrics
