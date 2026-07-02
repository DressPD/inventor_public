"""
Ensemble aggregation layer. Aggregates N parallel LLM runs per material using
majority vote (categorical) and mean±CI (numerical). Confidence tiers:
HIGH (≥4/5), MEDIUM (3/5), UNCERTAIN (≤2/5).
Ref: Dietterich (2000) Ensemble Methods in Machine Learning.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter

from inventor_tests.orchestration.ensemble_runner import canonicalize_selected_model

FIELD_REGISTRY: dict[str, tuple[str, list | None]] = {
    "selected_model":    ("categorical", ["EOQ", "(r,Q)", "(s,S)", "NB branch", "Base-stock"]),
    "boundary_risk":     ("categorical", ["LOW", "MEDIUM", "HIGH"]),
    "escalation_flag":   ("categorical", ["YES", "NO"]),
    "safety_stock":      ("numerical",   None),
    "reorder_point":     ("numerical",   None),
    "order_quantity":    ("policy_int",  None),
    "warnings":          ("list_union",  None),
}

POLICY_FALLBACK: str = "(r,Q)"


def _majority_vote(
    values: list[str],
    valid_set: list[str] | None,
) -> tuple[str, float]:
    filtered = [v for v in values if v is not None and v != ""]
    if not filtered:
        fallback = valid_set[0] if valid_set else ""
        return (fallback, 0.0)

    counts: Counter[str] = Counter(filtered)

    if valid_set:
        valid_counts = {v: counts.get(v, 0) for v in valid_set}
        if not any(valid_counts.values()):
            return (valid_set[0], 0.0)
        max_count = max(valid_counts.values())
        winner = next(v for v in valid_set if valid_counts[v] == max_count)  # Preserves valid_set order for deterministic tie-breaking
    else:
        max_count = max(counts.values())
        candidates = sorted(v for v, c in counts.items() if c == max_count)
        winner = candidates[0]

    return (winner, max_count / len(filtered))


def _aggregate_float(values: list[float | None]) -> tuple[float, float]:
    """Returns (mean, ci_halfwidth). CI = 1.96 × std / √n. Skips None. ci=0.0 when n<2."""
    valid = [v for v in values if v is not None]
    if not valid:
        return (0.0, 0.0)
    mean = statistics.mean(valid)
    if len(valid) < 2:
        return (mean, 0.0)
    ci = 1.96 * statistics.stdev(valid) / math.sqrt(len(valid))
    return (mean, ci)


def _aggregate_policy_int(values: list[float | None]) -> int:
    """Returns median rounded to nearest int; math.ceil applied on exact .5 remainder."""
    valid = [v for v in values if v is not None]
    if not valid:
        return 0
    sorted_vals = sorted(valid)
    n = len(sorted_vals)
    median = float(sorted_vals[n // 2]) if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
    if abs(median - math.floor(median) - 0.5) < 1e-10:
        return math.ceil(median)
    return round(median)


def confidence_tier(agree_frac: float, n_valid: int) -> str:
    if n_valid < 3:
        return "UNCERTAIN"
    if n_valid >= 5 and agree_frac >= 4 / 5:
        return "HIGH"
    if agree_frac >= 3 / 5:
        return "MEDIUM"
    return "UNCERTAIN"


def aggregate_runs(runs: list[dict]) -> dict:
    """
    Aggregate N parallel LLM run outputs into a single consensus result.

    Parameters
    ----------
    runs : list[dict]
        Each dict is one run result from ensemble_runner.run_ensemble().
        Expected keys: all FIELD_REGISTRY keys plus run_id, material_id, timestamp.

    Returns
    -------
    dict
        Keys: selected_model, model_confidence, boundary_risk, risk_confidence,
        escalation_flag, safety_stock_mean, safety_stock_ci, reorder_point_mean,
        reorder_point_ci, order_quantity_median, warnings_all, n_runs, n_valid,
        agreement_rate. UNCERTAIN model_confidence → caller should use POLICY_FALLBACK.
    """
    n_runs = len(runs)
    valid_runs = [r for r in runs if r.get("selected_model") not in (None, "")]
    n_valid = len(valid_runs)

    _, model_valid_set = FIELD_REGISTRY["selected_model"]
    selected_model, model_frac = _majority_vote(
        [canonicalize_selected_model(r.get("selected_model", "")) for r in valid_runs],
        model_valid_set,
    )
    model_confidence = confidence_tier(model_frac, n_valid)

    _, risk_valid_set = FIELD_REGISTRY["boundary_risk"]
    boundary_risk, risk_frac = _majority_vote(
        [r.get("boundary_risk", "") for r in valid_runs], risk_valid_set
    )
    risk_confidence = confidence_tier(risk_frac, n_valid)

    _, esc_valid_set = FIELD_REGISTRY["escalation_flag"]
    escalation_flag, _ = _majority_vote(
        [r.get("escalation_flag", "") for r in valid_runs], esc_valid_set
    )

    safety_stock_mean, safety_stock_ci = _aggregate_float(
        [r.get("safety_stock") for r in valid_runs]
    )
    reorder_point_mean, reorder_point_ci = _aggregate_float(
        [r.get("reorder_point") for r in valid_runs]
    )
    order_quantity_median = _aggregate_policy_int(
        [r.get("order_quantity") for r in valid_runs]
    )

    warnings_all: list[str] = []
    seen: set[str] = set()
    for r in valid_runs:
        for w in r.get("warnings") or []:
            if w and w not in seen:
                warnings_all.append(w)
                seen.add(w)

    return {
        "selected_model":        selected_model,
        "model_confidence":      model_confidence,
        "boundary_risk":         boundary_risk,
        "risk_confidence":       risk_confidence,
        "escalation_flag":       escalation_flag,
        "safety_stock_mean":     round(safety_stock_mean, 4),
        "safety_stock_ci":       round(safety_stock_ci, 4),
        "reorder_point_mean":    round(reorder_point_mean, 4),
        "reorder_point_ci":      round(reorder_point_ci, 4),
        "order_quantity_median": order_quantity_median,
        "warnings_all":          warnings_all,
        "n_runs":                n_runs,
        "n_valid":               n_valid,
        "agreement_rate":        round(model_frac, 4) if n_valid > 0 else 0.0,
    }


if __name__ == "__main__":
    mock_runs = [
        {
            "run_id": 1, "material_id": "MAT-001", "timestamp": "2024-01-01",
            "selected_model": "(r,Q)", "boundary_risk": "MEDIUM",
            "escalation_flag": "NO", "safety_stock": 120.0,
            "reorder_point": 350.0, "order_quantity": 500,
            "warnings": ["Low demand data", "High lead time variance"],
        },
        {
            "run_id": 2, "material_id": "MAT-001", "timestamp": "2024-01-01",
            "selected_model": "(r,Q)", "boundary_risk": "HIGH",
            "escalation_flag": "NO", "safety_stock": 115.0,
            "reorder_point": 340.0, "order_quantity": 490,
            "warnings": ["Low demand data"],
        },
        {
            "run_id": 3, "material_id": "MAT-001", "timestamp": "2024-01-01",
            "selected_model": "(r,Q)", "boundary_risk": "MEDIUM",
            "escalation_flag": "YES", "safety_stock": 125.0,
            "reorder_point": 360.0, "order_quantity": 510,
            "warnings": ["Sparse SKU history"],
        },
        {
            "run_id": 4, "material_id": "MAT-001", "timestamp": "2024-01-01",
            "selected_model": "(r,Q)", "boundary_risk": "MEDIUM",
            "escalation_flag": "NO", "safety_stock": 118.0,
            "reorder_point": 345.0, "order_quantity": 505,
            "warnings": [],
        },
        {
            "run_id": 5, "material_id": "MAT-001", "timestamp": "2024-01-01",
            "selected_model": "EOQ", "boundary_risk": "LOW",
            "escalation_flag": "NO", "safety_stock": 110.0,
            "reorder_point": 330.0, "order_quantity": 480,
            "warnings": ["Low demand data"],
        },
    ]

    result = aggregate_runs(mock_runs)

    print("=== Ensemble Aggregation Result ===")
    for k, v in result.items():
        print(f"  {k}: {v}")

    assert result["selected_model"] == "(r,Q)"
    assert result["model_confidence"] == "HIGH"
    assert result["n_runs"] == 5
    assert result["n_valid"] == 5
    assert result["agreement_rate"] == 0.8
    assert result["escalation_flag"] == "NO"
    assert "Low demand data" in result["warnings_all"]
    assert result["order_quantity_median"] == 500

    assert confidence_tier(1.0, 2) == "UNCERTAIN"
    assert confidence_tier(0.8, 5) == "HIGH"
    assert confidence_tier(0.6, 5) == "MEDIUM"
    assert confidence_tier(0.4, 5) == "UNCERTAIN"
    # Incomplete sets (<5 runs) capped at MEDIUM
    assert confidence_tier(1.0, 3) == "MEDIUM"
    assert confidence_tier(0.8, 4) == "MEDIUM"
    assert confidence_tier(1.0, 4) == "MEDIUM"
    assert confidence_tier(0.4, 3) == "UNCERTAIN"

    print("\nAll assertions passed ✓")
