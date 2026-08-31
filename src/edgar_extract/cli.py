"""Entry points: `edgar-extract poll` and `edgar-extract metrics`."""

from __future__ import annotations

import argparse

from . import metrics, store
from .extract import extract
from .fetch import EdgarClient


def cmd_poll(args: argparse.Namespace) -> None:
    client = EdgarClient()
    refs = client.recent(form_type=args.form, count=args.count)
    for ref in refs:
        text = client.document_text(ref)
        record = extract(ref, text)
        store.write(record)
        print(f"{ref.accession_number}  {record.extraction.event_type.value}  "
              f"${record.cost_usd:.4f}  {record.latency_ms}ms")


def cmd_metrics(_: argparse.Namespace) -> None:
    print(metrics.summarize(store.read_all()).render())


def main() -> None:
    parser = argparse.ArgumentParser(prog="edgar-extract")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("poll", help="fetch recent filings and extract")
    p.add_argument("--form", default="8-K")
    p.add_argument("--count", type=int, default=20)
    p.set_defaults(func=cmd_poll)

    m = sub.add_parser("metrics", help="cost and latency summary")
    m.set_defaults(func=cmd_metrics)

    args = parser.parse_args()
    args.func(args)
