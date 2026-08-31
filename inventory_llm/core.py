"""Shared inventory data loading, baselines, and simulation for prompt-only runs."""

from __future__ import annotations

import csv
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import NormalDist, mean, pstdev
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_CSV = PROJECT_ROOT / "data" / "synthetic_inventory.csv"
TRAIN_CUTOFF = "2026-03-10"
DEFAULT_VALID_END = "2026-08-27"
ANNUAL_WORKING_DAYS = 250
MIN_TRAIN_WORKING_DAYS = 20
MIN_VALID_WORKING_DAYS = 40
WORKING_DAY_DERIVATION_MODE = "majority_tie_working"
_CALENDAR_REPAIR_METADATA: dict[str, Any] = {}
_LOAD_METADATA: dict[str, Any] = {}


def data_csv() -> Path:
    """Return active source-data path. Override with INVENTOR_DATA_CSV."""
    import os

    return Path(os.environ.get("INVENTOR_DATA_CSV", DEFAULT_DATA_CSV)).expanduser()


def parse_date(value: str) -> date:
    text = value.strip()
    try:
        return date.fromisoformat(text)
    except ValueError:
        return datetime.strptime(text, "%d.%m.%Y").date()


def f(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return default


def demand(row: dict[str, str]) -> float:
    return abs(f(row.get("actual_demand")))


def is_working_day(row: dict[str, str]) -> bool:
    return str(row.get("_effective_is_working_day", row.get("is_working_day", "0"))).strip() == "1"


def _derive_working_day_flag(flags: list[bool]) -> bool:
    if not flags:
        return False
    if WORKING_DAY_DERIVATION_MODE == "all":
        return all(flags)
    if WORKING_DAY_DERIVATION_MODE == "any":
        return any(flags)
    return sum(flags) * 2 >= len(flags)


def _repair_working_day_calendar(grouped: dict[str, list[dict[str, str]]]) -> None:
    plant_rows: dict[str, list[dict[str, str]]] = {}
    for rows in grouped.values():
        for row in rows:
            plant_rows.setdefault(row["plant_code"], []).append(row)

    broken_plants = sorted(
        plant for plant, rows in plant_rows.items()
        if rows and not any(str(row.get("is_working_day", "0")).strip() == "1" for row in rows)
    )
    source_flag_votes: dict[str, dict[str, list[bool]]] = {}
    for plant, rows in plant_rows.items():
        if plant in broken_plants:
            continue
        for row in rows:
            source_flag_votes.setdefault(row["date"], {}).setdefault(plant, []).append(
                str(row.get("is_working_day", "0")).strip() == "1"
            )
    source_flags: dict[str, dict[str, bool]] = {
        day: {plant: _derive_working_day_flag(flags) for plant, flags in plants.items()}
        for day, plants in source_flag_votes.items()
    }

    repaired_rows = 0
    derived_dates = 0
    for rows in grouped.values():
        for row in rows:
            if row["plant_code"] in broken_plants:
                flags = list(source_flags.get(row["date"], {}).values())
                repaired = _derive_working_day_flag(flags)
                if flags:
                    derived_dates += 1
                row["_effective_is_working_day"] = "1" if repaired else "0"
                repaired_rows += 1
            else:
                row["_effective_is_working_day"] = "1" if str(row.get("is_working_day", "0")).strip() == "1" else "0"

    _CALENDAR_REPAIR_METADATA.clear()
    _CALENDAR_REPAIR_METADATA.update({
        "working_day_derivation_mode": WORKING_DAY_DERIVATION_MODE,
        "calendar_repaired_plants": broken_plants,
        "calendar_repaired_rows": repaired_rows,
        "calendar_derived_row_dates": derived_dates,
    })


def calendar_repair_metadata() -> dict[str, Any]:
    """Return the last calendar-repair record produced by load_grouped_rows()."""
    return dict(_CALENDAR_REPAIR_METADATA)


def _aggregate_material_dates(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Collapse duplicate material-date rows before policy simulation/statistics."""
    sum_fields = {"actual_demand", "goods_receipt_qty", "stock_correction", "scrap"}
    numeric_average_fields = {"delivery_time"}
    by_date: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_date.setdefault(row["date"], []).append(row)

    merged: list[dict[str, str]] = []
    for day in sorted(by_date):
        day_rows = by_date[day]
        out = dict(day_rows[-1])
        for field in sum_fields:
            if any(str(r.get(field, "")).strip() for r in day_rows):
                out[field] = str(sum(f(r.get(field)) for r in day_rows))
        for field in numeric_average_fields:
            vals = [f(r.get(field)) for r in day_rows if str(r.get(field, "")).strip() and f(r.get(field)) > 0]
            if vals:
                out[field] = str(mean(vals))
        flags = [str(r.get("is_working_day", "0")).strip() == "1" for r in day_rows]
        out["is_working_day"] = "1" if _derive_working_day_flag(flags) else "0"
        eff_flags = [str(r.get("_effective_is_working_day", r.get("is_working_day", "0"))).strip() == "1" for r in day_rows]
        out["_effective_is_working_day"] = "1" if _derive_working_day_flag(eff_flags) else "0"
        merged.append(out)
    return merged


def load_grouped_rows(path: Path | None = None) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    with (path or data_csv()).open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
            # Normalize renamed ERP source fields before downstream processing.
            for source, target in {
                "mat_description": "material_note",
                "sap_safety_lead_time_days": "safety_time_workdays_actual",
                "sap_minimum_order_quantity": "minimum_order_quantity",
                "sap_safety_stock": "safety_stock_units",
            }.items():
                if target not in row and source in row:
                    row[target] = row[source]
            row["date"] = parse_date(row["date"]).isoformat()
            key = f"{row['plant_code']}__{row['material']}"
            grouped.setdefault(key, []).append(row)
    parsed_records = sum(len(rows) for rows in grouped.values())
    def row_date(row: dict[str, str]) -> str:
        return row["date"]

    for rows in grouped.values():
        rows.sort(key=row_date)
    _repair_working_day_calendar(grouped)
    aggregated = {key: _aggregate_material_dates(rows) for key, rows in grouped.items()}
    _LOAD_METADATA.clear()
    _LOAD_METADATA.update({
        "parsed_records": parsed_records,
        "aggregated_material_date_records": sum(len(rows) for rows in aggregated.values()),
    })
    return aggregated


def validation_end(grouped: dict[str, list[dict[str, str]]] | None = None) -> str:
    if grouped is None:
        grouped = load_grouped_rows()
    dates = [r["date"] for rows in grouped.values() for r in rows]
    return max(dates) if dates else DEFAULT_VALID_END


def split_rows(rows: list[dict[str, str]], cutoff: str = TRAIN_CUTOFF, valid_end: str | None = None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    c = parse_date(cutoff)
    e = parse_date(valid_end or DEFAULT_VALID_END)
    train = [r for r in rows if parse_date(r["date"]) < c]
    test = [r for r in rows if c <= parse_date(r["date"]) <= e]
    return train, test


def eligible_item_keys(grouped: dict[str, list[dict[str, str]]] | None = None, cutoff: str = TRAIN_CUTOFF, valid_end: str | None = None) -> list[str]:
    grouped = grouped or load_grouped_rows()
    valid_end = valid_end or validation_end(grouped)
    keys: list[str] = []
    for key, rows in grouped.items():
        train, test = split_rows(rows, cutoff, valid_end)
        pre = sum(1 for r in train if is_working_day(r))
        post = sum(1 for r in test if is_working_day(r))
        if pre >= MIN_TRAIN_WORKING_DAYS and post >= MIN_VALID_WORKING_DAYS:
            keys.append(key)
    return keys


def compute_stats(train_rows: list[dict[str, str]]) -> dict[str, Any]:
    wd = [demand(r) for r in train_rows if is_working_day(r)]
    if not wd:
        wd = [0.0]
    lead = [f(r.get("delivery_time")) for r in train_rows if str(r.get("delivery_time", "")).strip() and f(r.get("delivery_time")) > 0]
    last = train_rows[-1] if train_rows else {}
    mu = mean(wd)
    sigma = pstdev(wd) if len(wd) > 1 else 0.0
    mean_lt = mean(lead) if lead else 1.0
    std_lt = pstdev(lead) if len(lead) > 1 else 0.0
    sap_slt = f(last.get("safety_time_workdays_actual"))
    eff_lt = max(mean_lt + max(sap_slt, 0.0), 0.1)
    sigma_ltd = math.sqrt(max(eff_lt * sigma**2 + (mu**2) * (std_lt**2), 0.0))
    unit_cost = f(last.get("unit_cost"), 1.0) or 1.0
    holding_rate = f(last.get("holding_cost_rate"), 0.12) or 0.12
    return {
        "mean_daily_demand": mu,
        "std_daily_demand": sigma,
        "cv_wd": sigma / mu if mu else 0.0,
        "mean_lead_time": mean_lt,
        "std_lead_time": std_lt,
        "effective_lead_time": eff_lt,
        "sigma_ltd": sigma_ltd,
        "unit_cost": unit_cost,
        "holding_cost_rate": holding_rate,
        "annual_holding_cost_per_unit": unit_cost * holding_rate,
        "ordering_cost": f(last.get("ordering_cost"), 75.0) or 75.0,
        "moq": max(1, int(round(f(last.get("minimum_order_quantity"), 1.0) or 1.0))),
        "max_storage_units": max(0, int(round(f(last.get("max_storage_units"), 0.0)))),
        "sap_safety_stock": max(0, int(round(f(last.get("safety_stock_units"), 0.0)))),
        "sap_slt": sap_slt,
        "service_level": f(last.get("service_level_target"), 0.95) or 0.95,
    }


def _z(service_level: float) -> float:
    return NormalDist().inv_cdf(min(max(service_level, 0.5), 0.999))


def _order_quantity(stats: dict[str, Any]) -> int:
    annual_demand = stats["mean_daily_demand"] * ANNUAL_WORKING_DAYS
    h = max(stats["annual_holding_cost_per_unit"], 1e-9)
    k = max(stats["ordering_cost"], 0.0)
    eoq = math.sqrt(2 * k * annual_demand / h) if annual_demand > 0 and k > 0 else stats["moq"]
    return max(stats["moq"], int(math.ceil(eoq)))


def make_rq_policy(stats: dict[str, Any]) -> dict[str, Any]:
    ss = int(math.ceil(_z(stats["service_level"]) * stats["sigma_ltd"]))
    rop = int(math.ceil(stats["mean_daily_demand"] * stats["effective_lead_time"] + ss))
    return {"policy": "universal_rq", "rop": max(0, rop), "oq": _order_quantity(stats), "ss": max(0, ss), "out_to": None}


def make_sap_policy(stats: dict[str, Any]) -> dict[str, Any]:
    ss = stats["sap_safety_stock"]
    rop = int(math.ceil(stats["mean_daily_demand"] * stats["effective_lead_time"] + ss))
    return {"policy": "sap_static", "rop": max(0, rop), "oq": _order_quantity(stats), "ss": ss, "out_to": None}


def project_policy_to_feasibility(policy: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any] | None:
    """Apply MOQ and per-material storage rules to deterministic comparators."""
    projected = dict(policy)
    moq = max(1, int(stats.get("moq", 1) or 1))
    ss = max(0, int(projected.get("ss", 0) or 0))
    oq = max(moq, int(projected.get("oq", 0) or 0))
    capacity = max(0, int(stats.get("max_storage_units", 0) or 0))
    capacity_projected = False
    if capacity:
        available = capacity - ss
        if available < moq:
            return None
        if oq > available:
            oq = available
            capacity_projected = True
    projected.update({"ss": ss, "oq": oq, "capacity_projected": capacity_projected})
    return projected


def opening_inventory(test_rows: list[dict[str, str]], fallback: int = 0) -> int:
    for row in test_rows:
        text = str(row.get("inventory_on_hand", "")).strip()
        if text:
            return max(0, int(round(f(text, fallback))))
    return max(0, fallback)


def simulate(
    test_rows: list[dict[str, str]],
    policy: dict[str, Any],
    stats: dict[str, Any],
    initial_inventory: int | None = None,
    arrival_mode: str = "working_days",
    shortage_penalty_per_unit: float = 0.0,
) -> dict[str, Any]:
    fallback_inventory = max(policy.get("rop", 0) + policy.get("oq", 0), 0)
    inventory = opening_inventory(test_rows, fallback_inventory) if initial_inventory is None else max(0, initial_inventory)
    on_order: list[tuple[date, int]] = []
    total_demand = 0.0
    served = 0.0
    stockout_days = 0
    shortage_units = 0.0
    inv_sum = 0.0
    num_orders = 0
    lead_days = max(1, int(round(stats["mean_lead_time"])))
    rop = int(policy.get("rop", 0))
    order_up_to_level: int | None = None
    raw_out_to = policy.get("out_to")
    is_order_up_to = raw_out_to is not None
    if is_order_up_to:
        order_up_to_level = max(0, int(raw_out_to))
        if order_up_to_level <= rop:
            raise ValueError("order-up-to level must exceed reorder point")
    oq = max(1, int(policy.get("oq", 1)))

    working = [r for r in test_rows if is_working_day(r)]
    for index, r in enumerate(working):
        current = parse_date(r["date"])
        arrived = [q for due, q in on_order if due <= current]
        if arrived:
            inventory += sum(arrived)
            on_order = [(due, q) for due, q in on_order if due > current]
        dem = demand(r)
        total_demand += dem
        fulfilled = min(inventory, dem)
        served += fulfilled
        inventory -= fulfilled
        if fulfilled < dem:
            stockout_days += 1
            shortage_units += dem - fulfilled
        position = inventory + sum(q for _, q in on_order)
        if position <= rop:
            order_quantity = int(max(0, order_up_to_level - position)) if order_up_to_level is not None else oq
            if order_quantity == 0:
                continue
            if arrival_mode == "working_days":
                due_index = index + lead_days
                due = (
                    parse_date(working[due_index]["date"])
                    if due_index < len(working)
                    else current + timedelta(days=lead_days * 7)
                )
            else:
                due = current + timedelta(days=lead_days)
            on_order.append((due, order_quantity))
            num_orders += 1
        inv_sum += inventory

    n = max(len(working), 1)
    avg_inventory = inv_sum / n
    holding = avg_inventory * stats["annual_holding_cost_per_unit"] * n / ANNUAL_WORKING_DAYS
    ordering = num_orders * stats["ordering_cost"]
    shortage_cost = shortage_units * max(0.0, shortage_penalty_per_unit)
    return {
        "fill_rate_pct": (served / total_demand * 100.0) if total_demand else 100.0,
        "total_cost": holding + ordering + shortage_cost,
        "holding_cost": holding,
        "ordering_cost": ordering,
        "shortage_cost": shortage_cost,
        "stockout_days": stockout_days,
        "shortage_units": shortage_units,
        "avg_inventory": avg_inventory,
        "num_orders": num_orders,
        "test_days": len(working),
        "total_demand": total_demand,
    }


def baseline_for_item(rows: list[dict[str, str]], cutoff: str = TRAIN_CUTOFF, valid_end: str | None = None) -> dict[str, Any]:
    train, _ = split_rows(rows, cutoff, valid_end)
    stats = compute_stats(train)
    rq = make_rq_policy(stats)
    sap = make_sap_policy(stats)
    return {
        "cv_wd": stats["cv_wd"],
        "regime": "Dead stock" if stats["mean_daily_demand"] == 0 else ("Lumpy" if stats["cv_wd"] >= 1 else "Smooth"),
        "selected_model": "universal_rq",
        "recommended_safety_stock": rq["ss"],
        "reorder_point": rq["rop"],
        "order_quantity": rq["oq"],
        "max_storage_units": stats["max_storage_units"],
        "current_safety_stock_units": sap["ss"],
        "current_sap_slt_days": stats["sap_slt"],
    }


def aggregate(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        return {}
    fill = [m["fill_rate_pct"] for m in metrics]
    costs = [m["total_cost"] for m in metrics]
    stockout = [m["stockout_days"] for m in metrics]
    total_demand = sum(m["total_demand"] for m in metrics)
    served = sum(m["total_demand"] * m["fill_rate_pct"] / 100.0 for m in metrics)
    return {
        "n_materials": len(metrics),
        "mean_fill_rate_pct": round(mean(fill), 4),
        "agg_fill_rate_pct": round(served / total_demand * 100.0, 4) if total_demand else 0.0,
        "pct_ge_95": round(100.0 * sum(1 for x in fill if x >= 95.0) / len(fill), 4),
        "zero_stockout_pct": round(100.0 * sum(1 for x in stockout if x == 0) / len(stockout), 4),
        "mean_total_cost": round(mean(costs), 4),
        "total_stockout_days": int(sum(stockout)),
        "mean_stockout_days": round(mean(stockout), 4),
    }


def data_summary() -> dict[str, Any]:
    grouped = load_grouped_rows()
    keys = eligible_item_keys(grouped)
    by_plant: dict[str, int] = {}
    for key in keys:
        plant = key.split("__", 1)[0]
        by_plant[plant] = by_plant.get(plant, 0) + 1
    all_dates = [r["date"] for rows in grouped.values() for r in rows]
    return {
        "data_csv": str(data_csv()),
        "rows": sum(len(rows) for rows in grouped.values()),
        **_LOAD_METADATA,
        "plant_material_pairs": len(grouped),
        "date_min": min(all_dates) if all_dates else None,
        "date_max": max(all_dates) if all_dates else None,
        "train_cutoff": TRAIN_CUTOFF,
        "min_train_working_days": MIN_TRAIN_WORKING_DAYS,
        "min_validation_working_days": MIN_VALID_WORKING_DAYS,
        "eligible_materials": len(keys),
        "eligible_by_plant": dict(sorted(by_plant.items())),
        **_CALENDAR_REPAIR_METADATA,
    }


def main() -> None:
    import json

    print(json.dumps(data_summary(), indent=2))


if __name__ == "__main__":
    main()
