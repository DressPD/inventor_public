#!/usr/bin/env python3
"""Sensitivity analysis for inventOR backtest.

Runs the backtest simulator under six named scenarios varying shortage penalty,
service level, and budget, then writes a summary CSV.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from inventor_tests.deterministic_method.backtest_simulator import (
    load_grouped_rows,
    load_targets_policies,
    run_backtest,
)

INTERNAL_DIR = ROOT / "sample_artifacts"
CSV_PATH = ROOT / "inventor_tests" / "data" / "20260619_400_Mat_2_plants.csv"
TARGETS_CSV = INTERNAL_DIR / "target_ranking.csv"
OUTPUT_DIR = ROOT / "outputs" / "sensitivity"
SUMMARY_CSV = OUTPUT_DIR / "summary.csv"

TRAIN_CUTOFF = "2026-03-10"
VALID_END = "2026-06-19"

SCENARIOS: list[dict] = [
    {"name": "default",              "shortage_penalty_rate": 0.35},
    {"name": "low_shortage_penalty", "shortage_penalty_rate": 0.10},
    {"name": "high_shortage_penalty","shortage_penalty_rate": 0.75},
    {"name": "severe_shortage",      "shortage_penalty_rate": 1.50},
    {"name": "minimal_cost",         "shortage_penalty_rate": 0.05},
    {"name": "extreme_shortage",     "shortage_penalty_rate": 3.00},
]

POLICY_NAMES = ["inventor_selected", "universal_rq", "universal_ss", "sap_static", "eoq_pure"]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        print(f"Error: CSV not found: {CSV_PATH}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Loading {CSV_PATH}...", file=sys.stderr)
    grouped = load_grouped_rows(CSV_PATH)
    targets_policies = load_targets_policies(TARGETS_CSV)
    print(f"  {len(grouped)} pairs | {len(targets_policies)} target policies", file=sys.stderr)

    summary_rows: list[dict] = []
    all_results: dict = {}

    for scenario in SCENARIOS:
        name = scenario["name"]
        print(f"\n[{name}]", file=sys.stderr)
        result = run_backtest(
            grouped,
            TRAIN_CUTOFF,
            VALID_END,
            targets_policies=targets_policies,
            shortage_penalty_rate=scenario["shortage_penalty_rate"],
        )
        all_results[name] = {
            "scenario": scenario,
            "items_evaluated": result["items_evaluated"],
            "aggregate": result["aggregate"],
        }
        agg = result["aggregate"]
        for policy in POLICY_NAMES:
            ag = agg.get(policy, {})
            summary_rows.append({
                "scenario": name,
                "shortage_penalty_rate": scenario["shortage_penalty_rate"],
                "policy": policy,
                "mean_fill_rate_pct": ag.get("mean_fill_rate_pct", ""),
                "mean_total_cost": ag.get("mean_total_cost", ""),
                "mean_stockout_days": ag.get("mean_stockout_days", ""),
                "total_cost_sum": ag.get("total_cost_sum", ""),
                "pct_ge_95": ag.get("pct_ge_95", ""),
                "zero_stockout_pct": ag.get("zero_stockout_pct", ""),
            })
        inv_fill = agg.get("inventor_selected", {}).get("mean_fill_rate_pct", 0)
        sap_fill = agg.get("sap_static", {}).get("mean_fill_rate_pct", 0)
        print(
            f"  inventor_selected: fill={inv_fill:.2f}%  "
            f"sap_static: fill={sap_fill:.2f}%  "
            f"penalty={scenario['shortage_penalty_rate']}", file=sys.stderr
        )

    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as fh:
        fields = ["scenario", "shortage_penalty_rate", "policy",
                  "mean_fill_rate_pct", "mean_total_cost", "mean_stockout_days",
                  "total_cost_sum", "pct_ge_95", "zero_stockout_pct"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    (OUTPUT_DIR / "sensitivity_full.json").write_text(
        json.dumps(all_results, indent=2), encoding="utf-8"
    )
    print(f"\nWrote {SUMMARY_CSV}", file=sys.stderr)


if __name__ == "__main__":
    main()
