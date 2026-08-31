# Evaluation

This directory is the part of the project that makes it credible. Most
LLM projects skip it; skipping it means you cannot answer "does it
work?" with anything but a demo.

## Building the label set

Target 50–100 filings. Fewer than 50 and accuracy differences are noise.

1. Run `edgar-extract poll` to collect real filings.
2. For each, hand-write the correct extraction as JSON in `labels/`,
   named `<accession_number>.json`, matching `FilingExtraction`.
3. Label them *before* you look at the model's output. Reading the
   model's answer first contaminates your judgment about what the
   correct answer was — this is the single easiest way to fool yourself
   into a good score.

Pick filings that are actually hard: multi-party deals, several dollar
amounts, ambiguous categories. An eval set of easy filings reports a
high number that means nothing.

## Scoring

| Field | Metric | Why |
|---|---|---|
| `event_type` | exact match accuracy | closed enum, one comparison |
| `parties` | set F1 on (name, role) | order-independent, partial credit |
| `amounts` | numeric match, 1% tolerance | rounding and unit differences are not errors |
| `effective_date` | exact match | unambiguous when stated |
| `summary` | not scored | free text; read a sample by hand |

Report per-field numbers, not one blended score. A pipeline that gets
`event_type` right 95% of the time and `amounts` right 60% of the time
has one specific problem, and a blended 82% hides it.

## What to publish in the top-level README

- Per-field accuracy on N labeled filings
- Cost per filing
- p50 / p99 latency
- What you tried that did not work
