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

A masked panel and sanitized frozen policies support offline scoring, without credentials. Run `python3 scripts/verify_public.py --recompute` to verify file hashes and rebuild both masked evidence files, the six-run table and Figures 2–4 source files. The six-run cohort contains 338 pairs; O1*–O3* are rescaled frozen original policies and M1–M3 fresh masked generations on the same underlying panel. The main ranking persists, but masked costs cannot be compared directly with confidential unscaled means. Raw operational inputs, masking factors and proprietary inference access remain unavailable. Provenance amendments retain their history and original hashes.

## Study Boundary

The private exporter creates a screened snapshot containing approved masked rows and sanitized masked artifacts, original aggregate evidence, scoring software and a hash manifest. The public snapshot cannot regenerate confidential original inference or raw-scale study results. Synthetic tests exercise software behavior; masked replay reproduces public numerical results; neither establishes independent external validation. Static policy quantities satisfy MOQ, but capacity-clipped simulated orders can violate MOQ.
