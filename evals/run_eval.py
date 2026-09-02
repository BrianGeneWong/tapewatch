"""Score extractions against hand-labeled ground truth.

Usage: python evals/run_eval.py
"""

from __future__ import annotations

import json
from pathlib import Path

from tapewatch.schema import Classification

LABELS = Path(__file__).parent / "labels"


def party_f1(predicted: Classification, truth: Classification) -> float:
    pred_parties = predicted.detail.parties if predicted.detail else []
    gold_parties = truth.detail.parties if truth.detail else []
    pred = {(p.name.strip().lower(), p.role) for p in pred_parties}
    gold = {(p.name.strip().lower(), p.role) for p in gold_parties}
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    if tp == 0:
        return 0.0
    precision, recall = tp / len(pred), tp / len(gold)
    return 2 * precision * recall / (precision + recall)


def amounts_match(
    predicted: Classification, truth: Classification, tol: float = 0.01
) -> float:
    gold_amounts = truth.detail.amounts if truth.detail else []
    pred_amounts = predicted.detail.amounts if predicted.detail else []
    gold = [a.value_usd for a in gold_amounts if a.value_usd is not None]
    pred = [a.value_usd for a in pred_amounts if a.value_usd is not None]
    if not gold and not pred:
        return 1.0
    if not gold or not pred:
        return 0.0
    hits = sum(
        1 for g in gold if any(abs(p - g) <= tol * max(abs(g), 1.0) for p in pred)
    )
    return hits / len(gold)


def materiality_mae(predicted: Classification, truth: Classification) -> float:
    """Mean absolute error on the 0-100 materiality score.

    Reported separately from event_type accuracy on purpose. A model can
    name the category correctly and still be useless at ranking what
    deserves a human's attention, and one blended score hides exactly
    that failure.
    """
    return float(abs(predicted.materiality - truth.materiality))


def event_type_correct(predicted: Classification, truth: Classification) -> bool:
    return predicted.event_type == truth.event_type


def main() -> None:
    # TODO(week 2): load records from data/records keyed by event_id,
    # pair each with its label file, and report per-field numbers plus
    # macro-F1 over event_type. Score each baseline and each routing
    # policy separately — the comparison is the whole point.
    labels = sorted(LABELS.glob("*.json"))
    if not labels:
        raise SystemExit(
            f"No label files in {LABELS}. See evals/README.md — hand-label "
            "200 events before running this."
        )
    for path in labels:
        truth = Classification.model_validate(json.loads(path.read_text()))
        print(f"{path.stem}: loaded ground truth ({truth.event_type.value})")
    raise NotImplementedError("pair labels with predictions and aggregate")


if __name__ == "__main__":
    main()
