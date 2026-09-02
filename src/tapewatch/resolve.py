"""Map an issuer to its ticker(s). Deterministic, no model involved.

This is the stage that connects an event to a book of positions, and it
is exactly the kind of work that must not go to a language model: the
answer is published, authoritative, and free. SEC maintains the full
CIK-to-ticker mapping at company_tickers.json.

The model is consulted here for one narrow case and no other — a news
item that names an issuer in prose with no ticker and no CIK, where the
name does not match the SEC index exactly. That path is off by default;
turn it on and measure it before trusting it.

Resolution failures are a pipeline metric, not a prompt problem. An
unresolvable event is dropped with a counter incremented, never passed
downstream with a guessed ticker.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import httpx2 as httpx

from .config import DATA_DIR, SEC_USER_AGENT

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_CACHE = Path(DATA_DIR) / "reference" / "company_tickers.json"

# Suffixes that differ between EDGAR's legal names and how news wires
# write them. Stripped on both sides before comparing.
_SUFFIXES = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|llc|lp|plc|ltd|limited|"
    r"holdings?|group|nv|sa|ag)\b\.?",
    re.I,
)
_PUNCT = re.compile(r"[^\w\s]")


def _normalize_name(name: str) -> str:
    name = _PUNCT.sub(" ", name)
    name = _SUFFIXES.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


def refresh_cache() -> Path:
    """Download the SEC ticker index. Run once, then it is a local file."""
    if not SEC_USER_AGENT:
        raise RuntimeError(
            "SEC_USER_AGENT is required. Set it in .env — SEC blocks "
            "requests without a contact-identifying User-Agent."
        )
    resp = httpx.get(
        COMPANY_TICKERS_URL,
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=30.0,
        follow_redirects=True,
    )
    resp.raise_for_status()
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(resp.text)
    return _CACHE


@lru_cache(maxsize=1)
def _index() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (cik -> tickers, normalized name -> tickers)."""
    if not _CACHE.exists():
        refresh_cache()
    raw = json.loads(_CACHE.read_text())

    by_cik: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for row in raw.values():
        ticker = str(row["ticker"]).strip().upper()
        cik = str(row["cik_str"]).zfill(10)
        by_cik.setdefault(cik, []).append(ticker)
        by_name.setdefault(_normalize_name(str(row["title"])), []).append(ticker)
    return by_cik, by_name


def by_cik(cik: str) -> list[str]:
    """Exact CIK lookup. The authoritative path — use it whenever a CIK
    is available, which for anything sourced from EDGAR is always."""
    return _index()[0].get(str(cik).zfill(10), [])


def by_name(issuer_name: str) -> list[str]:
    """Exact match on a normalized legal name.

    Deliberately not fuzzy. A near-miss here attaches an event to the
    wrong company's position, which is far worse than not resolving it:
    a missing alert is visibly missing, a wrong one is not.
    """
    return _index()[1].get(_normalize_name(issuer_name), [])


def resolve(
    cik: str | None = None,
    issuer_name: str = "",
    provider_symbols: list[str] | None = None,
) -> list[str]:
    """Best available deterministic resolution. Empty list means unresolved.

    Provider tagging wins when present. A news wire that says an article
    is about AAPL is stating it, not guessing, and re-deriving it from
    the issuer name would only introduce a way to be wrong.
    """
    if provider_symbols:
        return [s.upper() for s in provider_symbols]
    if cik:
        hits = by_cik(cik)
        if hits:
            return hits
    if issuer_name:
        return by_name(issuer_name)
    return []
