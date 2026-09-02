# Tapewatch — build plan

Working title. Alternates: Materiality, Bellwether. Rename the directory
before the first public commit.

A real-time engine that reads market news and SEC filings as they land,
judges whether each event actually matters *to a specific book of
positions*, and raises a grounded alert with citations.

Not a price tracker. A materiality engine.

Full plan (formatted): https://claude.ai/code/artifact/b3111af7-f647-44c0-be3b-8e530553ebd1

## Where the model is allowed to think

```
ingest ──► resolve tickers ──► CLASSIFY ──► aggregate ──► alert ──► INVESTIGATE ──► serve
 rules        rules            model        flink        rules       agent          api+ui
```

The model is confined to the two stages that require reading prose.
Ticker resolution, position math, windowing and thresholds stay
deterministic and unit-tested. Never ask a model for something you can
look up.

## Schema

```json
{
  "event_type": "guidance_cut | m_and_a | litigation | regulatory_action | exec_change | earnings_surprise | offering | other",
  "tickers": ["ABC"],
  "direction": "negative | positive | ambiguous",
  "materiality": 0,
  "horizon": "intraday | days | quarters",
  "evidence": [{"quote": "...", "char_start": 0, "char_end": 0}],
  "confidence": 0.0,
  "abstain": false
}
```

Evidence quotes are validated as verbatim substrings of the source before
the record is accepted. Cheap, hard grounding guard.

## Weeks

**Week 1 — thin vertical slice.** One news source, five event types, no
Kafka, no UI. Verify data-source free tiers on day one. Build the
ticker/CIK dictionary. Structured output + span validator. Instrument
tokens/latency/cost from the first call.
*Done when:* 100 real headlines classified end to end.

**Week 2 — the number.** Hand-label 200 items, stratified; write the
labeling guide first. Eval harness: macro-F1 on event type, MAE on
materiality, span-validity rate, abstention precision. Three baselines —
keyword rules, cheap model, frontier model. Confidence-based routing with
an accuracy-vs-cost curve. CI gate on >2pt macro-F1 regression.
*Done when:* README carries a real accuracy number and a $/1k figure.

**Week 3 — the streaming core.** Kafka topics between stages
(`raw.events` → `resolved.events` → `classified.events` → `risk.state`).
Flink job joining events to a simulated book, windowed materiality
accumulation. Real-time alerting with dedupe + cooldown. Replay from the
JSONL corpus so nothing depends on market hours.
*Done when:* an alert fires live on a real headline against a real position.

**Week 4 — the agent and the face.** Investigator agent producing cited
briefs. React dashboard. Docker Compose one-command run + K8s manifests.
README rewritten around the number.
*Done when:* a stranger can clone, run one command, and watch it work.

**Optional.** Online eval / drift monitoring. Prompt caching + batching
with a before/after cost curve. Alert precision vs subsequent realized
volatility — a measurement of alert quality, not a trading claim.

## Stack

| Layer | Choice |
|---|---|
| Ingest + classify | Python |
| Eval harness | Python + CI |
| Aggregation | Flink (Java) |
| API + alerting | Spring Boot |
| Transport | Kafka |
| Storage | JSONL → MinIO/S3 |
| UI | React + Vite |

If four weeks turns out optimistic: cut Flink before cutting the eval
harness. A project with no measured accuracy tells no story at all.

## Data sources — verify free tiers on day one

- SEC EDGAR Atom — already solved in `edgar-extract`
- Alpaca — news stream + bars; verify free-tier news access
- Finnhub — news, company data; verify request ceilings
- Tiingo / yfinance — EOD bars; verify redistribution terms

The book is **simulated** — a static positions file, stated plainly in
the README. No brokerage connection, no order path. The system surfaces
risk for review; it does not recommend trades.

## How this fails

- Dashboard first. Nothing to display until week three.
- No labels, so no number. Then it's a wrapper around a model call.
- Letting the model do arithmetic. Resolution and position math are lookups and sums.
- Scope creep into backtesting. Becomes unfinishable, claims stop being defensible.
- Running this and `edgar-extract` in parallel.

## Open decisions

- Name. Working title is Tapewatch; the GitHub repo is still named
  `edgar-extract` and needs renaming (GitHub redirects the old URL, so
  nothing breaks).
- Public from day one, or public at week two.

## Done

- **edgar-extract folded in** (Sep 2). Grown in place rather than copied,
  so the commit history from Aug 31 is preserved. `edgar_extract` became
  `tapewatch`; `fetch.py` became `sources/edgar.py` behind a `SourceEvent`
  envelope; `extract.py` became `classify.py` with confidence-based
  routing. New: `resolve.py`, `grounding.py`, `book.py`. 19 cached filings
  migrated to the new format. 14 tests, lint clean.
