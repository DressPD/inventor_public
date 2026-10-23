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

## Reproducibility Boundary

This fixture fully reproduces the released method and software behavior: fixture
generation, schema handling, calendar repair, eligibility, policy parsing, and
deterministic policy simulation. It does not reproduce the confidential-study
numbers reported in the manuscript. Synthetic demand, lead-time, capacity, ERP
baseline, and candidate-policy values are intentionally independent of the
confidential study data.

## Masked-release replication

A masked panel (pseudonymized identifiers, secretly scaled quantities and prices, unchanged dates) and three masked re-runs (`run-m1..m3`) are part of the release; `python3 scripts/build_masked_replication_evidence.py` rescores them offline and rebuilds `outputs/masked_replication_evidence.json`. Costs are within 1% of the original runs and the pattern is the same (LLM about 11--12% cheaper than the ERP-derived parameters, 5--6%, 7--9% and 16--18% costlier than history-only, Croston/SBA and empirical-quantile code). The masking factors and the source data are not released. Run m1 produced 364 of 365 policies, runs m2 and m3 365; 38 run-m1 metadata records carry a documented runner-hash amendment (authentication handling only).

## Study Boundary

`scripts/export_public.py --dest <outside-repository-directory>` creates aggregate-only study, review-evidence, and integrity-manifest files in a screened public snapshot. The primary comparison uses the common cohort meeting identical MOQ and per-material capacity rules, but contains no material rows or identifiers. The operational CSV, material-level artifacts, private inference adapter, credentials, and complete runtime metadata are not distributed. Published hashes support audit by an authorized data holder; they cannot reconstruct confidential inputs or independently regenerate study results.
