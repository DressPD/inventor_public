from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from inventor_tests._utils import safe_float as _safe_float

_ROOT = Path(__file__).resolve().parents[1]
_RESULTS_DIR = _ROOT.parent / "results"
_REVIEW_OUTPUT_DIR = _ROOT.parent / "outputs" / "review_flags"
_INTERNAL_DIR = _ROOT.parent / "sample_artifacts"
TARGETS_CSV = _INTERNAL_DIR / "target_ranking.csv"
FLAGS_CSV = _INTERNAL_DIR / "material_flags.csv"
REVIEWED_CSV = _INTERNAL_DIR / "reviewed_flags.csv"
OUTPUT_JSON = _INTERNAL_DIR / "targeted_evaluation.json"
OUTPUT_CSV = _RESULTS_DIR / "targeted_evaluation.csv"


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path.name


def _merge_rows(targets: list[dict[str, str]], flags: list[dict[str, str]], reviewed: list[dict[str, str]]) -> list[dict[str, str]]:
    flag_map = {row["item_key"]: row for row in flags if row.get("item_key")}
    review_map = {row["item_key"]: row for row in reviewed if row.get("item_key")}
    merged = []
    for row in targets:
        item_key = row["item_key"]
        merged.append({**row, **{f"flag_{k}": v for k, v in flag_map.get(item_key, {}).items()}, **{f"review_{k}": v for k, v in review_map.get(item_key, {}).items()}})
    return merged


def _strategy_selected(row: dict[str, str], strategy: str) -> bool:
    if strategy == "sap_only":
        return False
    if strategy == "inventor_all":
        return True
    if strategy == "deterministic_optimize_now":
        return row.get("flag_flag_bucket") == "OPTIMIZE_NOW"
    if strategy == "deterministic_optimize_or_review":
        return row.get("flag_flag_bucket") in {"OPTIMIZE_NOW", "LLM_REVIEW"}
    if strategy == "ml_stump_opportunity_score":
        return _safe_float(row.get("opportunity_score")) >= 2.40975
    if strategy == "llm_optimize_now":
        return row.get("review_final_bucket") == "OPTIMIZE_NOW"
    if strategy == "llm_optimize_or_review":
        return row.get("review_final_bucket") in {"OPTIMIZE_NOW", "LLM_REVIEW"}
    raise ValueError(f"Unknown strategy: {strategy}")


def _governed_candidate(row: dict[str, str]) -> bool:
    review_bucket = row.get("review_final_bucket")
    if review_bucket:
        return review_bucket in {"OPTIMIZE_NOW", "LLM_REVIEW"}
    return row.get("flag_flag_bucket") in {"OPTIMIZE_NOW", "LLM_REVIEW"}


def _cost_aware_choice(row: dict[str, str], strategy: str) -> str:
    if strategy != "governed_cost_aware_service_floor":
        return "inventor" if _strategy_selected(row, strategy) else "sap"
    if not _governed_candidate(row):
        return "sap"

    sap_fill = _safe_float(row.get("sap_fill_rate_pct"))
    sap_cost = _safe_float(row.get("sap_total_cost"))
    candidates = [
        ("sap", sap_fill, sap_cost),
        ("inventor", _safe_float(row.get("inventor_fill_rate_pct")), _safe_float(row.get("inventor_total_cost"))),
        ("universal_rq", _safe_float(row.get("universal_rq_fill_rate_pct")), _safe_float(row.get("universal_rq_total_cost"))),
    ]
    feasible = [candidate for candidate in candidates if candidate[1] >= sap_fill]
    return min(feasible, key=lambda candidate: candidate[2] - 1000.0 * max(candidate[1] - sap_fill, 0.0))[0]


