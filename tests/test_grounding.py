from tapewatch.grounding import check
from tapewatch.schema import Classification, EvidenceSpan

SOURCE = (
    "On August 26, 2026, the Company entered into a definitive agreement "
    "to acquire Northwind Systems for $1.2 billion in cash."
)


def _c(spans: list[EvidenceSpan]) -> Classification:
    return Classification(
        event_type="acquisition_or_merger",
        summary="",
        direction="ambiguous",
        materiality=50,
        horizon="days",
        evidence=spans,
        confidence="high",
    )


def _span(quote: str, start: int = 0, end: int = 0) -> EvidenceSpan:
    return EvidenceSpan(quote=quote, char_start=start, char_end=end)


def test_exact_offsets_are_grounded():
    quote = "acquire Northwind Systems"
    start = SOURCE.index(quote)
    result = check(_c([_span(quote, start, start + len(quote))]), SOURCE)
    assert result.exact == 1
    assert result.absent == 0
    assert result.is_grounded


def test_wrong_offsets_are_relocated_not_failed():
    """Models are poor at counting characters. A quote that is really in
    the document must not be reported as a hallucination."""
    quote = "acquire Northwind Systems"
    result = check(_c([_span(quote, 0, len(quote))]), SOURCE)
    assert result.relocated == 1
    assert result.absent == 0
    assert result.is_grounded
    # The span is repaired to where the quote actually is.
    span = result.spans[0]
    assert SOURCE[span.char_start : span.char_end] == quote


def test_whitespace_differences_still_count_as_present():
    result = check(_c([_span("acquire  Northwind\nSystems", 0, 10)]), SOURCE)
    assert result.absent == 0
    assert result.is_grounded


def test_fabricated_quote_fails_grounding():
    result = check(_c([_span("acquire Contoso Robotics", 0, 24)]), SOURCE)
    assert result.absent == 1
    assert not result.is_grounded


def test_validity_rate_is_fraction_present():
    quote = "in cash"
    result = check(
        _c([_span(quote, SOURCE.index(quote), SOURCE.index(quote) + len(quote)),
            _span("a fabricated clause", 0, 19)]),
        SOURCE,
    )
    assert result.total == 2
    assert result.validity_rate == 0.5


def test_no_evidence_is_vacuously_grounded():
    result = check(_c([]), SOURCE)
    assert result.is_grounded
    assert result.validity_rate == 1.0
