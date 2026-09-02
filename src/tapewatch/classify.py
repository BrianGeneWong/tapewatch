"""The model step: a SourceEvent in, a validated Classification out.

Two things happen here that do not happen in a plain wrapper around an
API call, and they are the point of the module:

  - **Routing.** The cheap model sees everything. The expensive one sees
    only what the cheap one could not confidently answer. The accuracy
    lost and the money saved are both measurable, and `route` on every
    record is what makes the accuracy/cost curve plottable.
  - **Grounding.** The model must quote the words it relied on, and those
    quotes are checked against the source before the record is accepted.
"""

from __future__ import annotations

import time

import anthropic

from .config import (
    EFFORT_CAPABLE,
    ESCALATE_ON_CONFIDENCE,
    ESCALATION_MODEL,
    PRIMARY_MODEL,
    price,
)
from .grounding import check
from .schema import Classification, EventRecord, SourceEvent

client = anthropic.Anthropic()

SYSTEM = """You classify material events for an equities risk system.

You are given one source document — an SEC filing or a market news item \
— about a public company. Decide what happened and how much it should \
move a reasonable investor's view of the issuer.

Rules:
- Report only what the source states. Never infer, estimate, or fill gaps \
from background knowledge about the company.
- If a field is not stated in the source, leave it null or empty. An empty \
field is correct; an invented one is a defect.
- Every quote in `evidence` must be copied verbatim from the source. Do \
not normalize whitespace, punctuation, or capitalization. Quotes that do \
not appear in the source are the single worst failure mode here.
- Party names must appear verbatim in the source.
- `materiality` is about the issuer, not about how dramatic the language \
is. Routine, scheduled, and administrative disclosures score low even \
when they are long.
- Set `direction` to "ambiguous" freely. Most disclosures genuinely do \
not imply a direction, and a forced guess is worse than an honest one.
- Set `confidence` to "low", or `abstain` to true, when the source is \
ambiguous, truncated, or fits no category cleanly. An honest abstention \
is a correct answer.
- Do not give investment advice or recommend any action. You are \
describing what happened, not what anyone should do about it."""


class RefusalError(RuntimeError):
    """The model declined the request. Rare here, but a source containing
    unusual content can trigger it — handle it rather than crashing a
    batch of ten thousand."""


def _prompt(event: SourceEvent) -> str:
    header = f"Source: {event.source_kind} · {event.title} · published {event.published_at}"
    if event.items:
        # 8-K item numbers are stated by EDGAR. Giving them to the model
        # is not cheating — it is the same lookup the baseline uses.
        header += f"\n8-K items: {', '.join(event.items)}"
    if event.source_kind != "edgar":
        header += (
            "\n\nThis is a news item, not a filing. Leave `detail` null — "
            "party roles and effective dates are rarely stated in a headline."
        )
    return f"{header}\n\n{event.text}"


def _call(event: SourceEvent, model: str) -> tuple[Classification, object, int]:
    started = time.monotonic()

    kwargs: dict = {}
    if model in EFFORT_CAPABLE:
        # Classification is not a reasoning-heavy task; low effort is the
        # right default and the cheap one. Raise it only if the eval says
        # accuracy is left on the table.
        kwargs["output_config"] = {"effort": "low"}

    response = client.messages.parse(
        model=model,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": _prompt(event)}],
        output_format=Classification,
        **kwargs,
    )

    # Always check stop_reason before reading content. A refusal returns
    # HTTP 200 — it does not raise.
    if response.stop_reason == "refusal":
        detail = getattr(response, "stop_details", None)
        raise RefusalError(f"refused on {event.event_id}: {detail}")

    # TODO(week 2): add server-side refusal fallbacks so a refusal reroutes
    # instead of failing the record. Shape per the Anthropic docs is
    # betas=["server-side-fallback-2026-07-01"] + fallbacks="default" on
    # messages.create — verify it is accepted by messages.parse() before
    # relying on it.

    latency_ms = int((time.monotonic() - started) * 1000)
    return response.parsed_output, response.usage, latency_ms


def _record(
    event: SourceEvent,
    classification: Classification,
    usage,
    latency_ms: int,
    model: str,
    route: str,
    tickers: list[str],
) -> EventRecord:
    price_in, price_out = price(model)
    cost = (
        usage.input_tokens / 1_000_000 * price_in
        + usage.output_tokens / 1_000_000 * price_out
    )
    return EventRecord(
        event=event,
        tickers=tickers,
        classification=classification,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=round(cost, 6),
        latency_ms=latency_ms,
        model=model,
        route=route,  # type: ignore[arg-type]
    )


def classify(
    event: SourceEvent,
    tickers: list[str] | None = None,
    model: str = PRIMARY_MODEL,
    route: str = "primary",
) -> EventRecord:
    """Single-model classification. No routing, no escalation."""
    classification, usage, latency_ms = _call(event, model)
    classification.evidence = check(classification, event.text).spans
    return _record(
        event, classification, usage, latency_ms, model, route, tickers or []
    )


def classify_routed(
    event: SourceEvent, tickers: list[str] | None = None
) -> tuple[EventRecord, EventRecord | None]:
    """Cheap model first, escalating only when it is unsure.

    Returns (final_record, primary_record_if_escalated). The discarded
    primary attempt is returned rather than dropped because its cost was
    really spent — a routing policy that reports only the winning call
    understates what it costs to run.
    """
    primary = classify(event, tickers, PRIMARY_MODEL, route="primary")

    unsure = (
        primary.classification.abstain
        or primary.classification.confidence == ESCALATE_ON_CONFIDENCE
    )
    if not unsure or ESCALATION_MODEL == PRIMARY_MODEL:
        return primary, None

    escalated = classify(event, tickers, ESCALATION_MODEL, route="escalated")
    return escalated, primary
