"""Market news ingestion.

Deliberately a stub with a working shape. Fill in against whichever
provider survives the day-one free-tier check — the rest of the pipeline
does not care which, because it only ever sees `SourceEvent`.

What matters when you wire a real provider:

  - Headlines are short. Classification quality on a 12-word headline is
    a different problem from a 4,000-word filing, and the eval set needs
    both or the accuracy number is an average over two populations that
    behave differently. Label them as separate strata.
  - Wires republish. Dedupe on a normalized title plus issuer, not on the
    provider's id, or the same event alerts three times.
  - Most providers give a ticker directly. When they do, trust it and
    skip `resolve` — it is the provider's authoritative field, not a
    guess.
"""

from __future__ import annotations

from ..schema import SourceEvent


class NewsClient:
    kind = "news"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def poll(self, limit: int = 20) -> list[SourceEvent]:
        raise NotImplementedError(
            "News ingestion is not wired yet. See PLAN.md week 1: verify a "
            "provider's free tier, then return SourceEvent(source_kind='news')."
        )
