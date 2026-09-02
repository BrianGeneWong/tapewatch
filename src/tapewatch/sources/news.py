"""Market news ingestion.

Provider evaluation (September 2026) — see PLAN.md for the full table.
Alpaca is the choice: free with a paper account, 200 req/min, history
back to 2015, a real-time websocket stream for week 3, and a `symbols`
field on every article that makes `resolve` unnecessary for news.

The licensing constraint that shapes this module
------------------------------------------------
Every free news tier restricts redistribution, and one of them restricts
it in a way that reaches this project directly: Finnhub's personal terms
forbid sharing "data **or derived results from the data**", which would
cover a public dashboard showing classifications computed from their
headlines. Tiingo's free tier is marked internal use only. Alpaca is the
least restrictive but still expects written confirmation before a
customer-facing dashboard.

So the rule here, which is also just good design:

  - **Article text never leaves the machine that fetched it.** It is not
    committed, not published, not included in screenshots.
  - **The public demo runs on EDGAR.** SEC filings are US government
    works in the public domain — no redistribution question exists, and
    the filings corpus already works.
  - **News labels commit as derived fields plus a URL**, never article
    text: event_id, provider, url, and the label itself. A fetch script
    rehydrates the text locally for anyone re-running the eval.

This keeps the licensed corpus private and the public artifact clean,
without weakening either.

Implementation notes for whoever wires this up
----------------------------------------------
  - Headlines are short. Classification on a 12-word headline is a
    different problem from a 4,000-word filing, and the eval set needs
    both as separate strata or the accuracy number is an average over
    two populations that behave differently.
  - Wires republish. Dedupe on a normalized title plus issuer, not on
    the provider's id, or the same event alerts three times.
  - Alpaca returns `symbols` directly. Trust it and skip `resolve` — it
    is the provider's authoritative field, not a guess.
"""

from __future__ import annotations

from ..schema import SourceEvent

# https://data.alpaca.markets/v1beta1/news — key and secret from a free
# paper-trading account. No funding required.
NEWS_URL = "https://data.alpaca.markets/v1beta1/news"


class NewsClient:
    kind = "news"

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        self._api_key = api_key
        self._api_secret = api_secret

    def poll(self, limit: int = 20) -> list[SourceEvent]:
        raise NotImplementedError(
            "News ingestion is not wired yet. See PLAN.md week 1. Map each "
            "article to SourceEvent(source_kind='news', event_id=str(id), "
            "title=headline, text=content or summary, published_at=created_at) "
            "and carry `symbols` through instead of calling resolve()."
        )
