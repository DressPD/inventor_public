#!/usr/bin/env python3
"""Score the masked-release re-runs (run-m1..m3) against the frozen scaled
original runs (mf-01..mf-03) and write outputs/masked_replication_evidence.json.

Run from inventor_project/:
    python3 scripts/build_masked_replication_evidence.py
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASKED_CSV = ROOT / "data" / "masked_release" / "masked_inventory_panel.csv"
os.environ["INVENTOR_DATA_CSV"] = str(MASKED_CSV)
sys.path.insert(0, str(ROOT))

from inventory_llm import policy_backtest as pb  # noqa: E402

MASKED_RUNS = ["run-m1", "run-m2", "run-m3"]
ORIGINAL_RUNS = ["mf-01", "mf-02", "mf-03"]
ARMS = {
    "sap_static": "ERP-derived parameters",
    "or_cold": "History-only code",
    "or_sba": "Croston/SBA code",
    "or_empirical": "Empirical-quantile code",
    "or_tuned": "Simulation-tuned code",
}
PLANTS = ["ALL", "PL1", "PL2", "PL3"]


def score(run_id: str) -> dict:
    os.environ["INVENTOR_RUN_ID"] = run_id
    res = pb.build_backtest(
        run_id=run_id, enforce_capacity=True, shortage_penalty_multiplier=0.0
    )
    return {
        "n_targets": res["n_targets"],
        "n_backtested": res["n_backtested"],
        "n_invalid": len(res["invalid_outputs"]),
        "n_missing": len(res["missing_outputs"]),
        "by_key": {x["item_key"]: x for x in res["results"]},
    }


def valid(rec: dict | None) -> bool:
    return bool(rec and rec.get("llm_pure"))


def main() -> None:
    runs = {r: score(r) for r in MASKED_RUNS + ORIGINAL_RUNS}
    out = {
        "scope": "hard-limit replay on the masked release",
        "masked_runs": {},
        "originals": {
            r: {k: runs[r][k] for k in ("n_targets", "n_backtested", "n_invalid", "n_missing")}
            for r in ORIGINAL_RUNS
        },
    }
    for rn in MASKED_RUNS:
        mk = runs[rn]["by_key"]
        entry = {
            k: runs[rn][k] for k in ("n_targets", "n_backtested", "n_invalid", "n_missing")
        }
        entry["plants"] = {}
        keys_all = [k for k, v in mk.items() if valid(v)]
        for grp in PLANTS:
            ks = [k for k in keys_all if grp == "ALL" or k.split("__")[0] == grp]
            if not ks:
                continue
            llm = st.mean(mk[k]["llm_pure"]["total_cost"] for k in ks)
            row = {
                "n": len(ks),
                "llm_cost": round(llm, 2),
                "llm_fill_pct": round(
                    st.mean(mk[k]["llm_pure"]["fill_rate_pct"] for k in ks), 2
                ),
                "vs_arm_pct": {},
                "cost_ratio_to": {},
            }
            for a in ARMS:
                if not all(mk[k].get(a) for k in ks):
                    continue
                av = st.mean(mk[k][a]["total_cost"] for k in ks)
                row["vs_arm_pct"][a] = round(100 * (llm / av - 1), 1)
            for o in ORIGINAL_RUNS + [m for m in MASKED_RUNS if m != rn]:
                com = [k for k in ks if valid(runs[o]["by_key"].get(k))]
                if not com:
                    continue
                rv = st.mean(runs[o]["by_key"][k]["llm_pure"]["total_cost"] for k in com)
                mv = st.mean(mk[k]["llm_pure"]["total_cost"] for k in com)
                row["cost_ratio_to"][o] = {"n": len(com), "ratio": round(mv / rv, 3)}
            entry["plants"][grp] = row
        out["masked_runs"][rn] = entry

    dest = ROOT / "outputs" / "masked_replication_evidence.json"
    dest.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", dest.relative_to(ROOT))
    for rn, e in out["masked_runs"].items():
        a = e["plants"]["ALL"]
        print(rn, e["n_backtested"], "invalid", e["n_invalid"], "missing", e["n_missing"],
              "cost", a["llm_cost"], a["vs_arm_pct"])


if __name__ == "__main__":
    main()
