from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inventor_tests.orchestration.ensemble_runner import _extract_json_from_messages
from inventor_tests.orchestration.llm_api_client import (
    llm_chat,
    validate_credentials,
)
from inventor_tests.deterministic_method.hard_flag import evaluate_hard_flag
from inventor_tests.orchestration.run_ensemble_test import _group_key
from inventor_tests.deterministic_method.slt_calculator import compare_slt_vs_sap, compute_slt
from inventor_tests.deterministic_method.stats_calculator import compute_policy_values, compute_stats

CSV_PATH = str(Path(__file__).resolve().parents[1] / "data" / "20260619_400_Mat_2_plants.csv")
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "batches" / "decision_card_tests"


def load_csv(csv_path: str, group_by: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            item_key = _group_key(row, group_by)
            grouped.setdefault(item_key, []).append(dict(row))
    return grouped


def build_decision_card(item_key: str, stats: dict[str, Any], policy_values: dict[str, Any], slt: dict[str, Any], hard_flag: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_key": item_key,
        "identity": {
            "plant_code": stats.get("plant_code"),
            "material_id": stats.get("source_material_id") or stats.get("material_id"),
            "working_days": stats.get("working_days"),
            "delivery_observations": stats.get("delivery_observations"),
        },
        "demand_profile": {
            "regime": stats.get("regime"),
            "distribution_type": stats.get("distribution_type"),
            "mean_daily_demand": stats.get("mean_daily_demand"),
            "std_daily_demand": stats.get("std_daily_demand"),
            "mean_wd_demand": stats.get("mean_wd_demand"),
            "std_wd_demand": stats.get("std_wd_demand"),
            "cv_wd": stats.get("cv_wd"),
            "non_zero_fraction_wd": stats.get("non_zero_fraction_wd"),
            "overdispersion_index": stats.get("overdispersion_index"),
            "trend_flag": stats.get("trend_flag"),
            "d_max_wd": stats.get("d_max_wd"),
        },
        "lead_time_profile": {
            "mean_lead_time": stats.get("mean_lead_time"),
            "std_lead_time": stats.get("std_lead_time"),
            "cv_lead_time": stats.get("cv_lead_time"),
            "lead_time_stability": stats.get("lead_time_stability"),
            "effective_lead_time": stats.get("effective_lead_time"),
            "supplier_reliability": stats.get("supplier_reliability"),
        },
        "current_erp_state": {
            "current_safety_stock_units": stats.get("current_safety_stock_units"),
            "current_sap_slt_days": stats.get("current_sap_slt_days"),
        },
        "or_outputs": {
            "sigma_ltd": policy_values.get("sigma_ltd"),
            "safety_stock": policy_values.get("safety_stock"),
            "safety_stock_robust": policy_values.get("safety_stock_robust"),
            "reorder_point": policy_values.get("reorder_point"),
            "order_quantity": policy_values.get("order_quantity"),
            "annual_demand": policy_values.get("annual_demand"),
            "milp_trigger": policy_values.get("milp_trigger"),
        },
        "slt": {
            "recommended_days": slt.get("recommended_days"),
            "comparison_action": slt.get("comparison_action"),
            "dominant_factor": slt.get("dominant_factor"),
            "dominant_pct": slt.get("dominant_pct"),
            "override_flag": slt.get("override_flag"),
        },
        "governance": {
            "hard_escalation_flag": hard_flag.get("hard_escalation_flag"),
            "reason_codes": hard_flag.get("reason_codes"),
            "reasons": hard_flag.get("reasons"),
        },
    }


def build_prompt(item_key: str, decision_card: dict[str, Any]) -> str:
    schema = {
        "recommended_route": "one of: EOQ, (r,Q), (s,S), NB branch, Base-stock",
        "route_confidence": "one of: HIGH, MEDIUM, LOW",
        "constraint_hypotheses": [{
            "constraint_type": "lead_time_risk|service_risk|policy_feasibility|data_quality|supplier_reliability|planner_capacity",
            "severity": "HIGH|MEDIUM|LOW",
            "evidence": "exact numeric evidence from the decision card",
            "or_implication": "why this matters for OR policy choice or review",
        }],
        "data_quality_risks": ["list of concrete data quality concerns"],
        "service_risk": "1-2 sentence service-risk statement",
        "cost_risk": "1-2 sentence cost-risk statement",
        "needs_human_review": "YES|NO",
        "counterfactual_to_test": "one of: universal_rq, sap_static, eoq_pure, k_sigma, none",
        "planner_questions": ["2-4 concrete operational questions"],
        "erp_feasibility_note": "1-2 sentences about implementability in ERP/planning practice",
        "decision_summary": "short planner-facing summary",
    }
    return (
        "You are a constraint-aware OR decision card layer for realistic planner-facing inventory decisions.\n"
        "Use only the structured card below. Do not recompute formulas.\n"
        "Consider planner capacity, ERP implementability, supplier reliability, thin lead-time evidence, and service-cost trade-offs.\n"
        "Treat NB branch as a distributional parameterization branch, not a standalone optimization paradigm.\n"
        "Return only valid JSON matching this schema:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        f"Item key: {item_key}\n"
        f"Decision card:\n{json.dumps(decision_card, indent=2)}\n"
    )


def _fallback_llm_output(decision_card: dict[str, Any]) -> dict[str, Any]:
    demand = decision_card["demand_profile"]
    lt = decision_card["lead_time_profile"]
    gov = decision_card["governance"]
    slt = decision_card["slt"]
    if demand.get("regime") in {"Lumpy", "Intermittent"}:
        route = "NB branch"
    elif lt.get("lead_time_stability") == "Unstable":
        route = "(r,Q)"
    elif (demand.get("cv_wd") or 0) > 0.7:
        route = "(s,S)"
    else:
        route = "(r,Q)"
    return {
        "recommended_route": route,
        "route_confidence": "LOW" if gov.get("hard_escalation_flag") == "YES" else "MEDIUM",
        "constraint_hypotheses": [
            {
                "constraint_type": "service_risk",
                "severity": "MEDIUM",
                "evidence": f"regime={demand.get('regime')}, lead_time_stability={lt.get('lead_time_stability')}, slt_action={slt.get('comparison_action')}",
                "or_implication": "Use as governance placeholder until real LLM review is available.",
            }
        ],
        "data_quality_risks": ["Fallback output used; verify with real LLM review."],
        "service_risk": "Fallback estimate only.",
        "cost_risk": "Fallback estimate only.",
        "needs_human_review": "YES" if gov.get("hard_escalation_flag") == "YES" else "NO",
        "counterfactual_to_test": "universal_rq",
        "planner_questions": ["What hidden operational constraint may override the numeric recommendation?"],
        "erp_feasibility_note": "Fallback output only; confirm ERP implementability before action.",
        "decision_summary": "Governance placeholder only; rerun with valid LLM credentials.",
    }


def run_decision_card_test(item_key: str, rows: list[dict], api_key: str, bearer: str) -> dict[str, Any]:
    stats = compute_stats(item_key, rows)
    policy_values = compute_policy_values(stats)
    slt = compute_slt(stats)
    slt["comparison_action"] = compare_slt_vs_sap(stats, slt)
    hard_flag = evaluate_hard_flag(stats, policy_values, slt)
    decision_card = build_decision_card(item_key, stats, policy_values, slt, hard_flag)
    try:
        response_text = llm_chat(build_prompt(item_key, decision_card), api_key=api_key)
        parsed = _extract_json_from_messages(response_text)
        if not isinstance(parsed, dict):
            raise ValueError("LLM did not return a valid JSON object")
        return {
            "item_key": item_key,
            "status": "ok",
            "decision_card": decision_card,
            "llm_decision": parsed,
            "llm_error": None,
        }
    except Exception as exc:
        return {
            "item_key": item_key,
            "status": "fallback_used",
            "decision_card": decision_card,
            "llm_decision": _fallback_llm_output(decision_card),
            "llm_error": str(exc),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run constraint decision card test.")
    parser.add_argument("--csv-path", default=CSV_PATH)
    parser.add_argument("--group-by", choices=["auto", "material", "plant-material"], default="plant-material")
    parser.add_argument("--item")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    api_key, bearer = validate_credentials()
    group_by = args.group_by
    if group_by == "auto":
        group_by = "plant-material"
    grouped = load_csv(args.csv_path, group_by)
    selected = [args.item] if args.item else list(grouped.keys())[: args.limit]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = []
    for item_key in selected:
        result = run_decision_card_test(item_key, grouped[item_key], api_key, bearer)
        (output_dir / f"{item_key}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        summaries.append({
            "item_key": item_key,
            "status": result["status"],
            "recommended_route": result["llm_decision"].get("recommended_route"),
            "needs_human_review": result["llm_decision"].get("needs_human_review"),
            "counterfactual_to_test": result["llm_decision"].get("counterfactual_to_test"),
        })
    print(json.dumps({"tested": len(selected), "items": summaries}, indent=2))


if __name__ == "__main__":
    main()
