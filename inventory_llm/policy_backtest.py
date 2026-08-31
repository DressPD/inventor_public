"""Simulate LLM-emitted policy outputs from stored enterprise-LLM runs.

Private evidence rerun:
    python3 -m inventory_llm.policy_backtest

Reads outputs/agentic_runs/<item_key>/output.json, converts each valid LLM
policy block into simulator policy parameters, and evaluates it on the same
validation window used by the deterministic backtest. Public users should run
``python3 -m inventory_llm.synthetic_demo`` instead; this command requires the
confidential input and stored material-level artifacts.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from inventory_llm import core


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "outputs"


def _run_root() -> Path:
    """Resolve the output root for the selected generation run.

    Replicate generation runs are stored under ``outputs/runs/<run id>/``; when
    ``INVENTOR_RUN_ID`` is unset the historical unlabelled root layout is used so
    the primary evaluated cohort and its stored artifacts stay in place.
    """
    raw = (os.environ.get("INVENTOR_RUN_ID") or "").strip()
    if not raw:
        return RESULTS_DIR
    safe = "".join(ch if (ch.isalnum() or ch in {"-", "_", "."}) else "_" for ch in raw)
    if safe in {"", ".", ".."}:
        raise SystemExit("INVENTOR_RUN_ID resolves to an unusable directory name")
    return RESULTS_DIR / "runs" / safe


RUN_ROOT = _run_root()
RUNS_DIR = RUN_ROOT / "agentic_runs"
OUT_JSON = RUN_ROOT / "agentic_policy_backtest.json"
OUT_CSV = RUN_ROOT / "agentic_policy_backtest.csv"
SUPPORTED_POLICY_LABELS = {"rq", "ss"}

# The LLM (enterprise LLM platform) has emitted policy data under many different top-level key
# names and field-name spellings across runs (schema drift, not a data
# problem). These lists were derived by enumerating every key actually
# present across all outputs/agentic_runs/*/output.json artifacts on
# 2026-07-14. Keep this list in sync if the runner's system prompt changes.
POLICY_CONTAINERS = [
    # "recommendations" is deliberately FIRST: it sometimes carries narrative
    # strings (e.g. "Order 5192 units per order") under field names that
    # collide with real numeric fields in the more structured containers
    # below (e.g. "order_quantity"). Merging it first lets later, more
    # authoritative structured containers overwrite any narrative-string
    # collision on the same key.
    "recommendations", "policy", "policy_recommendations", "reorder_policy",
    "recommended_policy", "policy_recommendation", "operational_parameters",
    "inventory_policy", "ordering_policy", "policy_selection",
    "replenishment_policy", "order_policy", "policy_rQ", "policy_rq",
    "policy_parameters", "reorder_point_policy", "inventory_policy_rQ",
]
BUFFER_CONTAINERS = [
    "buffer_analysis", "safety_stock", "buffer_safety_stock", "buffer_sizing",
    "safety_stock_calculation", "safety_stock_analysis", "buffer_calculation",
    "buffer_calculations", "buffer_strategy",
]
# Standalone order-quantity containers, kept separate from POLICY_CONTAINERS
# because they sometimes carry an ambiguous "recommended" field that would
# otherwise collide with safety_stock's own "recommended" field once merged.
OQ_CONTAINERS = ["order_quantity", "order_quantity_analysis", "eoq_analysis", "eoq"]
# Standalone reorder-point containers. Some runs emit a bare top-level
# "reorder_point" key whose own nested field is *also* called
# "reorder_point" (self-referential naming) -- kept out of the main merge
# to avoid clobbering safety_stock/order_quantity fields on key collision.
ROP_CONTAINERS = ["reorder_point"]
MODEL_CONTAINERS = ["research_model", "model_recommendation", "model_selection"]
# When a looked-up field's value is itself a nested dict (e.g.
# {"calculated": 7866.8, "calculated_ceil": 7867}) instead of a plain
# scalar, drill into it using these sub-key names, in priority order.
NESTED_SCALAR_KEYS = [
    "calculated_ceil", "calculated", "rounded", "raw", "final", "value",
    "total_units", "calculated_units", "recommended_units", "robust_units",
    "reorder_point_units", "safety_stock_units", "order_quantity",
]
# Some policy containers (e.g. "policy_recommendation") nest the actual
# rop/oq/ss fields one level deeper inside a "policy_parameters" sub-dict
# instead of at the container's own top level. Flatten that one level when
# present.
NESTED_POLICY_KEYS = ["policy_parameters", "parameters"]

ROP_KEYS = [
    "reorder_point", "reorder_point_units", "reorder_point_r",
    "reorder_point_normal", "reorder_point_r_robust", "reorder_point_raw",
    "reorder_point_robust", "primary_reorder_point", "reorder_point_rop",
    "rop_rounded", "rop_raw", "policy_rop", "rop",
    "reorder_point_standard_units", "reorder_point_standard_raw",
    "reorder_point_robust_units", "reorder_point_robust_raw",
    "r_reorder_point",
]
OQ_KEYS = [
    "order_quantity", "order_quantity_units", "order_quantity_Q",
    "order_quantity_final", "order_quantity_q", "policy_oq",
    "order_quantity_policy", "recommended_order_quantity",
    "order_quantity_recommended", "eoq_adjusted", "final_order_quantity",
    "eoq_rounded", "eoq_constrained", "economic_order_quantity",
    "eoq_final", "Q_order_quantity",
]
SS_KEYS = [
    # Final-decision/policy fields first (these are the LLM's actual chosen
    # value, sometimes distinct from a "robust"/"standard" diagnostic
    # computation reported alongside it in the same container). NOTE:
    # "recommendation" is deliberately EXCLUDED here -- some containers use
    # that exact key for a free-text narrative string (e.g. "INCREASE safety
    # stock to improve service level"), not a numeric value. Using
    # _first_numeric (which skips non-numeric matches and keeps looking)
    # makes it safe to keep "recommendation" in the list, but it is placed
    # after all real numeric aliases to avoid ever preferring it.
    "safety_stock_policy", "policy_ss", "safety_stock_s", "recommended",
    "safety_stock", "safety_stock_units", "primary_safety_stock",
    "safety_stock_component", "safety_stock_value_usd", "calculated",
    "calculated_safety_stock", "safety_stock_recommended", "recommended_safety_stock",
    # Fallback diagnostic/robust variants, only used if no final-decision
    # field is present.
    "safety_stock_robust", "safety_stock_standard", "safety_stock_robust_units",
    "recommended_safety_stock_robust", "calculated_normal", "calculated_robust",
    "recommendation",
]
MODEL_FIELD_KEYS = [
    "model", "model_type", "policy_type", "selected_model", "selected_policy",
    "recommended_model", "primary_model",
]


def _load_targets() -> list[str]:
    return core.eligible_item_keys()


def _as_int(value: object) -> int | None:
    if isinstance(value, dict):
        for k in NESTED_SCALAR_KEYS:
            if k in value and value[k] not in (None, ""):
                nested = _as_int(value[k])
                if nested is not None:
                    return nested
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _norm_family(label: str) -> str | None:
    text = (label or "").lower().replace(" ", "").replace("_", "")
    if not text:
        return None
    if "(s,s)" in text or "base-stock" in text or "order-up-to" in text:
        return "ss"
    if "(r,q)" in text or "s,q" in text or "reorder-point" in text or "continuous-review" in text or "rq" in text:
        return "rq"
    return None


def _first_present(d: dict[str, Any], keys: list[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _first_numeric_int(d: dict[str, Any], keys: list[str]) -> int | None:
    """Like _first_present, but skips candidates that don't resolve to a
    usable int (e.g. a free-text narrative string sharing a key name with a
    real numeric field elsewhere), continuing on to later-priority keys
    instead of giving up.
    """
    for k in keys:
        if k in d and d[k] not in (None, ""):
            val = _as_int(d[k])
            if val is not None:
                return val
    return None


def _safe_update(merged: dict[str, Any], v: dict[str, Any]) -> None:
    """Like dict.update(), but never lets a nested-dict value clobber an
    already-resolved scalar for the same key (schema drift means some runs
    nest a field's real value one level deeper under the same key name that
    another container already gave a plain scalar for; a blind update()
    would silently destroy the good scalar). If the existing merged value is
    a dict too, or the key is new, normal overwrite semantics apply.
    """
    for k, val in v.items():
        existing = merged.get(k)
        if isinstance(val, dict) and k in merged and not isinstance(existing, dict):
            continue
        merged[k] = val


def _merged_policy_block(artifact: dict[str, Any]) -> dict[str, Any]:
    """Union-merge every known policy/buffer container into one dict.

    Policy-container fields take precedence over buffer-container fields on
    key collisions, since the policy block is the more authoritative,
    final-decision source. Some policy containers nest their actual fields
    one level deeper under a "policy_parameters" sub-dict; those are
    flattened up so their fields participate in the same precedence order.
    """
    merged: dict[str, Any] = {}
    for k in BUFFER_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            _safe_update(merged, v)
    for k in OQ_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            _safe_update(merged, v)
    for k in ROP_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            _safe_update(merged, v)
    for k in POLICY_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            _safe_update(merged, v)
            for nk in NESTED_POLICY_KEYS:
                nested = v.get(nk)
                if isinstance(nested, dict):
                    _safe_update(merged, nested)
    return merged


def _oq_from_dedicated_containers(artifact: dict[str, Any]) -> int | None:
    """Fallback OQ lookup scoped to standalone order-quantity containers.

    These containers sometimes use a bare "recommended" field with no other
    order_quantity-style key. That field name is too ambiguous to add to the
    global OQ_KEYS list (it could collide with safety_stock fields once
    merged), so it is only checked here, within the OQ container itself.
    """
    for k in OQ_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            val = _first_numeric_int(v, OQ_KEYS + ["recommended"])
            if val is not None:
                return val
    return None


def _ss_from_dedicated_containers(artifact: dict[str, Any]) -> int | None:
    """Fallback safety-stock lookup scoped to buffer/safety-stock containers.

    "recommended_units" and "total_units" are too ambiguous to add to the
    global SS_KEYS list (order_quantity/reorder_point containers can use the
    same field names for their own values), so they are only checked here,
    directly within the buffer-analysis-style containers themselves.
    """
    for k in BUFFER_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            val = _first_numeric_int(v, SS_KEYS + ["recommended_units", "total_units", "standard", "robust"])
            if val is not None:
                return val
    return None


def _policy_only_block(artifact: dict[str, Any]) -> dict[str, Any]:
    """Policy-container fields only (used for model-label lookup)."""
    merged: dict[str, Any] = {}
    for k in POLICY_CONTAINERS:
        v = artifact.get(k)
        if isinstance(v, dict):
            merged.update(v)
    return merged


def _selected_model(artifact: dict[str, Any]) -> str:
    insights = artifact.get("research_insights") or {}
    if not isinstance(insights, dict):
        insights = {}
    label = insights.get("selected_model") or insights.get("model_selected")
    if not label:
        pol = _policy_only_block(artifact)
        label = _first_present(pol, MODEL_FIELD_KEYS)
    if not label:
        for k in MODEL_CONTAINERS:
            v = artifact.get(k)
            if isinstance(v, dict):
                label = v.get("primary_model") or v.get("model") or v.get("selected_model") or v.get("recommended_model")
                if label:
                    break
    return str(label or "")


def _order_up_to_parameters(artifact: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return explicit (s,S) values; never infer them from an r/Q artifact."""
    policy = artifact.get("policy_recommendation")
    params = policy.get("parameters") if isinstance(policy, dict) else None
    if not isinstance(params, dict):
        return None, None
    return _as_int(params.get("s")), _as_int(params.get("S"))


