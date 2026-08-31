"""Rule-based extraction — no API calls, no cost.

This is a *baseline*, not a replacement for the LLM path. It exists to
answer the question every LLM project should be able to answer and almost
none can: what does the model actually add over rules, and what does that
delta cost?

What rules can do here:
  - `event_type`   — 8-K item numbers are a near-direct mapping. EDGAR
                     states them, so this is free and deterministic.
  - `effective_date` — "Date of earliest event reported" is a fixed
                     convention in the form.
  - `amounts`      — dollar figures are regular. What each amount
                     *represents* is not.

What rules cannot do:
  - `parties`      — requires reading prose to know who is the acquirer
                     vs. the target vs. an unrelated mention.
  - `summary`      — requires generation.

Score the baseline only on the fields it attempts (see evals/README.md).
Reporting 0% on `parties` for an extractor that never tries is not a
finding, it is a category error.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from .fetch import FilingRef
from .schema import EventType, FilingExtraction, MonetaryAmount

# 8-K item number -> event category. From the SEC's own item definitions.
ITEM_TO_EVENT: dict[str, EventType] = {
    "1.01": EventType.MATERIAL_AGREEMENT,       # Entry into a Material Definitive Agreement
    "1.02": EventType.MATERIAL_AGREEMENT,       # Termination of same
    "1.03": EventType.RESTRUCTURING,            # Bankruptcy or Receivership
    "2.01": EventType.ACQUISITION_OR_MERGER,    # Completion of Acquisition/Disposition
    "2.02": EventType.FINANCIAL_RESULTS,        # Results of Operations
    "2.03": EventType.DEBT_OR_FINANCING,        # Direct Financial Obligation
    "2.04": EventType.DEBT_OR_FINANCING,        # Triggering Events / Acceleration
    "2.05": EventType.RESTRUCTURING,            # Exit or Disposal Costs
    "2.06": EventType.IMPAIRMENT_OR_WRITEDOWN,  # Material Impairments
    "3.02": EventType.DEBT_OR_FINANCING,        # Unregistered Sales of Equity
    "4.01": EventType.AUDITOR_CHANGE,           # Change in Certifying Accountant
    "4.02": EventType.FINANCIAL_RESULTS,        # Non-Reliance on Prior Statements
    "5.01": EventType.ACQUISITION_OR_MERGER,    # Changes in Control
    "5.02": EventType.EXECUTIVE_CHANGE,         # Departure/Election of Officers
}

# Items that wrap a disclosure rather than describe an event. A filing
# tagged 5.02 + 7.01 + 9.01 is an executive change; the other two say
# only "and here is a press release about it". Ignore them unless they
# are all a filing has.
WRAPPER_ITEMS = {"7.01", "8.01", "9.01", "3.03", "5.03"}

_DATE_LINE = re.compile(
    r"earliest\s+event\s+reported\)?\s*:?\s*"
    r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})",
    re.I,
)

_MULTIPLIER = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}
_AMOUNT = re.compile(
    r"\$\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<mult>thousand|million|billion|trillion)?",
    re.I,
)


def event_type_from_items(items: list[str]) -> EventType:
    """Map 8-K item numbers to a category, preferring substantive items."""
    substantive = [i for i in items if i not in WRAPPER_ITEMS]
    for item in substantive or items:
        if item in ITEM_TO_EVENT:
            return ITEM_TO_EVENT[item]
    return EventType.OTHER


def effective_date_from_text(text: str) -> date | None:
    m = _DATE_LINE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("date").replace("  ", " "), "%B %d, %Y").date()
    except ValueError:
        return None


def amounts_from_text(text: str, limit: int = 10) -> list[MonetaryAmount]:
    out: list[MonetaryAmount] = []
    seen: set[float] = set()
    for m in _AMOUNT.finditer(text):
        try:
            value = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        mult = m.group("mult")
        if mult:
            value *= _MULTIPLIER[mult.lower()]
        if value in seen:
            continue
        seen.add(value)
        out.append(
            MonetaryAmount(
                value_usd=value,
                raw_text=m.group(0).strip(),
                # Rules can find the number but not what it is for.
                # Empty is honest; a guess would poison the eval.
                represents="",
            )
        )
        if len(out) >= limit:
            break
    return out


def extract_baseline(ref: FilingRef, text: str) -> FilingExtraction:
    """Rule-only extraction. Fields rules cannot do are left empty."""
    return FilingExtraction(
        event_type=event_type_from_items(ref.items),
        summary="",           # not attempted
        parties=[],           # not attempted
        amounts=amounts_from_text(text),
        effective_date=effective_date_from_text(text),
        extraction_confidence="low" if not ref.items else "medium",
    )
