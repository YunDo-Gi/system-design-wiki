# experiments/knot/scripts/report.py
"""k6 JSON 결과를 받아 마크다운 리포트 + matplotlib PNG 차트 생성.

사용:
    uv run python scripts/report.py \
        --k6-json out/token_bucket.json \
        --algorithm token_bucket \
        --output reports/token_bucket.md
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt


def load_k6_json(path: Path) -> pd.DataFrame:
    """k6 --out json은 NDJSON 형식 (한 줄에 한 metric point)."""
    rows = []
    with path.open() as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("type") == "Point":
                rows.append({
                    "metric": obj["metric"],
                    "time": pd.to_datetime(obj["data"]["time"]),
                    "value": obj["data"]["value"],
                    "scenario": obj["data"].get("tags", {}).get("scenario", "unknown"),
                    "status": obj["data"].get("tags", {}).get("status", ""),
                })
    return pd.DataFrame(rows)


def chart_pass_deny_timeseries(df: pd.DataFrame, out: Path) -> None:
    """시간버킷별 통과(2xx,3xx)·거부(429) 카운트 stacked bar."""
    http_reqs = df[df["metric"] == "http_reqs"].copy()
    http_reqs["bucket"] = http_reqs["time"].dt.floor("s")
    http_reqs["result"] = http_reqs["status"].apply(
        lambda s: "denied" if s == "429" else "passed"
    )
    pivot = http_reqs.groupby(["bucket", "result"]).size().unstack(fill_value=0)
    if "passed" not in pivot.columns:
        pivot["passed"] = 0
    if "denied" not in pivot.columns:
        pivot["denied"] = 0

    ax = pivot[["passed", "denied"]].plot(
        kind="bar", stacked=True, color=["#4caf50", "#f44336"], figsize=(12, 4)
    )
    ax.set_title("Requests over time (passed vs denied)")
    ax.set_xlabel("time (second)")
    ax.set_ylabel("requests")
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()


def chart_scenario_summary(df: pd.DataFrame) -> str:
    """시나리오별 통과율·p50/p95 지연 표 (마크다운)."""
    http_reqs = df[df["metric"] == "http_reqs"]
    summary = http_reqs.groupby("scenario").agg(
        total=("value", "count"),
        denied=("status", lambda s: (s == "429").sum()),
    )
    summary["pass_rate"] = (1 - summary["denied"] / summary["total"]) * 100

    duration = df[df["metric"] == "http_req_duration"].groupby("scenario")["value"]
    summary["p50_ms"] = duration.quantile(0.50).round(1)
    summary["p95_ms"] = duration.quantile(0.95).round(1)

    return summary.to_markdown()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--k6-json", required=True, type=Path)
    p.add_argument("--algorithm", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    df = load_k6_json(args.k6_json)
    if df.empty:
        raise SystemExit(f"no data in {args.k6_json}")

    chart_dir = args.output.parent
    chart_dir.mkdir(parents=True, exist_ok=True)
    timeseries_png = chart_dir / f"{args.algorithm}_timeseries.png"
    chart_pass_deny_timeseries(df, timeseries_png)

    summary_table = chart_scenario_summary(df)

    md = f"""# {args.algorithm} — 부하 시험 결과

> k6 시나리오 3종(burst·ramp·cycle) 결과. 알고리즘 비교는 cycle 2 이후 cross-link.

## 시간축별 통과/거부

![timeseries]({timeseries_png.name})

## 시나리오별 요약

{summary_table}

---

생성: `uv run python scripts/report.py --k6-json {args.k6_json} --algorithm {args.algorithm} --output {args.output}`
"""
    args.output.write_text(md)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
