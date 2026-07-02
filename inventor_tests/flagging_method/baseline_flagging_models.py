from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from inventor_tests._utils import safe_float as _safe_float

_ROOT = Path(__file__).resolve().parents[1]
_RESULTS_DIR = _ROOT.parent / "results"
_INTERNAL_DIR = _ROOT.parent / "sample_artifacts"
TARGETS_CSV = _INTERNAL_DIR / "target_ranking.csv"
FLAGS_CSV = _INTERNAL_DIR / "material_flags.csv"
OUTPUT_JSON = _INTERNAL_DIR / "baseline_metrics.json"
OUTPUT_CSV = _RESULTS_DIR / "baseline_metrics.csv"


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _as_binary(value: bool) -> str:
    return "YES" if value else "NO"


def _target_label(row: dict[str, str]) -> str:
    return "YES" if row.get("isolate_for_optimization") == "YES" else "NO"


def _rule_sap_gain(row: dict[str, str]) -> str:
    return _as_binary(_safe_float(row.get("fill_gain_vs_sap_pct_pts")) > 1.0)


def _rule_stockout_gain(row: dict[str, str]) -> str:
    return _as_binary(_safe_float(row.get("stockout_days_reduction_vs_sap")) >= 2.0)


def _rule_hard_flag(row: dict[str, str]) -> str:
    return _as_binary(row.get("hard_escalation_flag") == "YES")


def _rule_special_route(row: dict[str, str]) -> str:
    route = row.get("route_used") or row.get("selected_model") or ""
    return _as_binary(route in {"(s,S)", "NB branch", "negbin"})


def _rule_current_bucket(row: dict[str, str]) -> str:
    return _as_binary((row.get("flag_bucket") or "") in {"OPTIMIZE_NOW", "LLM_REVIEW"})


def _metrics(y_true: list[str], y_pred: list[str]) -> dict[str, float | int]:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == "YES" and p == "YES")
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == "NO" and p == "NO")
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == "NO" and p == "YES")
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == "YES" and p == "NO")
    total = len(y_true)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": total,
        "accuracy": round((tp + tn) / total, 4) if total else 0.0,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "predicted_yes": sum(1 for p in y_pred if p == "YES"),
    }


FEATURES = [
    "fill_gain_vs_sap_pct_pts",
    "fill_gain_vs_universal_rq_pct_pts",
    "stockout_days_reduction_vs_sap",
    "cost_delta_vs_universal_rq",
    "opportunity_score",
    "cv_wd",
    "cv_lead_time",
    "delivery_observations",
    "supplier_reliability",
]


