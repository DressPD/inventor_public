from __future__ import annotations

import concurrent.futures
import json
import re
import sys
import time

from inventor_tests.orchestration.llm_api_client import (
    llm_chat,
    validate_credentials,
)

DEFAULT_N_RUNS = 5
DEFAULT_MAX_WORKERS = 5
DEFAULT_RETRIES = 2

MODEL_LABEL_MAP = {
    "NegBin": "NB branch",
    "negative binomial": "NB branch",
    "NB": "NB branch",
    "nb": "NB branch",
}

VALID_MODELS = frozenset({"EOQ", "(r,Q)", "(s,S)", "NB branch", "Base-stock"})
VALID_BOUNDARY_RISK = frozenset({"LOW", "MEDIUM", "HIGH"})

_OUTPUT_TEMPLATE = (
    "{\n"
    '  "selected_model": "<one of: EOQ, (r,Q), (s,S), NB branch, Base-stock>",\n'
    '  "selection_rationale": "<exactly 2 sentences, must cite specific numeric stat values>",\n'
    '  "boundary_risk": "<one of: LOW, MEDIUM, HIGH>",\n'
    '  "escalation_flag": "<YES or NO>",\n'
    '  "narrative": "<3 to 5 sentences explaining the recommendation>",\n'
    '  "warnings": ["<list of strings, can be empty>"]\n'
    "}"
)


def canonicalize_selected_model(model: str | None) -> str | None:
    if not isinstance(model, str):
        return model
    cleaned = model.strip()
    return MODEL_LABEL_MAP.get(cleaned, cleaned)


def build_ensemble_prompt(
    material_id: str,
    stats: dict,
    policy_values: dict,
    slt: dict,
) -> str:
    stats_block = json.dumps(stats, indent=2, ensure_ascii=False)
    policy_block = json.dumps(
        {
            "safety_stock": policy_values.get("safety_stock"),
            "reorder_point": policy_values.get("reorder_point"),
            "order_quantity": policy_values.get("order_quantity"),
            "sigma_ltd": policy_values.get("sigma_ltd"),
        },
        indent=2,
        ensure_ascii=False,
    )
    slt_block = json.dumps(
        {
            "recommended_days": slt.get("recommended_days"),
            "sigma_eff_days": slt.get("sigma_eff_days"),
            "dominant_factor": slt.get("dominant_factor"),
        },
        indent=2,
        ensure_ascii=False,
    )
    lines = [
        "You are an inventory optimization assistant.",
        "All statistics are pre-computed. DO NOT recompute any values.",
        "",
        f"MATERIAL ID: {material_id}",
        "",
        "--- PRE-COMPUTED STATISTICS (copy verbatim, do not modify) ---",
        stats_block,
        "",
        "--- PRE-COMPUTED POLICY VALUES ---",
        policy_block,
        "",
        "--- SERVICE LEVEL TARGET (SLT) ---",
        slt_block,
        "",
        "EXCLUDED from routing: Wagner-Whitin, Croston, Syntetos-Boylan methods.",
        "",
        "Your task: fill ONLY the following 6 fields. No calculations permitted.",
        "",
        "Output format (return ONLY valid JSON, no prose outside JSON):",
        _OUTPUT_TEMPLATE,
        "",
        "Rules:",
        "- selected_model must be exactly one of: EOQ, (r,Q), (s,S), NB branch, Base-stock",
        "- selection_rationale must be exactly 2 sentences and must reference"
        " specific numeric values from the stats above",
        "- boundary_risk must be exactly one of: LOW, MEDIUM, HIGH",
        "- escalation_flag must be exactly YES or NO",
        "- narrative must be 3 to 5 sentences",
        "- warnings is a list of strings (use empty list [] if none)",
        "- Return ONLY valid JSON. No prose outside JSON.",
        "- Save output as inventory_optimization_output.json",
    ]
    return "\n".join(lines)


