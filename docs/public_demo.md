# Public Synthetic Demo

The public demo exercises data loading, calendar repair, eligibility, policy-artifact parsing, and deterministic simulation without credentials or network access. Its pseudo-random values come from a fixed seed and are not sampled from the confidential study data.

## Run

From the repository root:

```bash
python3 -m inventory_llm.synthetic_demo
python3 -m unittest discover -s tests -v
```

The command recreates `data/synthetic_inventory.csv` and writes local detailed outputs under `outputs/synthetic_demo/`. Those detailed outputs are ignored by Git. The committed `outputs/synthetic_demo_summary.json` contains aggregate fixture results only.

## Fixture

The fixture covers three synthetic plant-material pairs from 2026-01-01 through 2026-05-31:

- `SYN_A__MAT_SMOOTH`: smooth demand.
- `SYN_B__MAT_LUMPY`: intermittent high-volume demand.
- `SYN_C__MAT_REPAIRED`: intermittent demand with an all-zero source calendar, repaired from the other two synthetic plants.

All 24 source columns are present. The values use generic ranges and fixed pseudo-random streams. The candidate artifacts are generated deterministically from the fixture and explicitly marked `deterministic_synthetic_not_llm`; they are not LLM outputs and do not reproduce the manuscript results.

## Study Boundary

`scripts/export_public.py --dest <outside-repository-directory>` creates aggregate-only study, review-evidence, and integrity-manifest files in a screened public snapshot. The primary comparison uses the common cohort meeting identical MOQ and per-material capacity rules, but contains no material rows or identifiers. The operational CSV, material-level artifacts, private inference adapter, credentials, and runtime metadata are not distributed.