def _candidate_thresholds(values: list[float]) -> list[float]:
    unique = sorted(set(values))
    if len(unique) <= 1:
        return unique
    mids = [(a + b) / 2.0 for a, b in zip(unique, unique[1:])]
    if len(mids) > 25:
        step = max(1, len(mids) // 25)
        mids = mids[::step]
    return mids


def _train_stump(rows: list[dict[str, str]], y_true: list[str]) -> dict[str, Any]:
    best: dict[str, Any] | None = None
    for feature in FEATURES:
        values = [_safe_float(row.get(feature), math.nan) for row in rows]
        values = [v for v in values if not math.isnan(v)]
        for threshold in _candidate_thresholds(values):
            for direction in (">=", "<"):
                preds = []
                for row in rows:
                    value = _safe_float(row.get(feature), math.nan)
                    preds.append(_as_binary(value >= threshold if direction == ">=" else value < threshold))
                score = _metrics(y_true, preds)
                if best is None or (score["f1"], score["recall"], score["precision"]) > (
                    best["metrics"]["f1"],
                    best["metrics"]["recall"],
                    best["metrics"]["precision"],
                ):
                    best = {"feature": feature, "threshold": threshold, "direction": direction, "metrics": score}
    return best or {"feature": None, "threshold": None, "direction": None, "metrics": _metrics(y_true, ["NO"] * len(y_true))}


def _apply_stump(row: dict[str, str], stump: dict[str, Any]) -> str:
    feature = stump.get("feature")
    if not feature:
        return "NO"
    value = _safe_float(row.get(feature), math.nan)
    threshold = float(stump["threshold"])
    return _as_binary(value >= threshold if stump.get("direction") == ">=" else value < threshold)


def _folds(rows: list[dict[str, str]], k: int = 5) -> list[list[int]]:
    positives = [i for i, row in enumerate(rows) if _target_label(row) == "YES"]
    negatives = [i for i, row in enumerate(rows) if _target_label(row) == "NO"]
    buckets: list[list[int]] = [[] for _ in range(k)]
    for seq in (positives, negatives):
        for pos, idx in enumerate(seq):
            buckets[pos % k].append(idx)
    return [bucket for bucket in buckets if bucket]


def _cross_validated_stump(rows: list[dict[str, str]], k: int = 5) -> dict[str, Any]:
    folds = _folds(rows, k=k)
    all_true: list[str] = []
    all_pred: list[str] = []
    fold_models: list[dict[str, Any]] = []
    for fold in folds:
        fold_set = set(fold)
        train_idx = [i for i in range(len(rows)) if i not in fold_set]
        model = _train_stump([rows[i] for i in train_idx], [_target_label(rows[i]) for i in train_idx])
        fold_models.append({"feature": model["feature"], "threshold": model["threshold"], "direction": model["direction"]})
        for i in fold:
            all_true.append(_target_label(rows[i]))
            all_pred.append(_apply_stump(rows[i], model))
    full_model = _train_stump(rows, [_target_label(row) for row in rows])
    return {
        "name": "decision_stump_cv",
        "type": "traditional_ml",
        "metrics": _metrics(all_true, all_pred),
        "full_fit": {
            "feature": full_model["feature"],
            "threshold": round(float(full_model["threshold"]), 6) if full_model["threshold"] is not None else None,
            "direction": full_model["direction"],
            "metrics_on_full_data": full_model["metrics"],
        },
        "fold_models": fold_models,
    }


def run_baselines(targets_csv: Path, flags_csv: Path, output_json: Path, output_csv: Path) -> dict[str, Any]:
    target_rows = _load_rows(targets_csv)
    flag_rows = {row["item_key"]: row for row in _load_rows(flags_csv)} if flags_csv.exists() else {}
    rows = [{**row, **{k: v for k, v in flag_rows.get(row["item_key"], {}).items() if k not in row}} for row in target_rows]
    y_true = [_target_label(row) for row in rows]
    baselines: list[dict[str, Any]] = []
    rules: list[tuple[str, Callable[[dict[str, str]], str]]] = [
        ("sap_gain_gt_1pp", _rule_sap_gain),
        ("stockout_reduction_ge_2", _rule_stockout_gain),
        ("hard_flag_only", _rule_hard_flag),
        ("special_route_only", _rule_special_route),
        ("current_deterministic_bucket", _rule_current_bucket),
    ]
    for name, func in rules:
        preds = [func(row) for row in rows]
        baselines.append({"name": name, "type": "rule", "metrics": _metrics(y_true, preds)})
    baselines.append(_cross_validated_stump(rows))

    summary = {
        "targets_csv": str(targets_csv),
        "flags_csv": str(flags_csv),
        "rows": len(rows),
        "target_counts": dict(Counter(y_true)),
        "target_definition": "isolate_for_optimization == YES from deterministic OR target export",
        "caveat": "This is agreement with deterministic OR labels, not human ground truth.",
        "baselines": baselines,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    with output_csv.open("w", newline="", encoding="utf-8") as fh:
        fieldnames = ["name", "type", "n", "accuracy", "precision", "recall", "f1", "tp", "tn", "fp", "fn", "predicted_yes", "notes"]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for baseline in baselines:
            metrics = baseline["metrics"]
            notes = ""
            if baseline["name"] == "decision_stump_cv":
                fit = baseline["full_fit"]
                notes = f"full_fit: {fit['feature']} {fit['direction']} {fit['threshold']}"
            writer.writerow({"name": baseline["name"], "type": baseline["type"], **metrics, "notes": notes})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Baseline deterministic and traditional ML material flagging approaches.")
    parser.add_argument("--targets-csv", default=str(TARGETS_CSV))
    parser.add_argument("--flags-csv", default=str(FLAGS_CSV))
    parser.add_argument("--output-json", default=str(OUTPUT_JSON))
    parser.add_argument("--output-csv", default=str(OUTPUT_CSV))
    args = parser.parse_args()
    summary = run_baselines(Path(args.targets_csv), Path(args.flags_csv), Path(args.output_json), Path(args.output_csv))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
