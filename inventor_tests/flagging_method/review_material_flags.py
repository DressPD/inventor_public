from __future__ import annotations

import argparse
import concurrent.futures
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
from inventor_tests.orchestration.ensemble_aggregator import confidence_tier
from inventor_tests.orchestration.llm_api_client import llm_chat, validate_credentials

ROOT = Path(__file__).resolve().parents[1]
INTERNAL_DIR = ROOT.parent / "sample_artifacts"
REVIEW_OUTPUT_DIR = ROOT.parent / "outputs" / "review_flags"
INPUT_JSONL = INTERNAL_DIR / "material_flags.jsonl"
OUTPUT_JSONL = REVIEW_OUTPUT_DIR / "reviewed_flags.jsonl"
OUTPUT_CSV = REVIEW_OUTPUT_DIR / "reviewed_flags.csv"
DEFAULT_REVIEW_N_RUNS = 5
DEFAULT_REVIEW_MAX_WORKERS = 5
LLM_REVIEW_RETRIES = 3

_REVIEW_VALID_SETS = {
    "final_bucket": ["OPTIMIZE_NOW", "LLM_REVIEW", "MONITOR", "LEAVE_BASELINE"],
    "review_confidence": ["HIGH", "MEDIUM", "LOW"],
    "route_to_code": ["optimize_policy", "rerun_counterfactual", "request_planner_review", "request_supplier_review", "keep_baseline"],
    "counterfactual_priority": ["universal_rq", "sap_static", "eoq_pure", "k_sigma", "none"],
    "requires_planner_contact": ["YES", "NO"],
    "requires_supplier_contact": ["YES", "NO"],
}


def _sanitize_error(error: str) -> str:
    text = (error or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in ("httpsconnectionpool", "proxyerror", "ssl")):
        return "LLM request failed before a valid response was received."
    return text.splitlines()[0][:300] if text else "LLM request failed."


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _rows_from_reviewed_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load_planner_notes(path: Path | None) -> dict[str, str]:
    if not path or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        return {row.get("item_key", ""): row.get("planner_note", "") for row in csv.DictReader(fh) if row.get("item_key")}


def _build_prompt(record: dict[str, Any]) -> str:
    schema = {
        "final_bucket": "one of: OPTIMIZE_NOW, LLM_REVIEW, MONITOR, LEAVE_BASELINE",
        "review_confidence": "one of: HIGH, MEDIUM, LOW",
        "route_to_code": "one of: optimize_policy, rerun_counterfactual, request_planner_review, request_supplier_review, keep_baseline",
        "code_task": "one concrete task the Python layer should run next",
        "or_rationale": "2-4 sentences grounded in exact numeric fields",
        "hidden_constraints": [
            {
                "constraint_type": "planner_capacity|supplier_reliability|lead_time_evidence|service_risk|cost_tradeoff|erp_feasibility",
                "severity": "HIGH|MEDIUM|LOW",
                "evidence": "exact values from structured_context",
                "implication": "why this affects the intervention decision",
            }
        ],
        "counterfactual_priority": "one of: universal_rq, sap_static, eoq_pure, k_sigma, none",
        "recommended_next_action": "one short action sentence",
        "requires_planner_contact": "YES|NO",
        "requires_supplier_contact": "YES|NO",
        "notes": "optional short note",
    }
    planner_note = record.get("planner_note")
    prompt = (
        "You are the LLM review layer for InventOR material flagging.\n"
        "Interpret deterministic OR outputs. Do not recompute formulas.\n"
        "Prefer realistic operational judgment over optimistic claims.\n"
        "NB branch is a distributional parameterization branch, not a standalone optimization paradigm.\n"
        "Thin lead-time evidence, unstable lead time, hard flags, and NB-branch use must be discussed explicitly.\n"
        "Return only valid JSON with this schema:\n"
        f"{json.dumps(schema, indent=2)}\n\n"
        f"Record:\n{json.dumps(record, indent=2)}\n"
    )
    if planner_note:
        prompt += f"\nPlanner note:\n{planner_note}\nUse it as extra operational context, but cite it separately from numeric evidence.\n"
    return prompt


