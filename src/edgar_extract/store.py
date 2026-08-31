"""Storage: cached filing documents (week 1) and extractions (week 2).

Documents are cached locally on fetch so extraction can be re-run without
re-hitting SEC. That matters twice over: it keeps you well inside SEC's
rate limits while you iterate, and it makes eval runs reproducible —
scoring against a moving corpus tells you nothing.

v1 is the local filesystem. Swapping in S3 is a change to these
functions and nothing else.

TODO(week 3): S3 backend behind this same interface.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import DATA_DIR
from .fetch import FilingRef
from .schema import ExtractionRecord

_DOCS = Path(DATA_DIR) / "documents"
_EXTRACTIONS = Path(DATA_DIR) / "extractions"


# --- filing documents -------------------------------------------------


def write_document(ref: FilingRef, text: str) -> Path:
    _DOCS.mkdir(parents=True, exist_ok=True)
    (_DOCS / f"{ref.accession_number}.txt").write_text(text)
    path = _DOCS / "refs.jsonl"
    existing = {r.accession_number for r in read_refs()}
    if ref.accession_number not in existing:
        with path.open("a") as f:
            f.write(json.dumps(asdict(ref)) + "\n")
    return _DOCS / f"{ref.accession_number}.txt"


def read_refs() -> list[FilingRef]:
    path = _DOCS / "refs.jsonl"
    if not path.exists():
        return []
    with path.open() as f:
        return [FilingRef(**json.loads(line)) for line in f if line.strip()]


def read_document(accession_number: str) -> str:
    return (_DOCS / f"{accession_number}.txt").read_text()


def has_document(accession_number: str) -> bool:
    return (_DOCS / f"{accession_number}.txt").exists()


# --- extractions ------------------------------------------------------


def write(record: ExtractionRecord) -> Path:
    day = record.filed_at[:10] or "unknown"
    out_dir = _EXTRACTIONS / day
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "records.jsonl"
    with path.open("a") as f:
        f.write(record.model_dump_json() + "\n")
    return path


def read_all() -> list[ExtractionRecord]:
    if not _EXTRACTIONS.exists():
        return []
    records = []
    for path in sorted(_EXTRACTIONS.glob("*/records.jsonl")):
        with path.open() as f:
            records.extend(
                ExtractionRecord.model_validate(json.loads(line))
                for line in f
                if line.strip()
            )
    return records
