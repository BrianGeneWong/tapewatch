"""The LLM step: filing text in, validated FilingExtraction out."""

from __future__ import annotations

import time

import anthropic

from .config import MODEL, PRICE_INPUT_PER_MTOK, PRICE_OUTPUT_PER_MTOK
from .fetch import FilingRef
from .schema import ExtractionRecord, FilingExtraction

client = anthropic.Anthropic()

SYSTEM = """You extract structured data from SEC 8-K filings.

Rules:
- Report only what the filing states. Never infer, estimate, or fill gaps \
from background knowledge about the company.
- If a field is not stated in the filing, leave it null or empty. An empty \
field is correct; an invented one is a defect.
- Party names must appear verbatim in the filing.
- Set extraction_confidence to "low" when the filing is ambiguous, appears \
truncated, or the event does not fit any category cleanly."""


class RefusalError(RuntimeError):
    """The model declined the request. Rare here, but a filing containing
    unusual content can trigger it — handle it rather than crashing a
    batch of ten thousand."""


def extract(ref: FilingRef, document_text: str) -> ExtractionRecord:
    started = time.monotonic()

    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Filing: {ref.form_type} filed {ref.filed_at} by "
                    f"{ref.company_name}\n\n{document_text}"
                ),
            }
        ],
        output_format=FilingExtraction,
    )

    # Always check stop_reason before reading content. A refusal returns
    # HTTP 200 — it does not raise.
    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise RefusalError(f"refused on {ref.accession_number}: {detail}")

    # TODO(week 2): add server-side refusal fallbacks so a refusal reroutes
    # instead of failing the record. Shape per the Anthropic docs is
    # betas=["server-side-fallback-2026-07-01"] + fallbacks="default" on
    # messages.create — verify it is accepted by messages.parse() before
    # relying on it.

    latency_ms = int((time.monotonic() - started) * 1000)
    usage = response.usage
    cost = (
        usage.input_tokens / 1_000_000 * PRICE_INPUT_PER_MTOK
        + usage.output_tokens / 1_000_000 * PRICE_OUTPUT_PER_MTOK
    )

    return ExtractionRecord(
        accession_number=ref.accession_number,
        cik=ref.cik,
        company_name=ref.company_name,
        form_type=ref.form_type,
        filed_at=ref.filed_at,
        source_url=ref.source_url,
        items=ref.items,
        extraction=response.parsed_output,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=round(cost, 6),
        latency_ms=latency_ms,
        model=MODEL,
    )
