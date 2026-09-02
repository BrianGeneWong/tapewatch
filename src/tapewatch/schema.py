"""Schemas for the Tapewatch pipeline.

Design notes — these types exist to be *evaluable*, not just expressive:

  - `event_type` is a closed enum, so accuracy is a single comparison.
    A free-text category would look richer and be impossible to score.
  - `parties` and `amounts` are lists of small structured records rather
    than prose, so they can be scored with set F1 and numeric tolerance.
  - `summary` is deliberately the ONLY free-text field. It is not
    auto-scored; it exists for humans reading the output.
  - Every optional field is explicitly `| None` so "the source didn't say"
    is representable. Without that, the model invents values to fill
    a required field — the single most common cause of extraction
    hallucination.

Layering, reading top to bottom:

    SourceEvent      what an ingestion adapter yields (filing, headline)
    Classification   what the model produces from it
    EventRecord      envelope + resolved tickers + classification + cost

Deterministic facts never appear in `Classification`. Accession numbers,
CIKs, form types, 8-K item numbers and tickers are all looked up, not
generated. Never ask a model for something you can look up.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Material event categories, shared across filings and news.

    Keep this list short. Every category you add costs classification
    accuracy and needs its own labeled examples in the eval set. The
    first ten came from 8-K item definitions; `guidance_change` and
    `regulatory_action` were added when news ingestion landed, because
    they are common in headlines and have no clean 8-K item mapping.
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
    GUIDANCE_CHANGE = "guidance_change"
    REGULATORY_ACTION = "regulatory_action"
    OTHER = "other"


PartyRole = Literal[
    "acquirer",
    "target",
    "counterparty",
    "lender",
    "borrower",
    "departing_officer",
    "incoming_officer",
    "regulator",
    "other",
]

Direction = Literal["negative", "positive", "ambiguous"]
Horizon = Literal["intraday", "days", "quarters"]
SourceKind = Literal["edgar", "news"]


class Party(BaseModel):
    name: str = Field(description="Legal name exactly as written in the source")
    role: PartyRole


class MonetaryAmount(BaseModel):
    value_usd: float | None = Field(
        description="Normalized to USD. Null if the source states a "
        "non-USD amount without a conversion, or gives no figure."
    )
    raw_text: str = Field(description="The amount verbatim, e.g. '$1.2 billion'")
    represents: str = Field(
        description="What this amount is, in a few words, e.g. "
        "'purchase price', 'severance', 'credit facility size'"
    )


class EvidenceSpan(BaseModel):
    """A verbatim quote from the source supporting the classification.

    Offsets are checked against the source text before a record is
    accepted (see `grounding.py`). This is the cheapest hallucination
    guard available: it costs no extra model call, and a model that
    cannot point at the words is usually a model that is guessing.
    """

    quote: str = Field(
        description="Verbatim substring of the source. Copy exactly — "
        "do not normalize whitespace, punctuation, or capitalization."
    )
    char_start: int = Field(description="Start offset of the quote in the source text")
    char_end: int = Field(description="End offset, exclusive")


class FilingDetail(BaseModel):
    """Fields worth extracting from a full filing, but not from a headline.

    Populated only for `source_kind == "edgar"`. A news headline rarely
    states party roles or a clean effective date, and asking for them
    anyway is how you teach a model to invent them.
    """

    parties: list[Party] = Field(default_factory=list)
    amounts: list[MonetaryAmount] = Field(default_factory=list)
    effective_date: date | None = Field(
        default=None, description="Date the event took effect, if stated"
    )


class Classification(BaseModel):
    """Everything the model is asked to produce. Source-agnostic."""

    event_type: EventType
    summary: str = Field(description="What happened, in at most two sentences")
    direction: Direction = Field(
        description="Likely direction of impact on the issuer's equity, if the "
        "source implies one. Use 'ambiguous' freely — most disclosures are."
    )
    materiality: int = Field(
        ge=0,
        le=100,
        description="How much this should move a reasonable investor's view of "
        "the issuer. 0 = routine or administrative, 50 = notable, "
        "90+ = reshapes the investment case.",
    )
    horizon: Horizon = Field(description="Timescale over which the impact plays out")
    evidence: list[EvidenceSpan] = Field(
        default_factory=list,
        description="One to three verbatim quotes that justify event_type and "
        "materiality. Required unless abstaining.",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        description="Low when the source is ambiguous, truncated, or the "
        "event does not fit any category well"
    )
    abstain: bool = Field(
        default=False,
        description="True when the source does not support a confident "
        "classification at all. An honest abstention is a correct answer; "
        "a confident guess is a defect.",
    )
    detail: FilingDetail | None = Field(
        default=None, description="Filing-only fields. Null for news items."
    )


class SourceEvent(BaseModel):
    """Normalized envelope yielded by every ingestion adapter.

    Adapters differ wildly upstream — an Atom feed of filings, a news
    websocket — and identically downstream. Everything after ingestion
    is written against this type, which is what lets the news source drop
    in beside EDGAR without touching classification, routing, or evals.
    """

    event_id: str = Field(description="Stable unique id, e.g. accession number")
    source_kind: SourceKind
    published_at: str
    source_url: str
    title: str
    text: str
    issuer_name: str = ""
    # Deterministic metadata the adapter happens to know. EDGAR fills cik
    # and items; a news adapter typically fills neither.
    cik: str | None = None
    items: list[str] = Field(default_factory=list)


class EventRecord(BaseModel):
    """What actually lands in storage: envelope + lookups + model output."""

    event: SourceEvent
    # Resolved deterministically from cik or issuer name — never by the
    # model. Empty means resolution failed, which is a pipeline metric
    # worth watching, not a reason to ask the model to guess.
    tickers: list[str] = Field(default_factory=list)
    classification: Classification
    # Instrumentation travels with the record so cost and latency can be
    # aggregated later without a separate join.
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    model: str
    # Which policy produced this record: the free rules path, the cheap
    # model, or an escalation. The accuracy/cost curve is built from this.
    route: Literal["rules", "primary", "escalated"] = "primary"