def _evaluate(rows: list[dict[str, str]], strategy: str) -> dict[str, Any]:
    choices = [_cost_aware_choice(row, strategy) for row in rows]
    fill_rates = []
    total_costs = []
    fill_gain_vs_sap = []
    cost_delta_vs_sap = []
    stockout_reduction = []
    for row, choice in zip(rows, choices):
        inv_fill = _safe_float(row.get("inventor_fill_rate_pct"))
        sap_fill = _safe_float(row.get("sap_fill_rate_pct"))
        rq_fill = _safe_float(row.get("universal_rq_fill_rate_pct"))
        inv_cost = _safe_float(row.get("inventor_total_cost"))
        sap_cost = _safe_float(row.get("sap_total_cost"))
        rq_cost = _safe_float(row.get("universal_rq_total_cost"))
        if choice == "inventor":
            fill, cost = inv_fill, inv_cost
            stockout = _safe_float(row.get("stockout_days_reduction_vs_sap"))
        elif choice == "universal_rq":
            fill, cost = rq_fill, rq_cost
            stockout = 0.0
        else:
            fill, cost = sap_fill, sap_cost
            stockout = 0.0
        fill_rates.append(fill)
        total_costs.append(cost)
        fill_gain_vs_sap.append(fill - sap_fill)
        cost_delta_vs_sap.append(cost - sap_cost)
        stockout_reduction.append(stockout)
    n = len(rows)
    selected = sum(1 for value in choices if value != "sap")
    return {
        "strategy": strategy,
        "n_items": n,
        "selected_items": selected,
        "selected_pct": round(100.0 * selected / n, 2) if n else 0.0,
        "sap_choices": choices.count("sap"),
        "inventor_choices": choices.count("inventor"),
        "universal_rq_choices": choices.count("universal_rq"),
        "mean_fill_rate_pct": round(sum(fill_rates) / n, 4) if n else 0.0,
        "mean_total_cost": round(sum(total_costs) / n, 4) if n else 0.0,
        "mean_fill_gain_vs_sap_pct_pts": round(sum(fill_gain_vs_sap) / n, 4) if n else 0.0,
        "mean_cost_delta_vs_sap": round(sum(cost_delta_vs_sap) / n, 4) if n else 0.0,
        "total_stockout_days_reduction_vs_sap": round(sum(stockout_reduction), 4),
    }


def evaluate_targeted_improvement(targets_csv: Path, flags_csv: Path, reviewed_csv: Path, output_json: Path, output_csv: Path) -> dict[str, Any]:
    rows = _merge_rows(_load_csv(targets_csv), _load_csv(flags_csv), _load_csv(reviewed_csv))
    strategies = [
        "sap_only",
        "inventor_all",
        "deterministic_optimize_now",
        "deterministic_optimize_or_review",
        "ml_stump_opportunity_score",
        "llm_optimize_now",
        "llm_optimize_or_review",
        "governed_cost_aware_service_floor",
    ]
    results = [_evaluate(rows, strategy) for strategy in strategies]
    summary = {
        "targets_csv": _display_path(targets_csv),
        "flags_csv": _display_path(flags_csv),
        "reviewed_csv": _display_path(reviewed_csv),
        "rows": len(rows),
        "caveat": "Uses paper-grade per-item SAP, InventOR, and universal (r,Q) columns. Governed cost-aware selection only considers LLM-reviewed OPTIMIZE_NOW or LLM_REVIEW rows, requires candidate fill rate to meet or beat SAP per item, and does not use raw simulator reruns.",
        "strategies": results,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(results[0].keys()) if results else ["strategy"])
        writer.writeheader()
        writer.writerows(results)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate targeted optimization strategies against SAP baseline.")
    parser.add_argument("--targets-csv", default=str(TARGETS_CSV))
    parser.add_argument("--flags-csv", default=str(FLAGS_CSV))
    parser.add_argument("--reviewed-csv", default=str(REVIEWED_CSV))
    parser.add_argument("--output-json", default=str(OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    args = parser.parse_args()
    summary = evaluate_targeted_improvement(
        Path(args.targets_csv),
        Path(args.flags_csv),
        Path(args.reviewed_csv),
        Path(args.output_json),
        Path(args.output_csv),
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
