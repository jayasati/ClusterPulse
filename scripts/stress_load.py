"""Stress-load generator: simulate a fleet of Agents against one Collector.

Ramps through fleet sizes, each step running a swarm of virtual agents
that POST realistic (but sub-threshold) metrics payloads on a fixed
interval, and reports per-step acceptance counts and latency percentiles.

Usage (run from a host that can reach the Collector, e.g. an agent node):

    python stress_load.py --url http://COLLECTOR:8000 --token TOKEN \
        --steps 10,25,50,100 --duration 45 --interval 5

Safety notes:
- Virtual node_ids are prefixed ``stress-`` so their rows are easy to
  delete afterwards:
      DELETE FROM metric_samples WHERE node_id LIKE 'stress-%';
      DELETE FROM nodes WHERE node_id LIKE 'stress-%';
- Metric values are far below every shipped alert threshold, so the run
  opens no alerts — but if staleness alerting is enabled, disable it (or
  clean up within the stale window) or every virtual node will page when
  the run stops.
- Never point this at a production fleet token.
"""

import argparse
import asyncio
import statistics
import sys
import time
from datetime import datetime, timezone

import httpx

PAYLOAD_SAMPLES = [
    {"metric_type": "cpu.usage_percent", "value": 12.5, "unit": "percent"},
    {"metric_type": "memory.usage_percent", "value": 41.0, "unit": "percent"},
    {"metric_type": "disk.usage_percent", "value": 33.0, "unit": "percent"},
    {"metric_type": "network.bytes_sent", "value": 1024.0, "unit": "bytes"},
    {"metric_type": "network.bytes_recv", "value": 2048.0, "unit": "bytes"},
]


async def _virtual_agent(
    client: httpx.AsyncClient,
    url: str,
    node_id: str,
    interval: float,
    stop_at: float,
    results: list[tuple[float, int]],
) -> None:
    while time.monotonic() < stop_at:
        payload = {
            "node_id": node_id,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "samples": PAYLOAD_SAMPLES,
            "collection_errors": [],
        }
        started = time.perf_counter()
        try:
            response = await client.post(f"{url}/api/v1/metrics", json=payload)
            results.append((time.perf_counter() - started, response.status_code))
        except httpx.HTTPError:
            results.append((time.perf_counter() - started, 0))
        await asyncio.sleep(interval)


def _percentile(latencies: list[float], pct: float) -> float:
    if not latencies:
        return 0.0
    ordered = sorted(latencies)
    index = min(int(len(ordered) * pct / 100), len(ordered) - 1)
    return ordered[index]


async def _run_step(
    url: str, token: str, agents: int, duration: float, interval: float
) -> None:
    results: list[tuple[float, int]] = []
    stop_at = time.monotonic() + duration
    limits = httpx.Limits(max_connections=agents)
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=10.0, limits=limits) as client:
        await asyncio.gather(
            *(
                _virtual_agent(
                    client, url, f"stress-{n:04d}", interval, stop_at, results
                )
                for n in range(agents)
            )
        )
    latencies = [latency for latency, _ in results]
    ok = sum(1 for _, code in results if code == 200)
    errors = {
        code: sum(1 for _, c in results if c == code)
        for code in {c for _, c in results if c != 200}
    }
    print(
        f"agents={agents:4d}  requests={len(results):5d}  ok={ok:5d}  "
        f"errors={errors or 'none'}  "
        f"p50={_percentile(latencies, 50) * 1000:7.1f}ms  "
        f"p95={_percentile(latencies, 95) * 1000:7.1f}ms  "
        f"p99={_percentile(latencies, 99) * 1000:7.1f}ms  "
        f"mean={statistics.fmean(latencies) * 1000 if latencies else 0:7.1f}ms",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--steps", default="10,25,50,100")
    parser.add_argument("--duration", type=float, default=45.0)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()

    for step in (int(s) for s in args.steps.split(",")):
        asyncio.run(_run_step(args.url, args.token, step, args.duration, args.interval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
