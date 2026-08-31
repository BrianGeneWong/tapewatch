"""Aggregate the instrumentation carried on each ExtractionRecord.

Cost per filing and p50/p99 latency are the two numbers that belong in
the README. They are what separate this from a demo.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .schema import ExtractionRecord


@dataclass
class Summary:
    count: int
    total_cost_usd: float
    mean_cost_usd: float
    p50_latency_ms: float
    p99_latency_ms: float
    mean_input_tokens: float
    mean_output_tokens: float

    def render(self) -> str:
        return (
            f"filings            {self.count}\n"
            f"total cost         ${self.total_cost_usd:.4f}\n"
            f"cost per filing    ${self.mean_cost_usd:.4f}\n"
            f"latency p50        {self.p50_latency_ms:.0f} ms\n"
            f"latency p99        {self.p99_latency_ms:.0f} ms\n"
            f"tokens in / out    {self.mean_input_tokens:.0f} / {self.mean_output_tokens:.0f}"
        )


def summarize(records: list[ExtractionRecord]) -> Summary:
    if not records:
        raise ValueError("no records to summarize")
    latencies = sorted(r.latency_ms for r in records)
    costs = [r.cost_usd for r in records]
    return Summary(
        count=len(records),
        total_cost_usd=sum(costs),
        mean_cost_usd=statistics.mean(costs),
        p50_latency_ms=statistics.median(latencies),
        p99_latency_ms=latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)],
        mean_input_tokens=statistics.mean(r.input_tokens for r in records),
        mean_output_tokens=statistics.mean(r.output_tokens for r in records),
    )
