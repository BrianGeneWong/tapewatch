"""Score extractions against hand-labeled ground truth.

Usage: python evals/run_eval.py
"""

from __future__ import annotations

import json
from pathlib import Path

from edgar_extract.schema import FilingExtraction

LABELS = Path(__file__).parent / "labels"


def party_f1(predicted: FilingExtraction, truth: FilingExtraction) -> float:
    pred = {(p.name.strip().lower(), p.role) for p in predicted.parties}
    gold = {(p.name.strip().lower(), p.role) for p in truth.parties}
    if not pred and not gold:
        return 1.0
    if not pred or not gold:
        return 0.0
    tp = len(pred & gold)
    if tp == 0:
        return 0.0
    precision, recall = tp / len(pred), tp / len(gold)
    return 2 * precision * recall / (precision + recall)


def amounts_match(predicted: FilingExtraction, truth: FilingExtraction, tol: float = 0.01) -> float:
    gold = [a.value_usd for a in truth.amounts if a.value_usd is not None]
    pred = [a.value_usd for a in predicted.amounts if a.value_usd is not None]
    if not gold and not pred:
        return 1.0
    if not gold or not pred:
        return 0.0
    hits = sum(
        1 for g in gold if any(abs(p - g) <= tol * max(abs(g), 1.0) for p in pred)
    )
    return hits / len(gold)


def main() -> None:
    # TODO(week 3): load predictions from data/ keyed by accession number,
    # pair each with its label file, and average the metrics below.
    labels = sorted(LABELS.glob("*.json"))
    if not labels:
        raise SystemExit(
            f"No label files in {LABELS}. See evals/README.md — hand-label "
            "50-100 filings before running this."
        )
    for path in labels:
        truth = FilingExtraction.model_validate(json.loads(path.read_text()))
        print(f"{path.stem}: loaded ground truth ({truth.event_type.value})")
    raise NotImplementedError("pair labels with predictions and aggregate")


if __name__ == "__main__":
    main()