def _fallback_review(record: dict[str, Any], error: str) -> dict[str, Any]:
    ctx = record.get("structured_context") or {}
    safe_error = _sanitize_error(error)
    route = ctx.get("route_used") or ctx.get("selected_model") or ""
    hard_flag = ctx.get("hard_escalation_flag") == "YES"
    fill_gain_vs_sap = float(ctx.get("fill_gain_vs_sap_pct_pts") or 0.0)
    cost_delta_vs_universal = float(ctx.get("cost_delta_vs_universal_rq") or 0.0)
    if hard_flag or route in {"NB branch", "negbin", "(s,S)"}:
        final_bucket = "LLM_REVIEW"
        route_to_code = "request_planner_review"
    elif fill_gain_vs_sap > 1.0 and cost_delta_vs_universal <= 0.0:
        final_bucket = "OPTIMIZE_NOW"
        route_to_code = "optimize_policy"
    elif fill_gain_vs_sap > 0.0:
        final_bucket = "MONITOR"
        route_to_code = "rerun_counterfactual"
    else:
        final_bucket = "LEAVE_BASELINE"
        route_to_code = "keep_baseline"
    return {
        "final_bucket": final_bucket,
        "review_confidence": "LOW",
        "route_to_code": route_to_code,
        "code_task": "Fallback review used; rerun with valid LLM credentials.",
        "or_rationale": "Fallback review from deterministic signals only.",
        "hidden_constraints": [{
            "constraint_type": "lead_time_evidence",
            "severity": "MEDIUM",
            "evidence": f"hard_flag={ctx.get('hard_escalation_flag')}, route={route}",
            "implication": "Requires governed review before trusting optimization action.",
        }],
        "counterfactual_priority": "universal_rq",
        "recommended_next_action": "Review deterministic evidence before implementation.",
        "requires_planner_contact": "YES" if hard_flag else "NO",
        "requires_supplier_contact": "NO",
        "notes": safe_error,
    }


def _majority_vote(values: list[str | None], valid_set: list[str]) -> tuple[str, float]:
    filtered = [value for value in values if value in valid_set]
    if not filtered:
        return valid_set[0], 0.0
    counts = {value: filtered.count(value) for value in valid_set}
    winner = max(valid_set, key=lambda value: counts[value])
    return winner, counts[winner] / len(filtered)


