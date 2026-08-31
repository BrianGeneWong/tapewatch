"""Extraction schema for SEC 8-K filings.

Design notes — this schema exists to be *evaluable*, not just expressive:

  - `event_type` is a closed enum, so accuracy is a single comparison.
    A free-text category would look richer and be impossible to score.
  - `parties` and `amounts` are lists of small structured records rather
    than prose, so they can be scored with set F1 and numeric tolerance.
  - `summary` is deliberately the ONLY free-text field. It is not
    auto-scored; it exists for humans reading the output.
  - Every optional field is explicitly `| None` so "the filing didn't say"
    is representable. Without that, the model invents values to fill
    a required field — the single most common cause of extraction
    hallucination.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Material event categories for 8-K filings.

    Keep this list short. Every category you add costs classification
    accuracy and needs its own labeled examples in the eval set.
    """

    ACQUISITION_OR_MERGER = "acquisition_or_merger"
    MATERIAL_AGREEMENT = "material_agreement"
    EXECUTIVE_CHANGE = "executive_change"
    FINANCIAL_RESULTS = "financial_results"
    DEBT_OR_FINANCING = "debt_or_financing"
    RESTRUCTURING = "restructuring"
    LEGAL_PROCEEDING = "legal_proceeding"
    IMPAIRMENT_OR_WRITEDOWN = "impairment_or_writedown"
    AUDITOR_CHANGE = "auditor_change"
    OTHER = "other"


PartyRole = Literal[
    "acquirer",
    "target",
    "counterparty",
    "lender",
    "borrower",
    "departing_officer",
    "incoming_officer",
    "other",
]


class Party(BaseModel):
    name: str = Field(description="Legal name exactly as written in the filing")
    role: PartyRole


class MonetaryAmount(BaseModel):
    value_usd: float | None = Field(
        description="Normalized to USD. Null if the filing states a "
        "non-USD amount without a conversion, or gives no figure."
    )
    raw_text: str = Field(description="The amount verbatim, e.g. '$1.2 billion'")
    represents: str = Field(
        description="What this amount is, in a few words, e.g. "
        "'purchase price', 'severance', 'credit facility size'"
    )


class FilingExtraction(BaseModel):
    """LLM-extracted content. Filing metadata is NOT here by design —
    accession number, CIK, company name, and form type come from EDGAR
    deterministically. Never ask a model for something you can look up."""

    event_type: EventType
    summary: str = Field(description="What happened, in at most two sentences")
    parties: list[Party] = Field(default_factory=list)
    amounts: list[MonetaryAmount] = Field(default_factory=list)
    effective_date: date | None = Field(
        default=None, description="Date the event took effect, if stated"
    )
    extraction_confidence: Literal["high", "medium", "low"] = Field(
        description="Low when the filing is ambiguous, truncated, or the "
        "event does not fit any category well"
    )


class ExtractionRecord(BaseModel):
    """What actually lands in storage: deterministic metadata + extraction."""

    accession_number: str
    cik: str
    company_name: str
    form_type: str
    filed_at: str
    source_url: str
    extraction: FilingExtraction
    # Instrumentation travels with the record so cost/latency can be
    # aggregated later without a separate join.
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
