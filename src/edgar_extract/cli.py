"""Entry points: `edgar-extract fetch | extract | metrics`."""

from __future__ import annotations

import argparse

from . import metrics, store
from .fetch import EdgarClient


def cmd_fetch(args: argparse.Namespace) -> None:
    """Week 1: pull filings to disk as clean text. No LLM involved."""
    client = EdgarClient()
    refs = client.recent(form_type=args.form, count=args.count)
    fetched = skipped = failed = 0
    for ref in refs:
        if store.has_document(ref.accession_number) and not args.force:
            skipped += 1
            continue
        try:
            text = client.document_text(ref)
        except Exception as exc:  # a malformed filing shouldn't end the run
            print(f"  FAIL {ref.accession_number}: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        store.write_document(ref, text)
        fetched += 1
        print(
            f"  {ref.accession_number}  {len(text):>7,} chars  "
            f"items={','.join(ref.items) or '-':<16} {ref.company_name[:40]}"
        )
    print(f"\nfetched {fetched}, skipped {skipped} (cached), failed {failed}")


def cmd_extract(args: argparse.Namespace) -> None:
    """Week 2: run extraction over cached documents."""
    from .extract import extract  # imported late so `fetch` needs no API key

    refs = store.read_refs()
    if not refs:
        raise SystemExit("No cached documents. Run `edgar-extract fetch` first.")
    for ref in refs[: args.limit]:
        record = extract(ref, store.read_document(ref.accession_number))
        store.write(record)
        print(
            f"  {ref.accession_number}  {record.extraction.event_type.value:<26} "
            f"${record.cost_usd:.4f}  {record.latency_ms}ms"
        )


def cmd_metrics(_: argparse.Namespace) -> None:
    records = store.read_all()
    if not records:
        raise SystemExit("No extractions yet. Run `edgar-extract extract` first.")
    print(metrics.summarize(records).render())


def main() -> None:
    parser = argparse.ArgumentParser(prog="edgar-extract")
    sub = parser.add_subparsers(required=True)

    f = sub.add_parser("fetch", help="fetch filings to disk as text (no LLM)")
    f.add_argument("--form", default="8-K")
    f.add_argument("--count", type=int, default=20)
    f.add_argument("--force", action="store_true", help="re-fetch cached filings")
    f.set_defaults(func=cmd_fetch)

    e = sub.add_parser("extract", help="extract from cached documents")
    e.add_argument("--limit", type=int, default=10)
    e.set_defaults(func=cmd_extract)

    m = sub.add_parser("metrics", help="cost and latency summary")
    m.set_defaults(func=cmd_metrics)

    args = parser.parse_args()
    args.func(args)
