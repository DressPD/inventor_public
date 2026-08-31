"""Run an offline, deterministic synthetic demonstration of the pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from inventory_llm import core, policy_backtest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED = 20260718
CSV_COLUMNS = [
    "date",
    "plant_code",
    "material",
    "material_note",
    "safety_time_workdays_actual",
    "actual_demand",
    "delivery_time",
    "minimum_order_quantity",
    "stock_correction",
    "scrap",
    "safety_stock_units",
    "supplier_plant_distance",
    "reliability_random",
    "reliability_calc",
    "inventory_on_hand",
    "goods_receipt_qty",
    "review_period_days",
    "unit_cost",
    "holding_cost_rate",
    "ordering_cost",
    "is_working_day",
    "is_ordering_day",
    "service_level_target",
    "transportation_network",
]


def _date_range(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _demand(profile: str, rng: random.Random, working: bool) -> int:
    if not working:
        return 0
    if profile == "smooth":
        return rng.randint(7, 15)
    if profile == "lumpy":
        return rng.randint(25, 70) if rng.random() < 0.22 else 0
    return rng.randint(4, 13) if rng.random() < 0.65 else 0


def generate_synthetic_csv(path: Path, seed: int = DEFAULT_SEED) -> None:
    """Write a full-schema fixture generated independently from private data."""
    profiles = [
        ("SYN_A", "MAT_SMOOTH", "smooth", 80, 240, 12.5, 0),
        ("SYN_B", "MAT_LUMPY", "lumpy", 45, 320, 28.0, 1),
        ("SYN_C", "MAT_REPAIRED", "intermittent", 60, 260, 18.0, 2),
    ]
    days = _date_range(date(2026, 1, 1), date(2026, 5, 31))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        for plant, material, profile, safety_stock, opening_inventory, unit_cost, stream in profiles:
            rng = random.Random(seed + stream * 10_000)
            for index, current in enumerate(days):
                working = current.weekday() < 5
                demand = _demand(profile, rng, working)
                source_working = working and plant != "SYN_C"
                writer.writerow({
                    "date": current.isoformat(),
                    "plant_code": plant,
                    "material": material,
                    "material_note": f"Synthetic {profile} fixture",
                    "safety_time_workdays_actual": "1",
                    "actual_demand": str(demand),
                    "delivery_time": str(rng.randint(1, 4)) if working and index % 9 == 0 else "",
                    "minimum_order_quantity": "25",
                    "stock_correction": "0",
                    "scrap": "0",
                    "safety_stock_units": str(safety_stock),
                    "supplier_plant_distance": str(100 + stream * 75),
                    "reliability_random": "0.96",
                    "reliability_calc": "0.95",
                    "inventory_on_hand": str(opening_inventory) if current == date(2026, 3, 10) else "",
                    "goods_receipt_qty": "0",
                    "review_period_days": "7",
                    "unit_cost": str(unit_cost),
                    "holding_cost_rate": "0.12",
                    "ordering_cost": "75",
                    "is_working_day": "1" if source_working else "0",
                    "is_ordering_day": "1" if source_working else "0",
                    "service_level_target": "0.95",
                    "transportation_network": "Synthetic road",
                })


def _artifact(item_key: str, stats: dict[str, Any]) -> dict[str, Any]:
    policy = core.make_rq_policy(stats)
    return {
        "material_id": item_key,
        "fixture_provenance": "deterministic_synthetic_not_llm",
        "policy": {
            "safety_stock": policy["ss"],
            "reorder_point": max(1, policy["rop"]),
            "order_quantity": max(1, policy["oq"]),
        },
        "research_insights": {"selected_model": "(r,Q)"},
    }


def build_demo(data_path: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    grouped = core.load_grouped_rows(data_path)
    valid_end = core.validation_end(grouped)
    targets = core.eligible_item_keys(grouped, valid_end=valid_end)
    rows: list[dict[str, Any]] = []
    artifacts: dict[str, dict[str, Any]] = {}
    for item_key in targets:
        train, test = core.split_rows(grouped[item_key], valid_end=valid_end)
        stats = core.compute_stats(train)
        artifact = _artifact(item_key, stats)
        candidate = policy_backtest.parse_policy_artifact(artifact, stats)
        if candidate is None:
            raise RuntimeError(f"Synthetic artifact is not scoreable: {item_key}")
        or_policy = core.make_rq_policy(stats)
        initial_inventory = core.opening_inventory(test, or_policy["rop"] + or_policy["oq"])
        rows.append({
            "item_key": item_key,
            "synthetic_candidate": core.simulate(test, candidate, stats, initial_inventory),
            "sap_derived": core.simulate(test, core.make_sap_policy(stats), stats, initial_inventory),
            "sap_slt_informed_or": core.simulate(test, or_policy, stats, initial_inventory),
            "candidate_policy": {key: candidate[key] for key in ("rop", "oq", "ss")},
        })
        artifacts[item_key] = artifact
    return {
        "demo_type": "deterministic_synthetic_offline",
        "seed": seed,
        "train_cutoff": core.TRAIN_CUTOFF,
        "valid_end": valid_end,
        "n_targets": len(targets),
        "n_backtested": len(rows),
        "calendar_repair": dict(core._CALENDAR_REPAIR_METADATA),
        "aggregate": {
            "synthetic_candidate": core.aggregate([row["synthetic_candidate"] for row in rows]),
            "sap_derived": core.aggregate([row["sap_derived"] for row in rows]),
            "sap_slt_informed_or": core.aggregate([row["sap_slt_informed_or"] for row in rows]),
        },
        "artifacts": artifacts,
        "results": rows,
    }


def _public_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key not in {"artifacts", "results"}}


def publish_fixture(project_root: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Create tracked synthetic input and aggregate-only demonstration evidence."""
    data_path = project_root / "data" / "synthetic_inventory.csv"
    generate_synthetic_csv(data_path, seed)
    result = build_demo(data_path, seed)
    summary = _public_summary(result)
    output = project_root / "outputs" / "synthetic_demo_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def run_demo(project_root: Path = PROJECT_ROOT, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    """Generate the fixture and write local detailed artifacts and backtest results."""
    data_path = project_root / "data" / "synthetic_inventory.csv"
    output_root = project_root / "outputs" / "synthetic_demo"
    if output_root.exists():
        shutil.rmtree(output_root)
    generate_synthetic_csv(data_path, seed)
    result = build_demo(data_path, seed)
    for item_key, artifact in result["artifacts"].items():
        artifact_path = output_root / "agentic_runs" / item_key / "output.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "backtest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (output_root / "backtest.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "item_key", "candidate_fill", "candidate_cost", "sap_fill", "sap_cost",
            "or_fill", "or_cost", "candidate_ss", "candidate_rop", "candidate_oq",
        ]
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in result["results"]:
            writer.writerow({
                "item_key": row["item_key"],
                "candidate_fill": row["synthetic_candidate"]["fill_rate_pct"],
                "candidate_cost": row["synthetic_candidate"]["total_cost"],
                "sap_fill": row["sap_derived"]["fill_rate_pct"],
                "sap_cost": row["sap_derived"]["total_cost"],
                "or_fill": row["sap_slt_informed_or"]["fill_rate_pct"],
                "or_cost": row["sap_slt_informed_or"]["total_cost"],
                "candidate_ss": row["candidate_policy"]["ss"],
                "candidate_rop": row["candidate_policy"]["rop"],
                "candidate_oq": row["candidate_policy"]["oq"],
            })
    (output_root / "summary.json").write_text(
        json.dumps(_public_summary(result), indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic offline InventOR demo.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    args = parser.parse_args()
    result = run_demo(args.project_root.resolve(), args.seed)
    print(json.dumps({
        "data": str(args.project_root / "data" / "synthetic_inventory.csv"),
        "outputs": str(args.project_root / "outputs" / "synthetic_demo"),
        "n_backtested": result["n_backtested"],
        "aggregate": result["aggregate"],
    }, indent=2))


if __name__ == "__main__":
    main()
