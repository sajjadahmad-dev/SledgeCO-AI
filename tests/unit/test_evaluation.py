from __future__ import annotations

import pytest

from eval.run_eval import run_evaluation


def test_evaluation_fails_for_empty_dataset(tmp_path):
    (tmp_path / "documents").mkdir()
    (tmp_path / "labels").mkdir()
    with pytest.raises(ValueError, match="dataset is empty"):
        run_evaluation(tmp_path, tmp_path / "results")


def test_evaluation_fails_for_missing_ground_truth(tmp_path):
    documents = tmp_path / "documents"
    labels = tmp_path / "labels"
    documents.mkdir()
    labels.mkdir()
    (documents / "co_001.txt").write_text("Project: Example", encoding="utf-8")
    with pytest.raises(ValueError, match="Missing ground-truth"):
        run_evaluation(tmp_path, tmp_path / "results")
