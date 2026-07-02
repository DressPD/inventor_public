"""Budget allocator for inventOR material flags.

Given a fixed change budget B (max items to optimise in one cycle),
ranks materials by opportunity_score and allocates greedily.
Also runs three comparison baselines: ABC-value, stockout-only, random.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path
from typing import Any

from inventor_tests._utils import safe_float as _f

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT.parent / "results"
DEFAULT_TARGETS = ROOT.parent / "sample_artifacts" / "target_ranking.csv"
DEFAULT_OUTPUT_JSON = ROOT.parent / "sample_artifacts" / "budget_allocation.json"
DEFAULT_OUTPUT_CSV = ROOT.parent / "sample_artifacts" / "budget_allocation.csv"


def _load(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _total_gain(selected_keys: set[str], rows_by_key: dict[str, dict[str, str]]) -> dict[str, float]:
    fill_gain = sum(_f(rows_by_key[k].get("fill_gain_vs_sap_pct_pts")) for k in selected_keys)
    stockout_gain = sum(_f(rows_by_key[k].get("stockout_days_reduction_vs_sap")) for k in selected_keys)
    shortage_gain = sum(_f(rows_by_key[k].get("shortage_reduction_vs_sap")) for k in selected_keys)
    return {
        "total_fill_gain_pct_pts": round(fill_gain, 4),
        "total_stockout_days_gain": round(stockout_gain, 4),
        "total_shortage_units_gain": round(shortage_gain, 4),
        "n_selected": len(selected_keys),
    }


def greedy_opportunity(rows: list[dict[str, str]], budget: int) -> list[str]:
    eligible = [r for r in rows if r.get("isolate_for_optimization") == "YES"]
    ranked = sorted(eligible, key=lambda r: _f(r.get("opportunity_score")), reverse=True)
    return [r["item_key"] for r in ranked[:budget]]


def greedy_abc_value(rows: list[dict[str, str]], budget: int) -> list[str]:
    """Prioritise by annual unit value (unit_cost × mean_daily_demand × 252)."""
    eligible = [r for r in rows if r.get("isolate_for_optimization") == "YES"]
    ranked = sorted(
        eligible,
        key=lambda r: _f(r.get("unit_cost", 0)) * _f(r.get("mean_daily_demand", 0)) * 252.0,
        reverse=True,
    )
    return [r["item_key"] for r in ranked[:budget]]


def greedy_stockout(rows: list[dict[str, str]], budget: int) -> list[str]:
    eligible = [r for r in rows if r.get("isolate_for_optimization") == "YES"]
    ranked = sorted(eligible, key=lambda r: _f(r.get("stockout_days_reduction_vs_sap")), reverse=True)
    return [r["item_key"] for r in ranked[:budget]]


def random_baseline(rows: list[dict[str, str]], budget: int, seed: int = 42) -> list[str]:
    eligible = [r for r in rows if r.get("isolate_for_optimization") == "YES"]
    rng = random.Random(seed)
    return [r["item_key"] for r in rng.sample(eligible, min(budget, len(eligible)))]


def allocate(targets_csv: Path, budget: int, output_json: Path, output_csv: Path) -> dict[str, Any]:
    rows = _load(targets_csv)
    rows_by_key = {r["item_key"]: r for r in rows}
    n_eligible = sum(1 for r in rows if r.get("isolate_for_optimization") == "YES")

    methods = {
        "greedy_opportunity": greedy_opportunity(rows, budget),
        "greedy_abc_value":   greedy_abc_value(rows, budget),
        "greedy_stockout":    greedy_stockout(rows, budget),
        "random_baseline":    random_baseline(rows, budget),
    }

    results: list[dict[str, Any]] = []
    for name, selected in methods.items():
        gains = _total_gain(set(selected), rows_by_key)
        results.append({"method": name, "selected_items": selected, **gains})

    summary = {
        "targets_csv": str(targets_csv),
        "total_items": len(rows),
        "eligible_items": n_eligible,
        "budget": budget,
        "methods": results,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        fields = ["method", "n_selected", "total_fill_gain_pct_pts",
                  "total_stockout_days_gain", "total_shortage_units_gain"]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fields})

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Allocate change budget across inventOR flags.")
    parser.add_argument("--targets-csv", default=str(DEFAULT_TARGETS))
    parser.add_argument("--budget", type=int, default=20,
                        help="Maximum number of materials to optimise in one cycle")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(DEFAULT_OUTPUT_CSV))
    args = parser.parse_args()
    summary = allocate(
        Path(args.targets_csv), args.budget,
        Path(args.output_json), Path(args.output_csv),
    )
    print(json.dumps({
        "eligible_items": summary["eligible_items"],
        "budget": summary["budget"],
        "method_gains": [
            {k: r[k] for k in ("method", "n_selected", "total_fill_gain_pct_pts",
                                "total_stockout_days_gain")}
            for r in summary["methods"]
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
