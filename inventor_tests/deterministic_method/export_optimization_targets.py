from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGETS = ROOT.parent / "sample_artifacts" / "target_ranking.csv"


def export_material_targets(output_path: str | Path) -> dict[str, Any]:
    path = Path(output_path)
    if not path.exists():
        raise FileNotFoundError(f"Target ranking file not found: {path}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    top = rows[:10]
    return {
        "evaluated_items": len(rows),
        "skipped_items": None,
        "output_path": str(path),
        "top_items": [
            {
                "item_key": row.get("item_key"),
                "route_used": row.get("route_used"),
                "hard_escalation_flag": row.get("hard_escalation_flag"),
                "fill_gain_vs_sap_pct_pts": row.get("fill_gain_vs_sap_pct_pts"),
                "fill_gain_vs_universal_rq_pct_pts": row.get("fill_gain_vs_universal_rq_pct_pts"),
                "opportunity_score": row.get("opportunity_score"),
            }
            for row in top
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize current optimization target ranking.")
    parser.add_argument("--output", default=str(DEFAULT_TARGETS))
    args = parser.parse_args()
    print(json.dumps(export_material_targets(args.output), indent=2))


if __name__ == "__main__":
    main()
