"""What every ingestion adapter must provide.

Adapters differ wildly upstream — a polled Atom feed of filings, a news
websocket — and identically downstream. Everything after ingestion is
written against `SourceEvent`, which is what lets a second source drop in
without touching resolution, classification, routing, or the eval
harness.

An adapter's only job is to normalize. It does not classify, does not
resolve tickers, and does not decide what matters.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..schema import SourceEvent


@runtime_checkable
class Source(Protocol):
    """Ingestion adapter interface.

    `kind` matches `SourceEvent.source_kind` and is what the classifier
    uses to decide whether to request filing-only detail fields.
    """

    kind: str

    def poll(self, limit: int = 20) -> list[SourceEvent]:
        """Return the most recent events, newest first.

        Implementations must be safe to call repeatedly: dedupe by
        `event_id` downstream, not here.
        """
        ...
