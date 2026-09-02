"""Storage: cached source documents and classified records.

Documents are cached locally on ingest so classification can be re-run
without re-hitting the source. That matters twice over: it keeps you well
inside SEC's rate limits while you iterate, and it makes eval runs
reproducible — scoring against a moving corpus tells you nothing.

It is also what makes the pipeline replayable. Week 3 puts Kafka between
ingestion and classification; the cached corpus is what you replay
through it so the whole system can be demonstrated outside market hours.

v1 is the local filesystem. Swapping in S3 is a change to these
functions and nothing else.

TODO(week 3): S3 backend behind this same interface.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR
from .schema import EventRecord, SourceEvent

_DOCS = Path(DATA_DIR) / "documents"
_RECORDS = Path(DATA_DIR) / "records"


# --- source documents -------------------------------------------------


def write_event(event: SourceEvent) -> Path:
    """Cache one source event. Idempotent on event_id."""
    _DOCS.mkdir(parents=True, exist_ok=True)
    path = _DOCS / f"{event.event_id}.json"
    path.write_text(event.model_dump_json(indent=2))
    return path


def read_events() -> list[SourceEvent]:
    if not _DOCS.exists():
        return []
    out = []
    for path in sorted(_DOCS.glob("*.json")):
        out.append(SourceEvent.model_validate_json(path.read_text()))
    return out


def read_event(event_id: str) -> SourceEvent:
    return SourceEvent.model_validate_json((_DOCS / f"{event_id}.json").read_text())


def has_event(event_id: str) -> bool:
    return (_DOCS / f"{event_id}.json").exists()


# --- classified records -----------------------------------------------


def write(record: EventRecord) -> Path:
    day = record.event.published_at[:10] or "unknown"
    out_dir = _RECORDS / day
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "records.jsonl"
    with path.open("a") as f:
        f.write(record.model_dump_json() + "\n")
    return path


def read_all() -> list[EventRecord]:
    if not _RECORDS.exists():
        return []
    records = []
    for path in sorted(_RECORDS.glob("*/records.jsonl")):
        with path.open() as f:
            records.extend(
                EventRecord.model_validate(json.loads(line))
                for line in f
                if line.strip()
            )
    return records
