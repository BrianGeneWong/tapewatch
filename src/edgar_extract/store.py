"""Output storage.

v1 writes newline-delimited JSON to the local filesystem, partitioned by
filing date. That is deliberately boring — it is trivially inspectable
while you are still getting extraction right, and swapping it for S3 is a
one-function change once the pipeline works.

TODO(week 3): S3 backend behind the same two functions.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR
from .schema import ExtractionRecord


def write(record: ExtractionRecord) -> Path:
    day = record.filed_at[:10]
    out_dir = Path(DATA_DIR) / "extractions" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "records.jsonl"
    with path.open("a") as f:
        f.write(record.model_dump_json() + "\n")
    return path


def read_all() -> list[ExtractionRecord]:
    root = Path(DATA_DIR) / "extractions"
    if not root.exists():
        return []
    records = []
    for path in sorted(root.glob("*/records.jsonl")):
        with path.open() as f:
            records.extend(
                ExtractionRecord.model_validate(json.loads(line)) for line in f if line.strip()
            )
    return records