def _has_valid_policy(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    return canonicalize_selected_model(result.get("selected_model")) in VALID_MODELS


def _extract_json_from_messages(messages) -> dict | None:
    text: str | None = None

    if isinstance(messages, str):
        text = messages
    elif isinstance(messages, list):
        parts: list[str] = []
        for item in messages:
            if isinstance(item, dict):
                content = item.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for chunk in content:
                        if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                            parts.append(chunk["text"])
        text = "\n".join(parts)
    elif isinstance(messages, dict):
        ai_msgs = messages.get("newAiMessages")
        if isinstance(ai_msgs, list) and ai_msgs:
            parts: list[str] = []
            for msg in ai_msgs:
                body = msg.get("body", {}) if isinstance(msg, dict) else {}
                t = body.get("text", "") if isinstance(body, dict) else ""
                if t:
                    parts.append(t)
            for candidate in parts:
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    m = re.search(r"\{.*\}", candidate, re.DOTALL)
                    if m:
                        try:
                            return json.loads(m.group())
                        except json.JSONDecodeError:
                            pass
            text = "\n".join(parts) if parts else None
        if text is None:
            content = messages.get("content", "")
            if isinstance(content, str):
                text = content
            else:
                text = json.dumps(content)

    if not text:
        return None

    # Try direct JSON parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Search for JSON object pattern {...} — handles prose-wrapped responses
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _run_single(
    material_id: str,
    stats: dict,
    policy_values: dict,
    slt: dict,
    run_idx: int,
    api_key: str,
    bearer: str,
    retries: int,
) -> dict | None:
    prompt = build_ensemble_prompt(material_id, stats, policy_values, slt)
    remaining = retries

    while True:
        try:
            validate_credentials()
            response_text = llm_chat(prompt, api_key=api_key)
            parsed = _extract_json_from_messages(response_text)
            if parsed is not None:
                parsed["selected_model"] = canonicalize_selected_model(
                    parsed.get("selected_model")
                )
                parsed["_run_idx"] = run_idx
            return parsed
        except Exception:
            if remaining > 0:
                remaining -= 1
                time.sleep(2)
            else:
                return None


def run_ensemble(
    material_id: str,
    stats: dict,
    policy_values: dict,
    slt: dict,
    api_key: str,
    bearer: str,
    n_runs: int = DEFAULT_N_RUNS,
    max_workers: int = DEFAULT_MAX_WORKERS,
    retries: int = DEFAULT_RETRIES,
) -> list[dict]:
    raw_results: list[dict | None] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _run_single,
                material_id,
                stats,
                policy_values,
                slt,
                run_idx,
                api_key,
                bearer,
                retries,
            ): run_idx
            for run_idx in range(n_runs)
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                raw_results.append(future.result())
            except Exception:
                raw_results.append(None)

    valid_results = [r for r in raw_results if r is not None]
    n_valid = len(valid_results)
    sys.stderr.write(f"[ensemble] {material_id}: {n_valid}/{n_runs} runs succeeded\n")
    return valid_results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Run ensemble LLM calls for a single material."
    )
    parser.add_argument("material_id", help="Material identifier")
    parser.add_argument("--api-key", required=True, help="LLM API key (or set LLM_API_KEY env var)")
    parser.add_argument("--n-runs", type=int, default=DEFAULT_N_RUNS)
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    args = parser.parse_args()

    sample_stats: dict = {}
    sample_policy_values: dict = {
        "safety_stock": 0,
        "reorder_point": 0,
        "order_quantity": 0,
        "sigma_ltd": 0.0,
    }
    sample_slt: dict = {
        "recommended_days": 0,
        "sigma_eff_days": 0.0,
        "dominant_factor": "unknown",
    }

    results = run_ensemble(
        material_id=args.material_id,
        stats=sample_stats,
        policy_values=sample_policy_values,
        slt=sample_slt,
        api_key=args.api_key,
        bearer=args.bearer,
        n_runs=args.n_runs,
        max_workers=args.max_workers,
        retries=args.retries,
    )
    print(json.dumps(results, indent=2, ensure_ascii=False))
