"""Verify that the model's evidence actually appears in the source.

The cheapest hallucination guard available. It costs no extra model
call: the model is asked to quote the words it relied on, and we check
the quote is really there. A model that cannot point at the words is
usually a model that is guessing.

Two failure modes are worth separating, because they mean different
things:

  - `offsets_wrong`  — the quote is in the document but not at the stated
    offsets. Common and benign; models are poor at counting characters.
    Repair it by relocating the span.
  - `quote_absent`   — the quote is not in the document at all. This is
    fabrication, and the record should not be trusted.

Only the second is a grounding failure. Conflating them produces an
alarming number that mostly measures arithmetic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import Classification, EvidenceSpan

# Filing text is full of runs of whitespace that survive de-HTMLing
# inconsistently. Compare on collapsed whitespace so a quote that differs
# only by a line break still counts as present.
_WS = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _WS.sub(" ", s).strip().lower()


@dataclass
class GroundingResult:
    total: int
    exact: int          # quote found at the stated offsets
    relocated: int      # quote found, offsets corrected
    absent: int         # quote not in the source at all
    spans: list[EvidenceSpan]

    @property
    def is_grounded(self) -> bool:
        """A record is grounded when nothing was fabricated."""
        return self.absent == 0

    @property
    def validity_rate(self) -> float:
        return (self.exact + self.relocated) / self.total if self.total else 1.0


def check(classification: Classification, source_text: str) -> GroundingResult:
    """Validate every evidence span, repairing offsets where possible."""
    exact = relocated = absent = 0
    repaired: list[EvidenceSpan] = []
    haystack = _norm(source_text)

    for span in classification.evidence:
        actual = source_text[span.char_start : span.char_end]
        if actual == span.quote:
            exact += 1
            repaired.append(span)
            continue

        found = source_text.find(span.quote)
        if found != -1:
            relocated += 1
            repaired.append(
                span.model_copy(
                    update={"char_start": found, "char_end": found + len(span.quote)}
                )
            )
            continue

        if _norm(span.quote) and _norm(span.quote) in haystack:
            # Present but whitespace-mangled. Keep it, flag nothing —
            # the words were really there.
            relocated += 1
            repaired.append(span)
            continue

        absent += 1

    return GroundingResult(
        total=len(classification.evidence),
        exact=exact,
        relocated=relocated,
        absent=absent,
        spans=repaired,
    )
