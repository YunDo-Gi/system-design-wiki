"""
NaiveClient vs KnotClient 비교 부하 시험.

사용:
  uv run python scripts/compare_clients.py --scenario cache_effect --base-url http://localhost:8001
  uv run python scripts/compare_clients.py --scenario backoff_effect --base-url http://localhost:8001 --user-tier premium
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import time
from typing import Any

from client.naive import NaiveClient
from client.sdk import KnotClient


async def _run_cache_scenario(client_factory, base_url: str, api_key: str) -> dict[str, Any]:
    """같은 URL을 100번 shorten."""
    client = client_factory(base_url, api_key=api_key, user_tier="free")
    url = f"https://e.com/test-{secrets.token_hex(4)}"

    start = time.perf_counter()
    successes = 0
    rate_limited = 0
    for _ in range(100):
        result = await client.shorten(url)
        if hasattr(result, "code"):
            successes += 1
        else:
            rate_limited += 1
    elapsed = time.perf_counter() - start

    stats = {
        "successes": successes,
        "rate_limited": rate_limited,
        "total_seconds": round(elapsed, 2),
    }
    if hasattr(client, "cache_hits"):
        stats["cache_hits"] = client.cache_hits
        stats["server_calls"] = client.server_calls

    await client.aclose()
    return stats


async def _run_backoff_scenario(client_factory, base_url: str, api_key: str, user_tier: str) -> dict[str, Any]:
    """다른 URL 60번을 1초 간격으로."""
    client = client_factory(base_url, api_key=api_key, user_tier=user_tier)

    start = time.perf_counter()
    successes = 0
    rate_limited = 0
    for i in range(60):
        url = f"https://e.com/req-{i}"
        result = await client.shorten(url)
        if hasattr(result, "code"):
            successes += 1
        else:
            rate_limited += 1
        # 다음 호출까지 1초 대기 (전체 ~60s)
        await asyncio.sleep(1.0)
    elapsed = time.perf_counter() - start

    stats = {
        "successes": successes,
        "rate_limited": rate_limited,
        "total_seconds": round(elapsed, 2),
    }
    if hasattr(client, "backoff_waits"):
        stats["backoff_waits"] = client.backoff_waits
        stats["server_calls"] = client.server_calls

    await client.aclose()
    return stats


def _print_table(scenario: str, naive: dict, sdk: dict) -> None:
    print(f"\n=== Scenario: {scenario} ===")
    keys = sorted(set(naive.keys()) | set(sdk.keys()))
    print(f"{'metric':<25} {'NaiveClient':>15} {'KnotClient':>15}")
    print("-" * 60)
    for k in keys:
        n = naive.get(k, "-")
        s = sdk.get(k, "-")
        print(f"{k:<25} {str(n):>15} {str(s):>15}")


async def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", choices=["cache_effect", "backoff_effect", "both"], default="both")
    p.add_argument("--base-url", default="http://localhost:8001")
    p.add_argument("--user-tier", default="free")
    p.add_argument("--output", default=None, help="JSON 출력 경로")
    args = p.parse_args()

    results: dict[str, Any] = {}

    if args.scenario in ("cache_effect", "both"):
        naive_key = f"cache-naive-{secrets.token_hex(2)}"
        sdk_key = f"cache-sdk-{secrets.token_hex(2)}"
        naive_stats = await _run_cache_scenario(NaiveClient, args.base_url, naive_key)
        sdk_stats = await _run_cache_scenario(KnotClient, args.base_url, sdk_key)
        _print_table("cache_effect (same URL ×100)", naive_stats, sdk_stats)
        results["cache_effect"] = {"naive": naive_stats, "sdk": sdk_stats}

    if args.scenario in ("backoff_effect", "both"):
        naive_key = f"backoff-naive-{secrets.token_hex(2)}"
        sdk_key = f"backoff-sdk-{secrets.token_hex(2)}"
        naive_stats = await _run_backoff_scenario(NaiveClient, args.base_url, naive_key, args.user_tier)
        sdk_stats = await _run_backoff_scenario(KnotClient, args.base_url, sdk_key, args.user_tier)
        _print_table(f"backoff_effect (60 reqs spread, tier={args.user_tier})", naive_stats, sdk_stats)
        results["backoff_effect"] = {"naive": naive_stats, "sdk": sdk_stats}

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(json.dumps(results, indent=2))
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
