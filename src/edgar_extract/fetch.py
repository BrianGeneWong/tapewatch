"""Polling ingestion from EDGAR.

v1 is a scheduled poll of the recent-filings Atom feed. Kafka goes in
week 3, once extraction and evals are proven — see README.

SEC rules that will get you blocked if ignored:
  - A User-Agent identifying you, with contact info, on every request.
  - No more than 10 requests/second.
Both are enforced. Neither is optional.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx2 as httpx

from .config import SEC_RATE_LIMIT_PER_SEC, SEC_USER_AGENT

RECENT_FILINGS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type={form_type}&count={count}&output=atom"
)


@dataclass
class FilingRef:
    accession_number: str
    cik: str
    company_name: str
    form_type: str
    filed_at: str
    source_url: str


class EdgarClient:
    def __init__(self, user_agent: str | None = None):
        ua = user_agent or SEC_USER_AGENT
        if not ua:
            raise RuntimeError(
                "SEC_USER_AGENT is required. Set it in .env — SEC blocks "
                "requests without a contact-identifying User-Agent."
            )
        self._client = httpx.Client(
            headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"},
            timeout=30.0,
        )
        self._min_interval = 1.0 / SEC_RATE_LIMIT_PER_SEC
        self._last_request = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()

    def recent(self, form_type: str = "8-K", count: int = 40) -> list[FilingRef]:
        """Return recent filings of a given form type.

        TODO(week 1): parse the Atom response into FilingRef records.
        The feed gives accession number, CIK, company name, and a link
        to the filing index. Prefer xml.etree over adding a dependency.
        """
        self._throttle()
        resp = self._client.get(
            RECENT_FILINGS_URL.format(form_type=form_type, count=count)
        )
        resp.raise_for_status()
        raise NotImplementedError("parse the Atom feed into FilingRef records")

    def document_text(self, ref: FilingRef) -> str:
        """Fetch the primary document for a filing and return its text.

        TODO(week 1): 8-K primary documents are HTML. Strip tags to plain
        text before sending to the model — markup burns input tokens and
        measurably hurts extraction quality. Keep the text; the LLM step
        should never see raw HTML.
        """
        self._throttle()
        raise NotImplementedError("fetch and de-HTML the primary document")
