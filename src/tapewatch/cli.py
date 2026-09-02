"""Entry points: `tapewatch ingest | resolve | baseline | classify | metrics`.

The commands map one-to-one onto pipeline stages, which is deliberate:
each one can be run, inspected, and demonstrated on its own. `ingest` and
`baseline` need no API key and cost nothing.
"""

from __future__ import annotations

import argparse

from . import book, metrics, resolve, store
from .baseline import extract_baseline
from .sources.edgar import EdgarClient


def cmd_ingest(args: argparse.Namespace) -> None:
    """Pull source events to disk as clean text. No model involved."""
    if args.source == "news":
        return _ingest_news(args)
    client = EdgarClient()
    refs = client.recent(form_type=args.form, count=args.count)
    fetched = skipped = failed = 0
    for ref in refs:
        if store.has_event(ref.accession_number) and not args.force:
            skipped += 1
            continue
        try:
            text = client.document_text(ref)
        except Exception as exc:  # a malformed filing shouldn't end the run
            print(f"  FAIL {ref.accession_number}: {type(exc).__name__}: {exc}")
            failed += 1
            continue
        from .sources.edgar import to_source_event

        event = to_source_event(ref, text)
        store.write_event(event)
        fetched += 1
        print(
            f"  {event.event_id}  {len(text):>7,} chars  "
            f"items={','.join(ref.items) or '-':<16} {ref.company_name[:40]}"
        )
    print(f"\ningested {fetched}, skipped {skipped} (cached), failed {failed}")


def _ingest_news(args: argparse.Namespace) -> None:
    """Ingest from the news wire. Article text stays local — see
    sources/news.py for why."""
    from .sources.news import NewsClient

    symbols = list(book.load()) if args.book_only else None
    if args.book_only and not symbols:
        raise SystemExit("No book to filter by. Copy book.example.json to data/book.json.")

    events = NewsClient().poll(limit=args.count, symbols=symbols)
    fetched = skipped = 0
    for event in events:
        if store.has_event(event.event_id) and not args.force:
            skipped += 1
            continue
        store.write_event(event)
        fetched += 1
        print(
            f"  {event.event_id:<12} {','.join(event.provider_symbols) or '-':<14} "
            f"{len(event.text):>6,} chars  {event.title[:52]}"
        )
    print(f"\ningested {fetched}, skipped {skipped} (cached)")


def cmd_resolve(args: argparse.Namespace) -> None:
    """Map cached events to tickers, and report how many touch the book.

    Free, deterministic, and the most useful diagnostic in the project:
    the resolution rate and the in-book rate together tell you how much
    of your corpus is even worth spending tokens on.
    """
    if args.refresh:
        print(f"refreshed {resolve.refresh_cache()}")
    events = store.read_events()
    if not events:
        raise SystemExit("No cached events. Run `tapewatch ingest` first.")

    resolved = in_book = 0
    for event in events:
        tickers = resolve.resolve(
            cik=event.cik,
            issuer_name=event.issuer_name,
            provider_symbols=event.provider_symbols,
        )
        if tickers:
            resolved += 1
        held = book.held(tickers)
        if held:
            in_book += 1
        print(
            f"  {event.event_id}  {','.join(tickers) or '-':<12} "
            f"{'IN BOOK' if held else '':<8} {event.issuer_name[:40]}"
        )
    print(
        f"\nresolved {resolved}/{len(events)} to a ticker; "
        f"{in_book} touch the book. Cost: $0.00"
    )


def cmd_baseline(_: argparse.Namespace) -> None:
    """Rule-only classification over cached events. No API calls, no cost."""
    events = store.read_events()
    if not events:
        raise SystemExit("No cached events. Run `tapewatch ingest` first.")
    unresolved = 0
    for event in events:
        b = extract_baseline(event)
        if b.event_type.value == "other":
            unresolved += 1
        detail = b.detail
        print(
            f"  {event.event_id}  {b.event_type.value:<24} "
            f"{str((detail.effective_date if detail else None) or '-'):<12} "
            f"{len(detail.amounts) if detail else 0} amounts"
        )
    print(
        f"\n{len(events) - unresolved}/{len(events)} categorized from item "
        f"numbers; {unresolved} need the model. Cost: $0.00"
    )


def cmd_classify(args: argparse.Namespace) -> None:
    """Run classification over cached events, with or without routing."""
    from .classify import classify, classify_routed

    events = store.read_events()
    if not events:
        raise SystemExit("No cached events. Run `tapewatch ingest` first.")

    if args.in_book_only:
        # The largest cost lever in the pipeline: most filings are about
        # companies nobody holds. Filter before spending tokens.
        before = len(events)
        events = [
            e
            for e in events
            if book.is_relevant(
                resolve.resolve(
                    cik=e.cik,
                    issuer_name=e.issuer_name,
                    provider_symbols=e.provider_symbols,
                )
            )
        ]
        print(f"filtering to {len(events)}/{before} events that touch the book")

    spent = 0.0
    for event in events[: args.limit]:
        tickers = resolve.resolve(
            cik=event.cik,
            issuer_name=event.issuer_name,
            provider_symbols=event.provider_symbols,
        )
        if args.route:
            record, discarded = classify_routed(event, tickers)
            if discarded:
                # The discarded attempt cost real money. Store it so the
                # routing policy is costed honestly.
                store.write(discarded)
                spent += discarded.cost_usd
        else:
            record = classify(event, tickers)
        store.write(record)
        spent += record.cost_usd
        c = record.classification
        print(
            f"  {event.event_id}  {c.event_type.value:<24} "
            f"mat={c.materiality:<3} {c.direction:<9} {record.route:<10} "
            f"${record.cost_usd:.4f}  {record.latency_ms}ms"
        )
    print(f"\ntotal spent ${spent:.4f}")


def cmd_metrics(_: argparse.Namespace) -> None:
    records = store.read_all()
    if not records:
        raise SystemExit("No records yet. Run `tapewatch classify` first.")
    print(metrics.summarize(records).render())


def main() -> None:
    parser = argparse.ArgumentParser(prog="tapewatch")
    sub = parser.add_subparsers(required=True)

    i = sub.add_parser("ingest", help="fetch source events to disk (no model)")
    i.add_argument("--source", choices=("edgar", "news"), default="edgar")
    i.add_argument("--form", default="8-K", help="edgar only")
    i.add_argument("--count", type=int, default=20)
    i.add_argument(
        "--book-only",
        action="store_true",
        help="news only: fetch just the tickers in the book",
    )
    i.add_argument("--force", action="store_true", help="re-fetch cached events")
    i.set_defaults(func=cmd_ingest)

    r = sub.add_parser("resolve", help="map events to tickers and the book (free)")
    r.add_argument("--refresh", action="store_true", help="re-download SEC ticker index")
    r.set_defaults(func=cmd_resolve)

    b = sub.add_parser("baseline", help="rule-only classification (free)")
    b.set_defaults(func=cmd_baseline)

    c = sub.add_parser("classify", help="classify cached events with the model")
    c.add_argument("--limit", type=int, default=10)
    c.add_argument("--route", action="store_true", help="cheap model first, escalate when unsure")
    c.add_argument(
        "--in-book-only",
        action="store_true",
        help="only classify events touching a held position",
    )
    c.set_defaults(func=cmd_classify)

    m = sub.add_parser("metrics", help="cost, latency, and routing summary")
    m.set_defaults(func=cmd_metrics)

    args = parser.parse_args()
    args.func(args)