def _policy_triple(artifact: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    merged = _merged_policy_block(artifact)
    rop = _first_numeric_int(merged, ROP_KEYS)
    oq = _first_numeric_int(merged, OQ_KEYS)
    if oq is None:
        oq = _oq_from_dedicated_containers(artifact)
    ss = _first_numeric_int(merged, SS_KEYS)
    if ss is None:
        ss = _ss_from_dedicated_containers(artifact)
    # Use explicit (s,S) fields only for missing generic values. The returned
    # values retain their original policy family and are not routed as r/Q.
    if (rop is None or oq is None) and _norm_family(_selected_model(artifact)) == "ss":
        threshold, out_to = _order_up_to_parameters(artifact)
        if threshold is not None and out_to is not None and out_to > threshold:
            rop = threshold if rop is None else rop
            oq = out_to - threshold if oq is None else oq
    return rop, oq, ss


def _resolved_family(artifact: dict[str, Any]) -> str | None:
    family = _norm_family(_selected_model(artifact))
    if family in SUPPORTED_POLICY_LABELS:
        return family
    # Fallback: every run empirically resolves to an (r,Q)-style policy once
    # a reorder_point-family field is present, regardless of what internal
    # forecasting-model name (EOQ, Croston-TSB, Holt_Linear, etc.) the LLM
    # used to get there. Treat presence of a rop field as "rq".
    merged = _merged_policy_block(artifact)
    if _first_present(merged, ROP_KEYS) is not None:
        return "rq"
    return None


def _llm_policy(artifact: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any] | None:
    insights = artifact.get("research_insights") or {}
    if not isinstance(insights, dict):
        insights = {}
    rop, oq, ss = _policy_triple(artifact)
    if rop is None or oq is None or ss is None:
        return None
    if rop <= 0 or oq <= 0 or ss < 0:
        return None
    if oq < int(stats.get("moq", 1) or 1):
        return None
    max_storage_units = float(stats.get("max_storage_units", 0) or 0)
    if max_storage_units > 0 and ss + oq > max_storage_units:
        return None
    family = _resolved_family(artifact)
    if family not in SUPPORTED_POLICY_LABELS:
        return None
    if family == "ss":
        threshold, out_to = _order_up_to_parameters(artifact)
        if threshold is None or out_to is None or out_to <= threshold:
            return None
        if threshold != rop or out_to - threshold != oq:
            return None
        return {"policy": "llm_ss", "rop": rop, "oq": oq, "ss": ss, "out_to": out_to}
    return {"policy": "llm_rq", "rop": rop, "oq": oq, "ss": ss, "out_to": None}


def parse_policy_artifact(artifact: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a stored policy artifact into scoreable simulator parameters."""
    return _llm_policy(artifact, stats)


def _invalid_reason(artifact: dict[str, Any], stats: dict[str, Any]) -> str:
    insights = artifact.get("research_insights") or {}
    if not isinstance(insights, dict):
        return "research_insights_not_object"
    rop, oq, ss = _policy_triple(artifact)
    missing = [
        name for name, value in {
            "reorder_point": rop,
            "order_quantity": oq,
            "safety_stock": ss,
        }.items()
        if value is None
    ]
    if missing:
        return "missing_or_non_numeric_" + "_".join(missing)
    family = _resolved_family(artifact)
    if family not in SUPPORTED_POLICY_LABELS:
        return "unsupported_or_missing_policy_label"
    if family == "ss":
        threshold, out_to = _order_up_to_parameters(artifact)
        if threshold is None or out_to is None or out_to <= threshold:
            return "missing_or_invalid_order_up_to_parameters"
    if _llm_policy(artifact, stats) is None:
        if oq is not None and oq < int(stats.get("moq", 1) or 1):
            return "minimum_order_quantity_violation"
        max_storage_units = float(stats.get("max_storage_units", 0) or 0)
        if max_storage_units > 0 and ss is not None and oq is not None and ss + oq > max_storage_units:
            return "max_storage_units_violation"
        return "non_positive_policy_value"
    return "unknown_invalid_policy"


def _aggregate(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    return core.aggregate([r[key] for r in rows if key in r])


def build_backtest(
    arrival_mode: str = "working_days",
    shortage_penalty_multiplier: float = 0.0,
    exclude_repaired_calendars: bool = False,
) -> dict[str, Any]:
    grouped = core.load_grouped_rows()
    repaired_plants = set(core.calendar_repair_metadata().get("calendar_repaired_plants", []))
    targets = _load_targets()
    if exclude_repaired_calendars and repaired_plants:
        targets = [key for key in targets if key.split("__", 1)[0] not in repaired_plants]
    valid_end = core.validation_end(grouped)
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    invalid: list[str] = []
    invalid_reasons: dict[str, str] = {}
    infeasible_comparators: list[str] = []
    capacity_projected = {"sap_static": 0, "universal_rq": 0}

    for item_key in targets:
        path = RUNS_DIR / item_key / "output.json"
        if not path.exists():
            missing.append(item_key)
            continue
        try:
            artifact = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            invalid.append(item_key)
            invalid_reasons[item_key] = "unreadable_json"
            continue
        if not isinstance(artifact, dict):
            invalid.append(item_key)
            invalid_reasons[item_key] = "artifact_not_object"
            continue
        all_rows = grouped.get(item_key, [])
        train, test = core.split_rows(all_rows, core.TRAIN_CUTOFF, valid_end)
        stats = core.compute_stats(train)
        llm_policy = _llm_policy(artifact, stats)
        if llm_policy is None:
            invalid.append(item_key)
            invalid_reasons[item_key] = _invalid_reason(artifact, stats)
            continue
        rq_policy = core.project_policy_to_feasibility(core.make_rq_policy(stats), stats)
        sap_policy = core.project_policy_to_feasibility(core.make_sap_policy(stats), stats)
        if rq_policy is None or sap_policy is None:
            infeasible_comparators.append(item_key)
            continue
        capacity_projected["sap_static"] += int(bool(sap_policy["capacity_projected"]))
        capacity_projected["universal_rq"] += int(bool(rq_policy["capacity_projected"]))
        initial_inventory = core.opening_inventory(test, rq_policy["rop"] + rq_policy["oq"])
        shortage_penalty = max(0.0, shortage_penalty_multiplier) * stats["unit_cost"]
        item = {
            "item_key": item_key,
            "llm_pure": core.simulate(test, llm_policy, stats, initial_inventory, arrival_mode, shortage_penalty),
            "sap_static": core.simulate(test, sap_policy, stats, initial_inventory, arrival_mode, shortage_penalty),
            "universal_rq": core.simulate(test, rq_policy, stats, initial_inventory, arrival_mode, shortage_penalty),
            "llm_policy": llm_policy,
        }
        rows.append(item)

    aggregate = {
        "llm_pure": _aggregate(rows, "llm_pure"),
        "sap_static_subset": _aggregate(rows, "sap_static"),
        "universal_rq_subset": _aggregate(rows, "universal_rq"),
    }
    return {
        "train_cutoff": core.TRAIN_CUTOFF,
        "valid_end": valid_end,
        "n_targets": len(targets),
        "n_backtested": len(rows),
        "arrival_mode": arrival_mode,
        "shortage_penalty_multiplier": max(0.0, shortage_penalty_multiplier),
        "shortage_penalty_basis": "multiplier times source unit_cost per lost-sales unit",
        "policy_scoreability_validation": True,
        "calendar_repair_policy": (
            "imputed_working_day_calendars_excluded"
            if exclude_repaired_calendars
            else "imputed_working_day_calendars_included"
        ),
        "n_plants_with_imputed_working_day_calendar": len(repaired_plants),
        "executed_policy_families": dict(
            sorted(Counter(row["llm_policy"]["policy"] for row in rows).items())
        ),
        "feasibility_rule": "MOQ <= Q and, when supplied, SS + Q <= max_storage_units",
        "capacity_projected_comparators": capacity_projected,
        "infeasible_comparators": infeasible_comparators,
        "missing_outputs": missing,
        "invalid_outputs": invalid,
        "invalid_output_reasons": invalid_reasons,
        "aggregate": aggregate,
        "results": rows,
    }


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result = build_backtest()
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    rows = result["results"]
    fields = [
        "item_key", "llm_fill", "llm_cost", "llm_stockout_days",
        "sap_fill", "sap_cost", "rq_fill", "rq_cost", "llm_ss", "llm_rop", "llm_oq",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "item_key": r["item_key"],
                "llm_fill": r["llm_pure"]["fill_rate_pct"],
                "llm_cost": r["llm_pure"]["total_cost"],
                "llm_stockout_days": r["llm_pure"]["stockout_days"],
                "sap_fill": r["sap_static"]["fill_rate_pct"],
                "sap_cost": r["sap_static"]["total_cost"],
                "rq_fill": r["universal_rq"]["fill_rate_pct"],
                "rq_cost": r["universal_rq"]["total_cost"],
                "llm_ss": r["llm_policy"]["ss"],
                "llm_rop": r["llm_policy"]["rop"],
                "llm_oq": r["llm_policy"]["oq"],
            })
    print(json.dumps({"written": [str(OUT_JSON), str(OUT_CSV)], "aggregate": result["aggregate"]}, indent=2))


if __name__ == "__main__":
    main()
