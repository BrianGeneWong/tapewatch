# edgar-extract

Structured extraction of material events from SEC EDGAR 8-K filings, with
a measured accuracy number, tracked cost per document, and a deployment
story.

## Why this exists

Most LLM side projects are a model call behind a UI, with no way to
answer "does it work?" This one is built around the answer: a hand-labeled
eval set, per-field accuracy, and cost/latency instrumentation carried on
every record.

## Status

**Week 1 complete.** Ingestion works end to end: the Atom feed is
parsed, primary documents are located by type off the filing index, and
HTML is reduced to clean text. 19 filings fetched, 0 failures, no markup
or iXBRL metadata surviving into the text.

Week 2 (extraction + labels) is next. `extract()` is written but has not
been run against a real filing.

## Architecture

```
EDGAR Atom feed ──poll──► filing refs ──fetch──► document text
                                                      │
                                                      ▼
                                          Claude (structured output)
                                                      │
                                                      ▼
                          ExtractionRecord ──► JSONL (v1) / S3 (v3)
                                   │
                                   ├──► evals/  per-field accuracy
                                   └──► metrics cost + latency
```

Deterministic metadata (accession number, CIK, company, form type) comes
from EDGAR. Only the parts that genuinely require reading prose go to the
model. Never ask an LLM for something you can look up.

## Build plan

**Week 1 — ingestion, no LLM.** ✅ Parse the Atom feed into `FilingRef`
records; fetch and de-HTML primary documents. Done when you can pull 20
filings to disk as clean text.

**Week 2 — extraction.** Wire up `extract()` against the schema. Hand-label
50–100 filings (see `evals/README.md`). Done when you have a first
accuracy number, however bad.

**Week 3 — evals, instrumentation, deploy.** Finish `run_eval.py`, swap
JSONL for S3, put Kafka between ingestion and extraction, containerize,
deploy to a cluster.

Ship week 1 and 2 properly before starting week 3. A pipeline that
reliably extracts three fields beats an ambitious one that half-works.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # then set SEC_USER_AGENT
```

SEC requires a User-Agent identifying you with contact info, and caps
requests at 10/sec. Both are enforced.

## Usage

```bash
edgar-extract fetch --count 20     # filings to disk as text, no LLM
edgar-extract extract --limit 10   # run extraction over cached documents
edgar-extract metrics              # cost and latency summary
python evals/run_eval.py           # accuracy against hand labels
```

Documents are cached under `data/documents/` on fetch. Extraction reads
from that cache rather than re-fetching, which keeps you inside SEC's rate
limits while iterating and — more importantly — makes eval runs
reproducible. Scoring against a corpus that changes under you tells you
nothing.

## Results

<!-- Fill this in once week 2 lands. This section is the deliverable. -->

| Field | Accuracy | n |
|---|---|---|
| `event_type` | — | — |
| `parties` (F1) | — | — |
| `amounts` | — | — |
| `effective_date` | — | — |

Cost per filing: —
Latency p50 / p99: —

## What didn't work

<!-- Keep this honest and specific. It is the most senior-reading section
     in the file — more so than the results table. -->

## Design notes

- **Closed enums over free text.** `event_type` is an enum so accuracy is
  one comparison. A free-text category reads richer and cannot be scored.
- **Nullable everything optional.** If a field can't be null, the model
  invents a value to fill it. This is the most common source of
  extraction hallucination.
- **Instrumentation on the record, not in a side channel.** Tokens, cost,
  and latency travel with each extraction, so aggregation needs no join.
- **Model choice is a measurable lever.** `EDGAR_MODEL` and the price
  constants in `config.py` are configurable. Running the eval across
  models and reporting accuracy against cost per filing is a result worth
  publishing.
- **8-K item numbers are a free label.** EDGAR states them
  deterministically (`FilingRef.items`), and they correlate strongly with
  `event_type` — Item 5.02 is an executive change, 1.01 a material
  agreement. They are not a substitute for hand labels, but disagreement
  between the item number and the model's category is a cheap way to find
  filings worth reviewing by hand.
- **Line structure comes from block tags only.** Filing HTML soft-wraps
  mid-phrase; preserving those newlines splits company names across lines
  and breaks both verbatim extraction and eval string matching.
