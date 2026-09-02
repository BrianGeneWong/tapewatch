"""The simulated book of positions.

Simulated, and said so everywhere it surfaces. There is no brokerage
connection and no order path anywhere in this project: Tapewatch decides
which events are worth a human's attention, which is a filtering problem,
not a trading one.

A position file is JSON:

    [
      {"ticker": "ABC", "shares": 1200, "sector": "Industrials"},
      {"ticker": "XYZ", "shares": -400, "sector": "Technology"}
    ]

Exposure is deliberately share-count based rather than mark-to-market.
Live prices would add a data dependency, a staleness problem, and a
market-hours constraint to a component whose only job is answering "do we
hold this, and roughly how much".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR

_BOOK = Path(DATA_DIR) / "book.json"


@dataclass(frozen=True)
class Position:
    ticker: str
    shares: float
    sector: str = "Unclassified"

    @property
    def is_short(self) -> bool:
        return self.shares < 0


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> dict[str, Position]:
    src = path or _BOOK
    if not src.exists():
        return {}
    rows = json.loads(src.read_text())
    return {
        str(r["ticker"]).upper(): Position(
            ticker=str(r["ticker"]).upper(),
            shares=float(r["shares"]),
            sector=str(r.get("sector", "Unclassified")),
        )
        for r in rows
    }


def held(tickers: list[str]) -> list[Position]:
    """Positions matching any of these tickers. Empty when we hold none."""
    book = load()
    return [book[t] for t in {t.upper() for t in tickers} if t in book]


def is_relevant(tickers: list[str]) -> bool:
    """Whether an event touches the book at all.

    The cheapest filter in the pipeline, and the one that decides whether
    an event is worth classifying at all. Applying it *before* the model
    call is the single largest cost lever available — most filings are
    about companies nobody holds.
    """
    return bool(held(tickers))