def _merge_hidden_constraints(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for review in reviews:
        for constraint in review.get("hidden_constraints") or []:
            if not isinstance(constraint, dict):
                continue
            key = json.dumps(constraint, sort_keys=True)
            if key not in seen:
                seen.add(key)
                merged.append(constraint)
    return merged


def _pick_exemplar(reviews: list[dict[str, Any]], aggregated: dict[str, Any]) -> dict[str, Any]:
    for review in reviews:
        if review.get("final_bucket") == aggregated["final_bucket"] and review.get("route_to_code") == aggregated["route_to_code"]:
            return review
    return reviews[0]


def _combine_review_confidence(base_confidence: str | None, ensemble_confidence: str) -> str:
    ranking = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    inverse = {value: key for key, value in ranking.items()}
    base_rank = ranking.get(base_confidence or "LOW", 1)
    ensemble_rank = ranking.get(ensemble_confidence, 1)
    return inverse[min(base_rank, ensemble_rank)]


def _review_once(record: dict[str, Any], api_key: str, bearer: str) -> tuple[dict[str, Any], str | None, str]:
    last_error: str | None = None
    for _ in range(LLM_REVIEW_RETRIES):
        try:
            response_text = llm_chat(_build_prompt(record), api_key=api_key)
            payload = json.loads(response_text)
            parsed = _extract_json_from_messages(payload)
            if not isinstance(parsed, dict):
                raise ValueError("LLM did not return a valid JSON object")
            return parsed, None, "ok"
        except Exception as exc:
            last_error = _sanitize_error(str(exc))
    return _fallback_review(record, last_error or "LLM request failed."), last_error, "fallback_used"


def review_one(
    record: dict[str, Any],
    api_key: str,
    bearer: str,
    n_runs: int = DEFAULT_REVIEW_N_RUNS,
    max_workers: int = DEFAULT_REVIEW_MAX_WORKERS,
) -> tuple[dict[str, Any], str | None, str]:
    run_count = max(1, n_runs)
    worker_count = max(1, min(max_workers, run_count))
    raw_runs: list[tuple[dict[str, Any], str | None, str] | None] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(_review_once, record, api_key, bearer) for _ in range(run_count)]
        for future in concurrent.futures.as_completed(futures):
            try:
                raw_runs.append(future.result())
            except Exception as exc:
                safe_error = _sanitize_error(str(exc))
                raw_runs.append((_fallback_review(record, safe_error), safe_error, "fallback_used"))

    valid_runs = [review for review, _, status in raw_runs if review is not None and status == "ok"]
    if not valid_runs:
        last_error = next((error for _, error, _ in reversed(raw_runs) if error), "LLM request failed.")
        return _fallback_review(record, last_error), last_error, "fallback_used"

    aggregated: dict[str, Any] = {}
    agree_frac = 0.0
    for field, valid_set in _REVIEW_VALID_SETS.items():
        winner, field_agree_frac = _majority_vote([review.get(field) for review in valid_runs], valid_set)
        aggregated[field] = winner
        if field == "final_bucket":
            agree_frac = field_agree_frac

    ensemble_confidence = confidence_tier(agree_frac, len(valid_runs))
    exemplar = _pick_exemplar(valid_runs, aggregated)
    aggregated["code_task"] = exemplar.get("code_task")
    aggregated["or_rationale"] = exemplar.get("or_rationale")
    aggregated["recommended_next_action"] = exemplar.get("recommended_next_action")
    aggregated["notes"] = exemplar.get("notes")
    aggregated["hidden_constraints"] = _merge_hidden_constraints(valid_runs)
    aggregated["review_confidence"] = _combine_review_confidence(aggregated.get("review_confidence"), ensemble_confidence)
    aggregated["ensemble_n_runs"] = run_count
    aggregated["ensemble_n_valid"] = len(valid_runs)
    aggregated["ensemble_agreement_rate"] = round(agree_frac, 4)
    aggregated["ensemble_confidence"] = ensemble_confidence
    return aggregated, None, "ok"


def _csv_row(row: dict[str, Any]) -> dict[str, Any]:
    ctx = row.get("structured_context") or {}
    review = row.get("review") or {}
    return {
        "item_key": row.get("item_key"),
        "input_flag_bucket": row.get("input_flag_bucket"),
        "input_priority": row.get("input_priority"),
        "status": row.get("status"),
        "final_bucket": review.get("final_bucket"),
        "review_confidence": review.get("review_confidence"),
        "counterfactual_priority": review.get("counterfactual_priority"),
        "route_to_code": review.get("route_to_code"),
        "code_task": review.get("code_task"),
        "requires_planner_contact": review.get("requires_planner_contact"),
        "requires_supplier_contact": review.get("requires_supplier_contact"),
        "planner_note": row.get("planner_note"),
        "route_used": ctx.get("route_used"),
        "hard_escalation_flag": ctx.get("hard_escalation_flag"),
        "delivery_observations": ctx.get("delivery_observations"),
        "lead_time_stability": ctx.get("lead_time_stability"),
        "supplier_reliability": ctx.get("supplier_reliability"),
        "fill_gain_vs_sap_pct_pts": ctx.get("fill_gain_vs_sap_pct_pts"),
        "fill_gain_vs_universal_rq_pct_pts": ctx.get("fill_gain_vs_universal_rq_pct_pts"),
        "stockout_days_reduction_vs_sap": ctx.get("stockout_days_reduction_vs_sap"),
        "cost_delta_vs_universal_rq": ctx.get("cost_delta_vs_universal_rq"),
        "opportunity_score": ctx.get("opportunity_score"),
        "recommended_next_action": review.get("recommended_next_action"),
        "or_rationale": review.get("or_rationale"),
        "ensemble_n_runs": review.get("ensemble_n_runs"),
        "ensemble_n_valid": review.get("ensemble_n_valid"),
        "ensemble_agreement_rate": review.get("ensemble_agreement_rate"),
        "ensemble_confidence": review.get("ensemble_confidence"),
        "notes": review.get("notes"),
        "llm_error": row.get("llm_error"),
    }


