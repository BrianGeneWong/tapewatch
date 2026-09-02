"""Polling ingestion from EDGAR — the filings adapter.

v1 is a scheduled poll of the recent-filings Atom feed. Kafka goes in
week 3, once extraction and evals are proven — see README.

SEC rules that will get you blocked if ignored:
  - A User-Agent identifying you, with contact info, on every request.
  - No more than 10 requests/second.
Both are enforced. Neither is optional.
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx2 as httpx

from ..config import SEC_RATE_LIMIT_PER_SEC, SEC_USER_AGENT
from ..htmltext import html_to_text
from ..schema import SourceEvent

ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}

RECENT_FILINGS_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type={form_type}&count={count}&output=atom"
)

# "8-K - Metallus Inc. (0001598428) (Filer)"
_TITLE_RE = re.compile(r"^(?P<form>.+?)\s+-\s+(?P<name>.+?)\s+\((?P<cik>\d{10})\)")
_ACCESSION_RE = re.compile(r"accession-number=(?P<acc>[\d-]+)")
_FILED_RE = re.compile(r"Filed:</b>\s*(?P<date>\d{4}-\d{2}-\d{2})")
_ITEM_RE = re.compile(r"Item\s+(\d+\.\d+):")


@dataclass
class FilingRef:
    accession_number: str
    cik: str
    company_name: str
    form_type: str
    filed_at: str
    source_url: str  # the filing index page
    # 8-K item numbers, e.g. ["5.02", "7.01"]. EDGAR states these
    # deterministically, so they are a free cross-check on the model's
    # event_type — see evals/README.md.
    items: list[str] = field(default_factory=list)


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
            follow_redirects=True,
        )
        self._min_interval = 1.0 / SEC_RATE_LIMIT_PER_SEC
        self._last_request = 0.0

    def _get(self, url: str) -> httpx.Response:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.monotonic()
        resp = self._client.get(url)
        resp.raise_for_status()
        return resp

    def recent(self, form_type: str = "8-K", count: int = 40) -> list[FilingRef]:
        """Return recent filings of a given form type, newest first."""
        resp = self._get(RECENT_FILINGS_URL.format(form_type=form_type, count=count))
        root = ET.fromstring(resp.content)

        refs: list[FilingRef] = []
        for entry in root.findall("a:entry", ATOM_NS):
            title = (entry.findtext("a:title", "", ATOM_NS) or "").strip()
            summary = entry.findtext("a:summary", "", ATOM_NS) or ""
            entry_id = entry.findtext("a:id", "", ATOM_NS) or ""
            link_el = entry.find("a:link", ATOM_NS)
            href = link_el.get("href", "") if link_el is not None else ""

            title_m = _TITLE_RE.match(title)
            acc_m = _ACCESSION_RE.search(entry_id)
            if not (title_m and acc_m and href):
                # Malformed entry — skip rather than fail the whole poll.
                continue

            filed_m = _FILED_RE.search(summary)
            refs.append(
                FilingRef(
                    accession_number=acc_m.group("acc"),
                    cik=title_m.group("cik"),
                    company_name=title_m.group("name").strip(),
                    form_type=title_m.group("form").strip(),
                    filed_at=filed_m.group("date") if filed_m else "",
                    source_url=href,
                    items=_ITEM_RE.findall(summary),
                )
            )
        return refs

    def _primary_document_url(self, ref: FilingRef) -> str:
        """Find the filing's primary document from its index page.

        The index page lists every document with a Type column; the
        primary one carries the form type itself (e.g. "8-K"), with
        exhibits as EX-*. Picking by Type is deterministic — filename
        conventions are not.
        """
        html = self._get(ref.source_url).text
        table_m = re.search(r'<table[^>]*class="tableFile".*?</table>', html, re.S)
        if not table_m:
            raise ValueError(f"no document table on index page for {ref.accession_number}")

        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_m.group(0), re.S):
            cells = [
                re.sub(r"<[^>]+>", "", c).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
            ]
            # Columns: Seq | Description | Document | Type | Size
            if len(cells) < 4 or cells[3] != ref.form_type:
                continue
            href_m = re.search(r'href="([^"]+)"', row)
            if not href_m:
                continue
            href = href_m.group(1)
            # iXBRL documents are linked through a viewer; the raw file
            # is the doc parameter.
            if href.startswith("/ix?doc="):
                href = href[len("/ix?doc="):]
            return urljoin("https://www.sec.gov", href)

        raise ValueError(
            f"no document of type {ref.form_type} in {ref.accession_number}"
        )

    def document_text(self, ref: FilingRef) -> str:
        """Fetch the filing's primary document and return it as plain text."""
        return html_to_text(self._get(self._primary_document_url(ref)).text)


    # --- adapter interface --------------------------------------------

    kind = "edgar"

    def poll(self, limit: int = 20) -> list[SourceEvent]:
        """Fetch recent filings and normalize them into SourceEvents.

        Document text is fetched here rather than lazily because the
        classifier needs it and SEC rate limits make a second pass
        expensive. A filing that fails to fetch is skipped, not raised —
        one malformed document must not end a poll.
        """
        events: list[SourceEvent] = []
        for ref in self.recent(count=limit):
            try:
                text = self.document_text(ref)
            except Exception:
                continue
            events.append(to_source_event(ref, text))
        return events


def to_source_event(ref: FilingRef, text: str) -> SourceEvent:
    """Normalize a filing into the envelope the rest of the pipeline sees."""
    return SourceEvent(
        event_id=ref.accession_number,
        source_kind="edgar",
        published_at=ref.filed_at,
        source_url=ref.source_url,
        title=f"{ref.form_type} — {ref.company_name}",
        text=text,
        issuer_name=ref.company_name,
        cik=ref.cik,
        items=ref.items,
    )
