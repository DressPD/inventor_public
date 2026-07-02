import argparse
import csv
import json
import os
import sys
from pathlib import Path
from collections import Counter

from inventor_tests.deterministic_method.stats_calculator import build_item_key, compute_stats, compute_policy_values
from inventor_tests.deterministic_method.slt_calculator import compute_slt, compare_slt_vs_sap
from inventor_tests.orchestration.llm_api_client import validate_credentials
from inventor_tests.orchestration.ensemble_runner import run_ensemble
from inventor_tests.orchestration.ensemble_aggregator import aggregate_runs, POLICY_FALLBACK
from inventor_tests.deterministic_method.model_solvers import route_to_solver
from inventor_tests.deterministic_method.hard_flag import evaluate_hard_flag

CSV_PATH = "data/20260619_400_Mat_2_plants.csv"
OUTPUT_DIR = Path("batches/ensemble_results")
DEFAULT_MATERIALS = ["PLANT_A__MATERIAL_0001", "PLANT_A__MATERIAL_0002", "PLANT_A__MATERIAL_0003"]


def _group_key(row: dict, group_by: str) -> str:
    material_id = row["material"].strip()
    plant_code = row.get("plant_code", "").strip()
    if group_by == "material" or not plant_code:
        return material_id
    return build_item_key(material_id, plant_code)


def load_csv(csv_path: str, group_by: str) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            mat_id = _group_key(row, group_by)
            grouped.setdefault(mat_id, []).append(dict(row))
    return grouped


def process_one(
    item_key: str,
    rows: list[dict],
    api_key: str,
    bearer: str,
    n_runs: int,
    max_workers: int,
    retries: int,
    output_dir: Path,
) -> dict:
    base_material_id = rows[0].get("material", item_key)
    plant_code = rows[0].get("plant_code", "")

    stats = compute_stats(item_key, rows)
    policy_values = compute_policy_values(stats)
    slt = compute_slt(stats)
    slt["comparison_action"] = compare_slt_vs_sap(stats, slt)
    hard_flag = evaluate_hard_flag(stats, policy_values, slt)

    skip_reasons: list[str] = []
    if stats.get("positive_demand_rows", 0) <= 0:
        skip_reasons.append("no_positive_demand_rows")
    if stats["mean_daily_demand"] <= 0:
        skip_reasons.append("non_positive_mean_daily_demand")
    if stats["d_max_calendar"] <= 0:
        skip_reasons.append("non_positive_peak_demand")

    if skip_reasons:
        final = {
            "status": "skipped_invalid_input",
            "item_key": item_key,
            "material_id": base_material_id,
            "plant_code": plant_code,
            "skip_reasons": skip_reasons,
            "stats": stats,
            "policy_values": policy_values,
            "slt": slt,
            "hard_flag": hard_flag,
            "ensemble_runs": 0,
            "aggregated": {
                "selected_model": POLICY_FALLBACK,
                "model_confidence": "UNCERTAIN",
                "boundary_risk": "HIGH",
                "risk_confidence": "UNCERTAIN",
                "escalation_flag": "YES",
                "n_runs": 0,
                "n_valid": 0,
                "agreement_rate": 0.0,
                "reason": "skipped_invalid_input",
            },
            "solver_result": None,
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{item_key}.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(final, fh, indent=2, default=str)
        return final

    runs = run_ensemble(
        item_key, stats, policy_values, slt, api_key, bearer, n_runs, max_workers, retries
    )

    if runs:
        aggregated = aggregate_runs(runs)
    else:
        aggregated = {
            "selected_model": POLICY_FALLBACK,
            "confidence": "UNCERTAIN",
            "reason": "no ensemble runs completed",
        }

    model = aggregated.get("selected_model", POLICY_FALLBACK)
    confidence = aggregated.get("model_confidence", "UNCERTAIN")
    merged_stats = {**stats, **policy_values}
    solver_result = route_to_solver(model, confidence, merged_stats, rows)

    final = {
        "status": "processed",
        "item_key": item_key,
        "material_id": base_material_id,
        "plant_code": plant_code,
        "stats": stats,
        "policy_values": policy_values,
        "slt": slt,
        "hard_flag": hard_flag,
        "ensemble_runs": len(runs) if runs else 0,
        "aggregated": aggregated,
        "solver_result": solver_result,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{item_key}.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(final, fh, indent=2, default=str)

    return final


def main() -> None:
    parser = argparse.ArgumentParser(
        description="InventOR ensemble orchestrator for material optimization."
    )
    parser.add_argument(
        "--csv-path",
        default=CSV_PATH,
        help="Input semicolon-delimited CSV path.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory for per-material JSON outputs.",
    )
    parser.add_argument(
        "--group-by",
        choices=["auto", "material", "plant-material"],
        default="auto",
        help="Grouping key for rows. auto uses plant-material when materials repeat across plants.",
    )
    parser.add_argument(
        "--material",
        metavar="MATERIAL_ID",
        help="Process a single material by ID.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="all_materials",
        help="Process all materials found in the CSV.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip materials whose output JSON already exists in OUTPUT_DIR.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        metavar="N",
        help="Number of ensemble runs per material (default: 5).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        metavar="N",
        help="Max parallel workers per ensemble run (default: 5).",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        metavar="N",
        help="Retry count for failed API calls (default: 2).",
    )
    parser.add_argument(
        "--skip",
        default="",
        metavar="MAT1,MAT2,...",
        help="Comma-separated list of material IDs to skip.",
    )
    args = parser.parse_args()

    api_key, bearer = validate_credentials()

    requested_group_by = args.group_by
    if requested_group_by == "auto":
        with open(args.csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            material_counts = Counter(row["material"].strip() for row in reader)
        group_by = "plant-material" if any(count > 1 for count in material_counts.values()) else "material"
    else:
        group_by = requested_group_by

    data = load_csv(args.csv_path, group_by)
    output_dir = Path(args.output_dir)

    if args.material:
        targets = [args.material]
    elif args.all_materials:
        targets = list(data.keys())
    else:
        targets = list(DEFAULT_MATERIALS)

    skip_set: set[str] = set()
    if args.skip:
        skip_set = {m.strip() for m in args.skip.split(",") if m.strip()}
    targets = [m for m in targets if m not in skip_set]

    if args.resume:
        targets = [m for m in targets if not (output_dir / f"{m}.json").exists()]

    n_total = len(targets)
    n_success = 0

    for idx, item_key in enumerate(targets, start=1):
        print(f"[{idx}/{n_total}] Processing {item_key} ...", file=sys.stderr)
        if item_key not in data:
            print(f"  WARNING: {item_key} not found in CSV, skipping.", file=sys.stderr)
            continue
        try:
            process_one(
                item_key=item_key,
                rows=data[item_key],
                api_key=api_key,
                bearer=bearer,
                n_runs=args.runs,
                max_workers=args.workers,
                retries=args.retries,
                output_dir=output_dir,
            )
            n_success += 1
            print(f"  OK: {item_key}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {item_key} failed: {exc}", file=sys.stderr)

    print(
        f"\nDone: {n_success}/{n_total} materials processed successfully.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