def _fallback_row_for_header() -> dict[str, Any]:
    return _csv_row({"structured_context": {}, "review": {}, "item_key": "", "input_flag_bucket": "", "input_priority": "", "status": "", "llm_error": None})


def export_reviews(
    input_jsonl: Path,
    output_jsonl: Path,
    output_csv: Path,
    api_key: str,
    bearer: str,
    limit: int | None = None,
    planner_notes_csv: Path | None = None,
    n_runs: int = DEFAULT_REVIEW_N_RUNS,
    max_workers: int = DEFAULT_REVIEW_MAX_WORKERS,
) -> dict[str, Any]:
    rows = _load_jsonl(input_jsonl)
    if limit is not None:
        rows = rows[:limit]
    planner_notes = _load_planner_notes(planner_notes_csv)

    bucket_counts: dict[str, int] = {}
    fallback_count = 0
    top_items: list[str] = []
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_jsonl.open("w", encoding="utf-8") as out_jsonl, output_csv.open("w", newline="", encoding="utf-8") as out_csv:
        writer = csv.DictWriter(out_csv, fieldnames=list(_fallback_row_for_header().keys()))
        writer.writeheader()

        for idx, record in enumerate(rows, start=1):
            item_key = record.get("item_key", "")
            planner_note = planner_notes.get(item_key)
            if planner_note:
                record = dict(record)
                record["planner_note"] = planner_note

            review, llm_error, status = review_one(record, api_key, bearer, n_runs=n_runs, max_workers=max_workers)
            bucket = review.get("final_bucket", "LLM_REVIEW")
            bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            if status != "ok":
                fallback_count += 1
            if len(top_items) < 10:
                top_items.append(item_key)

            row = {
                "item_key": item_key,
                "input_flag_bucket": record.get("flag_bucket"),
                "input_priority": record.get("llm_review_priority"),
                "status": status,
                "review": review,
                "llm_error": llm_error,
                "planner_note": planner_note,
                "structured_context": record.get("structured_context") or {},
            }
            out_jsonl.write(json.dumps(row) + "\n")
            out_jsonl.flush()
            writer.writerow(_csv_row(row))
            out_csv.flush()
            print(f"[{idx}/{len(rows)}] {item_key} {status} -> {bucket}", flush=True)

    return {
        "reviewed": len(rows),
        "bucket_counts": bucket_counts,
        "fallback_count": fallback_count,
        "ensemble_n_runs": n_runs,
        "top_items": top_items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Review material flags via LLM or deterministic fallback.")
    parser.add_argument("--input-jsonl", default=str(INPUT_JSONL))
    parser.add_argument("--output-jsonl", default=str(OUTPUT_JSONL))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    parser.add_argument("--planner-notes-csv")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retry-from-reviewed-csv")
    parser.add_argument("--n-runs", type=int, default=DEFAULT_REVIEW_N_RUNS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_REVIEW_MAX_WORKERS)
    args = parser.parse_args()

    api_key, bearer = validate_credentials()

    if args.retry_from_reviewed_csv:
        reviewed_rows = _rows_from_reviewed_csv(Path(args.retry_from_reviewed_csv))
        retry_items = {row["item_key"] for row in reviewed_rows if row.get("status") != "ok"}
        base_rows = _load_jsonl(Path(args.input_jsonl))
        retry_rows = [row for row in base_rows if row.get("item_key") in retry_items]
        retry_input = Path(args.output_jsonl).with_suffix(".retry-input.jsonl")
        retry_input.parent.mkdir(parents=True, exist_ok=True)
        with retry_input.open("w", encoding="utf-8") as fh:
            for row in retry_rows:
                fh.write(json.dumps(row) + "\n")
        input_path = retry_input
    else:
        input_path = Path(args.input_jsonl)

    summary = export_reviews(
        input_path,
        Path(args.output_jsonl),
        Path(args.output_csv),
        api_key,
        bearer,
        args.limit,
        Path(args.planner_notes_csv) if args.planner_notes_csv else None,
        args.n_runs,
        args.max_workers,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
