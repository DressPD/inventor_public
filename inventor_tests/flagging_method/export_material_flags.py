from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from inventor_tests._utils import safe_float as _safe_float

ROOT = Path(__file__).resolve().parent.parent
INTERNAL_DIR = ROOT.parent / "sample_artifacts"


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _flag_row(row: dict[str, str]) -> dict[str, Any]:
    fill_gain_vs_sap = _safe_float(row.get("fill_gain_vs_sap_pct_pts"))
    fill_gain_vs_universal = _safe_float(row.get("fill_gain_vs_universal_rq_pct_pts"))
    stockout_gain_vs_sap = _safe_float(row.get("stockout_days_reduction_vs_sap"))
    cost_delta_vs_universal = _safe_float(row.get("cost_delta_vs_universal_rq"))
    opportunity_score = _safe_float(row.get("opportunity_score"))
    route = row.get("route_used") or ""
    hard_flag = row.get("hard_escalation_flag") == "YES"
    thin_delivery = int(float(row.get("delivery_observations") or 0)) < 10
    boundary_risk = row.get("boundary_risk") or ""

    # Threshold rationale:
    # fill_gain > 1 pp: minimum meaningful service improvement over SAP baseline
    #   (1 pp chosen to exceed measurement noise in 250-day backtests)
    # stockout_gain >= 2 days: at least one full working week improvement
    # thin_delivery < 10: fewer than 10 observed lead-time events means LT statistics
    #   are unreliable; manual review is cheaper than a mis-parameterised policy
    # routes (s,S) / NB branch: non-standard solver paths need human sign-off before
    #   production deployment because they carry higher parameter sensitivity
    # opportunity_score >= 10 for HIGH within LLM_REVIEW: score is
    #   fill_gain_vs_sap * stockout_gain_vs_sap + fill_gain_vs_universal;
    #   10 corresponds to ~3 pp fill gain with ~3 fewer stockout days

    reasons: list[str] = []
    if fill_gain_vs_sap > 1.0:
        reasons.append("service_gain_vs_sap")
    if fill_gain_vs_universal > 0.0:
        reasons.append("beats_universal_rq")
    if stockout_gain_vs_sap >= 2.0:
        reasons.append("stockout_reduction_vs_sap")
    if hard_flag:
        reasons.append("hard_flag")
    if thin_delivery:
        reasons.append("thin_delivery_data")
    if route == "(s,S)":
        reasons.append("order_up_to_case")
    if route in {"NB branch", "negbin"}:
        reasons.append("distributional_branch_case")
    if cost_delta_vs_universal > 0.0:
        reasons.append("cost_premium_vs_universal_rq")

    isolate = (
        fill_gain_vs_sap > 1.0
        or stockout_gain_vs_sap >= 2.0
        or hard_flag
        or thin_delivery
        or route in {"(s,S)", "NB branch", "negbin"}
    )

    if isolate and (
        hard_flag
        or route in {"(s,S)", "NB branch", "negbin"}
        or (fill_gain_vs_sap > 1.0 and stockout_gain_vs_sap >= 2.0)
        or (fill_gain_vs_universal > 0.0 and cost_delta_vs_universal <= 0.0)
    ):
        bucket = "OPTIMIZE_NOW"
        priority = "HIGH"
        question = "What operational constraint could still block implementation despite apparent service gain?"
    elif isolate:
        bucket = "LLM_REVIEW"
        priority = "HIGH" if opportunity_score >= 10 else "MEDIUM"
        question = "Which counterfactual or hidden constraint should be reviewed before optimizing this material?"
    elif fill_gain_vs_sap > 0.0 or boundary_risk == "HIGH":
        bucket = "MONITOR"
        priority = "MEDIUM"
        question = "Should this item stay under observation for lead time or service deterioration?"
    else:
        bucket = "LEAVE_BASELINE"
        priority = "LOW"
        question = "Is there any evidence this item needs intervention beyond routine monitoring?"

    return {
        "flag_bucket": bucket,
        "llm_review_priority": priority,
        "flag_reasons": "|".join(reasons),
        "llm_question": question,
    }


def export_material_flags(input_csv: Path, output_csv: Path, output_jsonl: Path) -> dict[str, Any]:
    rows = _load_rows(input_csv)
    output_rows: list[dict[str, Any]] = []
    bucket_counts: dict[str, int] = {}
    top_optimize_now: list[str] = []

    for row in rows:
        flag = _flag_row(row)
        out = {**row, **flag}
        output_rows.append(out)
        bucket = flag["flag_bucket"]
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        if bucket == "OPTIMIZE_NOW" and len(top_optimize_now) < 10:
            top_optimize_now.append(row.get("item_key", ""))

    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)

    with output_jsonl.open("w", encoding="utf-8") as fh:
        for row in output_rows:
            payload = {
                "item_key": row.get("item_key"),
                "flag_bucket": row.get("flag_bucket"),
                "llm_review_priority": row.get("llm_review_priority"),
                "llm_question": row.get("llm_question"),
                "flag_reasons": (row.get("flag_reasons") or "").split("|") if row.get("flag_reasons") else [],
                "structured_context": {
                    "plant_code": row.get("plant_code"),
                    "material_id": row.get("material_id"),
                    "route_used": row.get("route_used"),
                    "selected_model": row.get("selected_model"),
                    "hard_escalation_flag": row.get("hard_escalation_flag"),
                    "hard_reason_codes": row.get("hard_reason_codes"),
                    "delivery_observations": row.get("delivery_observations"),
                    "lead_time_stability": row.get("lead_time_stability"),
                    "supplier_reliability": row.get("supplier_reliability"),
                    "fill_gain_vs_sap_pct_pts": row.get("fill_gain_vs_sap_pct_pts"),
                    "fill_gain_vs_universal_rq_pct_pts": row.get("fill_gain_vs_universal_rq_pct_pts"),
                    "stockout_days_reduction_vs_sap": row.get("stockout_days_reduction_vs_sap"),
                    "cost_delta_vs_universal_rq": row.get("cost_delta_vs_universal_rq"),
                    "opportunity_score": row.get("opportunity_score"),
                },
            }
            fh.write(json.dumps(payload) + "\n")

    return {
        "input_csv": str(input_csv),
        "output_csv": str(output_csv),
        "output_jsonl": str(output_jsonl),
        "rows": len(output_rows),
        "bucket_counts": bucket_counts,
        "top_optimize_now": top_optimize_now,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export deterministic material flags.")
    parser.add_argument("--input", default=str(INTERNAL_DIR / "target_ranking.csv"))
    parser.add_argument("--output-csv", default=str(INTERNAL_DIR / "material_flags.csv"))
    parser.add_argument("--output-jsonl", default=str(INTERNAL_DIR / "material_flags.jsonl"))
    args = parser.parse_args()
    res = export_material_flags(Path(args.input), Path(args.output_csv), Path(args.output_jsonl))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
