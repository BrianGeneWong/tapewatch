"""Market news ingestion, via Alpaca.

Provider evaluation (September 2026) — see PLAN.md for the full table.
Alpaca is the choice: free with a paper trading account, 200 req/min,
history back to 2015, a real-time websocket stream for week 3, and a
`symbols` field on every article that makes `resolve` unnecessary here.

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
    works in the public domain — no redistribution question exists.
  - **News labels commit as derived fields plus a URL**, never article
    text. A fetch script rehydrates the text locally.

Note on freshness: without a real-time data subscription the window
defaults to 15 minutes behind live. That is invisible to the eval work
and matters only when week 3 wires the websocket stream.
"""

from __future__ import annotations

import httpx2 as httpx

from ..config import ALPACA_API_KEY, ALPACA_API_SECRET
from ..htmltext import html_to_text
from ..schema import SourceEvent

NEWS_URL = "https://data.alpaca.markets/v1beta1/news"

# The API caps a page at 50 regardless of what you ask for.
MAX_PAGE = 50


class NewsClient:
    kind = "news"

    def __init__(self, api_key: str | None = None, api_secret: str | None = None):
        key = api_key or ALPACA_API_KEY
        secret = api_secret or ALPACA_API_SECRET
        if not (key and secret):
            raise RuntimeError(
                "ALPACA_API_KEY and ALPACA_API_SECRET are required. Generate a "
                "key pair from the Alpaca dashboard with Paper Trading selected "
                "and put them in .env."
            )
        # Full URL per request rather than base_url: joining an empty
        # path onto a base_url yields "/news/", and the trailing slash
        # 404s.
        self._client = httpx.Client(
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret},
            timeout=30.0,
            follow_redirects=True,
        )

    def poll(
        self,
        limit: int = 20,
        symbols: list[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> list[SourceEvent]:
        """Return the most recent articles, newest first.

        Paginates until `limit` is satisfied. `symbols` narrows to a set
        of tickers, which is how you build an eval corpus for the book
        without pulling the whole wire.
        """
        params: dict[str, str | int | bool] = {
            "limit": min(limit, MAX_PAGE),
            "sort": "desc",
            "include_content": True,
            # An article with no body is a headline stub — it cannot be
            # classified with evidence, so it is not worth a model call.
            "exclude_contentless": True,
        }
        if symbols:
            params["symbols"] = ",".join(s.upper() for s in symbols)
        if start:
            params["start"] = start
        if end:
            params["end"] = end

        events: list[SourceEvent] = []
        token: str | None = None
        while len(events) < limit:
            if token:
                params["page_token"] = token
            resp = self._client.get(NEWS_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()

            for article in payload.get("news", []):
                event = to_source_event(article)
                if event is not None:
                    events.append(event)

            token = payload.get("next_page_token")
            if not token:
                break

        return events[:limit]


def to_source_event(article: dict) -> SourceEvent | None:
    """Normalize one Alpaca article into the envelope.

    Returns None for an article with no usable body. Content arrives as
    HTML and is reduced with the same de-HTMLer the filings path uses, so
    both sources reach the classifier as plain text.
    """
    body = article.get("content") or article.get("summary") or ""
    text = html_to_text(body) if body else ""
    if not text.strip():
        return None

    return SourceEvent(
        event_id=str(article["id"]),
        source_kind="news",
        published_at=article.get("created_at", ""),
        source_url=article.get("url") or "",
        title=article.get("headline", ""),
        text=text,
        # The wire names the issuer in the headline, not as a legal
        # entity, so issuer_name stays empty — provider_symbols is the
        # authoritative link to the book.
        provider_symbols=list(article.get("symbols") or []),
    )
