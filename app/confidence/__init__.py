"""Confidence module: multi-signal confidence scoring and optional calibration."""
from app.confidence.calibration import CalibrationMetrics, evaluate_calibration

__all__ = ["CalibrationMetrics", "evaluate_calibration"]
