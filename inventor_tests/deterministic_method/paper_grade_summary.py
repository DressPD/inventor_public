from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from inventor_tests._utils import safe_float


PAPER_COLUMN_POLICIES = {
    "inventor_selected": ("inventor_fill_rate_pct", "inventor_total_cost"),
    "sap_static": ("sap_fill_rate_pct", "sap_total_cost"),
    "universal_rq": ("universal_rq_fill_rate_pct", "universal_rq_total_cost"),
}


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path.name


def _column_validation(rows: list[dict[str, str]], archive: dict[str, Any]) -> dict[str, Any]:
    validation: dict[str, Any] = {}
    for policy, (fill_col, cost_col) in PAPER_COLUMN_POLICIES.items():
        archived = archive.get("aggregate", {}).get(policy, {})
        fill = round(_mean([safe_float(row.get(fill_col)) for row in rows]), 4)
        cost = round(_mean([safe_float(row.get(cost_col)) for row in rows]), 4)
        validation[policy] = {
            "source_columns": [fill_col, cost_col],
            "mean_fill_rate_pct": fill,
            "archived_mean_fill_rate_pct": archived.get("mean_fill_rate_pct"),
            "mean_total_cost": cost,
            "archived_mean_total_cost": archived.get("mean_total_cost"),
            "matches_archive": (
                fill == archived.get("mean_fill_rate_pct")
                and cost == archived.get("mean_total_cost")
            ),
        }
    return validation


def build_paper_grade_summary(targets_csv: Path, archive_json: Path, output_json: Path) -> dict[str, Any]:
    rows = _load_rows(targets_csv)
    archive = json.loads(archive_json.read_text(encoding="utf-8"))
    result = dict(archive)
    result["evaluation_source"] = {
        "mode": "paper_grade_replay",
        "targets_csv": _display_path(targets_csv),
        "archive_json": _display_path(archive_json),
        "paper_column_policies": sorted(PAPER_COLUMN_POLICIES),
        "archived_aggregate_policies": [
            policy for policy in result.get("policies", []) if policy not in PAPER_COLUMN_POLICIES
        ],
        "note": (
            "Default paper replay preserves the frozen paper artifact. "
            "inventor_selected, sap_static, and universal_rq are validated against "
            "paper-grade target CSV columns; aggregate-only comparators are retained "
            "from the archived paper artifact because per-item columns are not stored. "
            "Use paper-backtest --mode simulate for raw simulator reruns."
        ),
    }
    result["source_validation"] = _column_validation(rows, archive)
    result["items_evaluated"] = len(rows)
    result["items_skipped"] = 0
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
