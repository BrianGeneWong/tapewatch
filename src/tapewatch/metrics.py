"""Aggregate the instrumentation carried on each EventRecord.

Cost per thousand events and p50/p99 latency are the numbers that
belong in the README. The routing split matters just as much: a policy
that escalates everything is not a routing policy, and the only way to
see that is to count.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from .schema import EventRecord


@dataclass
class Summary:
    count: int
    by_route: dict[str, int]
    total_cost_usd: float
    mean_cost_usd: float
    p50_latency_ms: float
    p99_latency_ms: float
    mean_input_tokens: float
    mean_output_tokens: float

    @property
    def cost_per_1k_usd(self) -> float:
        return self.mean_cost_usd * 1000

    def render(self) -> str:
        return (
            f"events             {self.count}\n"
            f"routes             "
            + ", ".join(f"{k}={v}" for k, v in sorted(self.by_route.items()))
            + "\n"
            f"total cost         ${self.total_cost_usd:.4f}\n"
            f"cost per event     ${self.mean_cost_usd:.4f}\n"
            f"cost per 1k        ${self.cost_per_1k_usd:.2f}\n"
            f"latency p50        {self.p50_latency_ms:.0f} ms\n"
            f"latency p99        {self.p99_latency_ms:.0f} ms\n"
            f"tokens in / out    {self.mean_input_tokens:.0f} / {self.mean_output_tokens:.0f}"
        )


def summarize(records: list[EventRecord]) -> Summary:
    if not records:
        raise ValueError("no records to summarize")
    latencies = sorted(r.latency_ms for r in records)
    costs = [r.cost_usd for r in records]
    by_route: dict[str, int] = {}
    for r in records:
        by_route[r.route] = by_route.get(r.route, 0) + 1

    return Summary(
        count=len(records),
        by_route=by_route,
        total_cost_usd=sum(costs),
        mean_cost_usd=statistics.mean(costs),
        p50_latency_ms=statistics.median(latencies),
        p99_latency_ms=latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)],
        mean_input_tokens=statistics.mean(r.input_tokens for r in records),
        mean_output_tokens=statistics.mean(r.output_tokens for r in records),
    )
