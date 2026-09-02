# tapewatch

Reads market news and SEC filings as they land, judges whether each event
actually matters **to a specific book of positions**, and raises a
grounded alert with citations.

Not a price tracker. A materiality engine.

## Why this exists

Most LLM side projects are a model call behind a UI, with no way to
answer "does it work?" This one is built around the answer: a
hand-labeled eval set, per-field accuracy, rule and model baselines, and
cost/latency instrumentation carried on every record.

## Status

**Week 1 complete.** Ingestion, ticker resolution, and the rule baseline
run end to end with no API key and no cost:

```
19 filings ingested, 0 failures
17/19 resolved to a ticker      (the 2 misses are a debt-only subsidiary
                                 and a mortgage trust — neither has one)
 7/19 touch the simulated book
11/19 categorized by rules alone, 8 need the model
```

Week 2 (labels, eval harness, routing) is next. `classify()` is written
and exercised by tests, but has not been run against a live corpus.

## Where the model is allowed to think

```
ingest ──► resolve ──► CLASSIFY ──► aggregate ──► alert ──► INVESTIGATE ──► serve
 rules      rules       model        flink        rules       agent          api
```

The model is confined to the two stages that require reading prose.
Ticker resolution, position math, windowing, and thresholds are
deterministic and unit-tested. Never ask a model for something you can
look up — the SEC publishes the entire CIK-to-ticker mapping, so
resolution is a dictionary lookup, not a prompt.

Two consequences worth stating plainly:

- **Grounding is checked, not trusted.** Every classification must quote
  the words it relied on, and those quotes are verified as verbatim
  substrings of the source before the record is accepted. Wrong offsets
  are repaired; absent quotes fail the record. See `grounding.py`.
- **Relevance is filtered before spend.** Most filings are about
  companies nobody holds. `--in-book-only` applies that filter ahead of
  the model call, which is the single largest cost lever in the pipeline.

## Layout

```
src/tapewatch/
  sources/        ingestion adapters — edgar.py (working), news.py (stub)
  resolve.py      CIK/name -> ticker, deterministic, no model
  book.py         the simulated book of positions
  classify.py     the model step, with confidence-based routing
  grounding.py    verbatim-quote verification
  baseline.py     rule-only classification, $0.00, scored alongside
  metrics.py      cost, latency, and routing split
evals/            labeling guide and scoring harness
```

Adapters differ upstream and are identical downstream: everything after
ingestion is written against `SourceEvent`, which is what lets the news
source drop in beside EDGAR without touching classification or evals.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env          # set SEC_USER_AGENT — SEC blocks requests without it
cp book.example.json data/book.json
```

## Run

```bash
tapewatch ingest --count 20      # fetch filings to disk        (free)
tapewatch resolve --refresh      # map to tickers and the book  (free)
tapewatch baseline               # rule-only classification     (free)
tapewatch classify --route --in-book-only --limit 5
tapewatch metrics
```

The first three need no API key and cost nothing.

## Build plan

See [PLAN.md](PLAN.md). Weeks 2-4 add the eval harness and a measured
accuracy number, then Kafka and a Flink risk aggregation against the
book, then the investigator agent and a dashboard.

## Limitations

The book is **simulated** — a static positions file. There is no
brokerage connection and no order path. Tapewatch surfaces events for
human review; it does not recommend trades, and nothing it produces is
investment advice.
