"""
stats_calculator.py
-------------------
Deterministic pre-computation of inventory statistics for one material.
Implements exactly the D1-D12 rules and Steps 1-3 from the inventOR SYSTEM_PROMPT.
Output is a clean dict ready to be injected into the ensemble prompt.

Usage:
    from stats_calculator import compute_stats
    stats = compute_stats("MATERIAL_0001", rows)   # rows = list[dict] from CSV

Or standalone:
    python3 stats_calculator.py MATERIAL_0001
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm

from inventor_tests._utils import safe_float as _to_float, safe_int as _to_int

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "20260619_400_Mat_2_plants.csv"


def build_item_key(material_id: str, plant_code: str | None) -> str:
    plant = (plant_code or "").strip()
    material = (material_id or "").strip()
    if plant:
        return f"{plant}__{material}"
    return material


def split_item_key(item_key: str) -> tuple[str | None, str]:
    if "__" in item_key:
        plant_code, material_id = item_key.split("__", 1)
        return plant_code, material_id
    return None, item_key


def infer_demand_sign_inversion(rows: list[dict]) -> bool:
    raw_demand_values = np.array([_to_float(r.get("actual_demand"), 0.0) for r in rows], dtype=float)
    raw_positive = int(np.sum(raw_demand_values > 0))
    raw_negative = int(np.sum(raw_demand_values < 0))
    return raw_positive == 0 and raw_negative > 0


def normalized_row_demand(row: dict, sign_inverted: bool | None = None) -> float:
    demand = _to_float(row.get("actual_demand"), 0.0)
    if sign_inverted is None:
        sign_inverted = demand < 0
    return -demand if sign_inverted else demand


def normalized_demand_values(rows: list[dict], sign_inverted: bool | None = None) -> np.ndarray:
    if sign_inverted is None:
        sign_inverted = infer_demand_sign_inversion(rows)
    return np.array([normalized_row_demand(r, sign_inverted) for r in rows], dtype=float)


def load_material_rows(material_id: str, csv_path=CSV_PATH) -> list[dict]:
    csv_path = Path(csv_path)
    plant_filter, material_filter = split_item_key(material_id)
    rows = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            if row.get("material", "").strip() != material_filter:
                continue
            if plant_filter and row.get("plant_code", "").strip() != plant_filter:
                continue
            rows.append(row)
    return rows


def compute_stats(material_id: str, rows: list[dict]) -> dict:
    if not rows:
        raise ValueError(f"No rows found for material {material_id}")

    plant_code, source_material_id = split_item_key(material_id)
    sign_inverted = infer_demand_sign_inversion(rows)
    demand_raw = normalized_demand_values(rows, sign_inverted)

    is_working = np.array([_to_int(r.get("is_working_day"), 0) == 1 for r in rows], dtype=bool)
    demand_wd = demand_raw[is_working]
    wd_nonzero = demand_wd[demand_wd > 0]

    delivery_vals = np.array([_to_float(r.get("delivery_time"), np.nan) for r in rows], dtype=float)
    delivery_vals = delivery_vals[np.isfinite(delivery_vals) & (delivery_vals > 0)]

    current_ss = _to_float(rows[-1].get("safety_stock_units"), 0.0)
    current_slt = _to_float(rows[-1].get("safety_time_workdays_actual"), 0.0)

    unit_cost = _to_float(rows[-1].get("unit_cost"), 0.0)
    hcr = _to_float(rows[-1].get("holding_cost_rate"), 0.0)
    ordering_cost = _to_float(rows[-1].get("ordering_cost"), 0.0)
    moq = _to_int(rows[-1].get("minimum_order_quantity"), 1)
    review_period_days = _to_float(rows[-1].get("review_period_days"), 1.0)
    service_level = _to_float(rows[-1].get("service_level_target") or rows[-1].get("service_level"), 0.95)
    supplier_reliability = _to_float(rows[-1].get("reliability_calc") or rows[-1].get("reliability") or rows[-1].get("reliability_random"), 0.0)
    distance_km = _to_float(rows[-1].get("supplier_plant_distance"), 0.0)

    mean_daily = float(np.mean(demand_raw)) if len(demand_raw) else 0.0
    std_daily = float(np.std(demand_raw, ddof=1)) if len(demand_raw) > 1 else 0.0
    mean_wd = float(np.mean(demand_wd)) if len(demand_wd) else 0.0
    std_wd = float(np.std(demand_wd, ddof=1)) if len(demand_wd) > 1 else 0.0
    robust_std_daily = float((np.percentile(demand_wd, 75) - np.percentile(demand_wd, 25)) / 1.35) if len(demand_wd) >= 4 else std_wd
    d_max_calendar = float(np.max(demand_raw)) if len(demand_raw) else 0.0
    d_max_wd = float(np.max(demand_wd)) if len(demand_wd) else 0.0

    mean_lt = float(np.mean(delivery_vals)) if len(delivery_vals) else 0.0
    std_lt = float(np.std(delivery_vals, ddof=1)) if len(delivery_vals) > 1 else 0.0
    cv_lt = (std_lt / mean_lt) if mean_lt > 0 else 0.0
    cv_wd = (std_wd / mean_wd) if mean_wd > 0 else 0.0

    if cv_lt >= 0.50:
        lt_stability = "Unstable"
    elif cv_lt >= 0.25:
        lt_stability = "Moderate"
    else:
        lt_stability = "Stable"

    non_zero_fraction_wd = float(len(wd_nonzero) / len(demand_wd)) if len(demand_wd) else 0.0
    if non_zero_fraction_wd < 0.35:
        regime = "Intermittent"
    elif cv_wd > 1.0:
        regime = "Lumpy"
    elif cv_wd > 0.5:
        regime = "Erratic"
    elif mean_wd <= 0:
        regime = "Dead stock"
    else:
        regime = "Smooth"

    distribution_type = "Negative Binomial" if regime in {"Intermittent", "Lumpy"} else "Normal"
    overdispersion_index = float((std_wd ** 2) / mean_wd) if mean_wd > 0 else 0.0
    trend_flag = bool(len(demand_wd) >= 8 and abs(np.polyfit(np.arange(len(demand_wd)), demand_wd, 1)[0]) > 0.01 * max(mean_wd, 1.0))
    effective_lead_time = mean_lt + max(current_slt, review_period_days)

    positive_raw = int(np.sum(demand_raw > 0))
    negative_raw = int(np.sum(np.array([_to_float(r.get("actual_demand"), 0.0) for r in rows], dtype=float) < 0))
    zero_raw = int(np.sum(np.array([_to_float(r.get("actual_demand"), 0.0) for r in rows], dtype=float) == 0))

    unique_dates = {r.get("date") for r in rows if r.get("date")}
    span_days = max(len(unique_dates), 1)
    working_days = int(np.sum(is_working))
    annual_demand_days = 365.0 * working_days / span_days if span_days > 0 else 365.0

    z_score = float(norm.ppf(service_level)) if 0 < service_level < 1 else float(norm.ppf(0.95))

    return {
        "material_id": material_id,
        "source_material_id": source_material_id,
        "plant_code": plant_code or rows[-1].get("plant_code", "").strip() or None,
        "working_days": working_days,
        "delivery_observations": int(len(delivery_vals)),
        "mean_daily_demand": mean_daily,
        "std_daily_demand": std_daily,
        "robust_std_daily": robust_std_daily,
        "mean_wd_demand": mean_wd,
        "std_wd_demand": std_wd,
        "cv_wd": cv_wd,
        "non_zero_fraction_wd": non_zero_fraction_wd,
        "d_max_calendar": d_max_calendar,
        "d_max_wd": d_max_wd,
        "mean_lead_time": mean_lt,
        "std_lead_time": std_lt,
        "cv_lead_time": cv_lt,
        "lead_time_stability": lt_stability,
        "effective_lead_time": effective_lead_time,
        "supplier_reliability": supplier_reliability,
        "distance_km": distance_km,
        "current_safety_stock_units": current_ss,
        "current_sap_slt_days": current_slt,
        "unit_cost": unit_cost,
        "holding_cost_rate": hcr,
        "ordering_cost": ordering_cost,
        "annual_holding_cost_per_unit": unit_cost * hcr,
        "moq": max(moq, 1),
        "lot_size": max(moq, 1),
        "review_period_days": review_period_days,
        "service_level": service_level,
        "z_score": z_score,
        "regime": regime,
        "distribution_type": distribution_type,
        "overdispersion_index": overdispersion_index,
        "trend_flag": trend_flag,
        "milp_pretrigger": None,
        "scrap_rate": 0.0,
        "stock_correction_count": 0,
        "replenishment_cycles": 0,
        "demand_sign_inverted": sign_inverted,
        "positive_demand_rows_raw": positive_raw,
        "negative_demand_rows_raw": negative_raw,
        "zero_demand_rows_raw": zero_raw,
        "positive_demand_rows": int(np.sum(demand_raw > 0)),
        "annual_demand_days": annual_demand_days,
    }


def compute_policy_values(stats: dict) -> dict:
    mean_lt = max(float(stats.get("mean_lead_time", 0.0)), 0.0)
    std_d = max(float(stats.get("std_daily_demand", 0.0)), 0.0)
    mean_d = max(float(stats.get("mean_daily_demand", 0.0)), 0.0)
    std_lt = max(float(stats.get("std_lead_time", 0.0)), 0.0)
    z = float(stats.get("z_score", norm.ppf(0.95)))
    gamma = 0.5
    d_max = max(float(stats.get("d_max_calendar", 0.0)), 0.0)
    effective_lt = max(float(stats.get("effective_lead_time", mean_lt)), 0.0)
    annual_holding = max(float(stats.get("annual_holding_cost_per_unit", 0.0)), 0.0)
    ordering_cost = max(float(stats.get("ordering_cost", 0.0)), 0.0)
    moq = max(int(stats.get("moq", 1) or 1), 1)
    annual_demand_days = float(stats.get("annual_demand_days", 365.0) or 365.0)

    sigma_ltd = math.sqrt(max(mean_lt * (std_d ** 2) + (mean_d ** 2) * (std_lt ** 2), 0.0)) if mean_lt > 0 else 0.0
    safety_stock = z * sigma_ltd
    safety_stock_robust = safety_stock + gamma * max(0.0, d_max - mean_d) * math.sqrt(mean_lt) if mean_lt > 0 else safety_stock
    reorder_point = mean_d * effective_lt + safety_stock_robust
    annual_demand = mean_d * annual_demand_days

    if annual_holding > 0 and ordering_cost > 0 and annual_demand > 0:
        eoq_raw = math.sqrt(2.0 * annual_demand * ordering_cost / annual_holding)
    else:
        eoq_raw = float(moq)
    order_quantity = max(int(math.ceil(max(eoq_raw, moq))), moq)

    return {
        "sigma_ltd": sigma_ltd,
        "safety_stock": safety_stock,
        "safety_stock_robust": safety_stock_robust,
        "reorder_point": reorder_point,
        "annual_demand": annual_demand,
        "annual_demand_days": annual_demand_days,
        "eoq_raw": eoq_raw,
        "order_quantity": order_quantity,
        "review_period_days": stats.get("review_period_days", 1.0),
        "milp_trigger": stats.get("milp_pretrigger"),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 stats_calculator.py <material_or_item_key>")
        raise SystemExit(1)
    key = sys.argv[1]
    rows = load_material_rows(key)
    stats = compute_stats(key, rows)
    print(stats)
