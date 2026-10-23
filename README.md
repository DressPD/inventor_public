# InventOR

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22262051.svg)](https://doi.org/10.5281/zenodo.22262051)

This repository contains a confidentiality-screened research release.

## Reproducibility Boundary

The public synthetic benchmark fully reproduces the released software method:
fixture generation, schema handling, calendar repair, eligibility, policy-artifact
parsing, and deterministic policy simulation. It runs offline with a fixed seed
and no credentials or network access.

It does not reproduce the manuscript's confidential-study numerical findings.
Those findings depended on confidential operational data and a private enterprise
LLM deployment. The release provides aggregate-only study evidence and integrity
hashes for audit, but does not include the source rows, material-level inputs,
artifacts, credentials, or sufficient runtime metadata to independently regenerate
the 365-material study outputs.

The synthetic benchmark is methodological and software replication, not a
numerical reproduction of the confidential study.

## Replication on the masked release

The company approved the release of a masked version of the study panel
(`data/masked_release/masked_inventory_panel.csv`, 233,078 daily records, 411
plant-material pairs). Plants are labelled PL1, PL2 and PL3 (corresponding to
Plants A, B and C of the manuscript), material identifiers are pseudonymized,
and quantities and prices are multiplied by secret per-pair factors; the
factors, the salt and the source data are not released. Dates and plant
structure are unchanged.

- `outputs/runs/mf-01`, `mf-02`, `mf-03`, `mf-noerp` hold the frozen policies of
  the original runs, rescaled to the masked panel (`output.json` only).
- `outputs/runs/run-m1`, `run-m2`, `run-m3` hold three fresh LLM generations on
  the masked panel with the unchanged prompt (policy, metadata and prompt per
  material; session identifiers are replaced by a hash prefix and the raw
  platform responses are not released). Run m1 produced 364 and
  runs m2 and m3 produced 365 of the 365 policies; 38 records of run m1 carry a
  `runner_hash_amendment` (authentication handling only; the original hash is in
  `runner_code_sha256_original`).
- `outputs/masked_replication_evidence.json` is the scored replication
  (`python3 scripts/build_masked_replication_evidence.py`, offline).

Scoring needs only the standard-library simulator, no network or credentials.
The three masked runs reproduce the original pattern: the LLM is 11--12% cheaper
than the ERP-derived parameters and 5--6%, 7--9% and 16--18% costlier than the
history-only, Croston/SBA and empirical-quantile code arms, with mean cost within
1% of the original runs. The LLM generation itself still needs the private
enterprise deployment and cannot be rerun publicly.

## Release Contents

- deterministic synthetic inventory data generated from a fixed seed;
- a credential-free execution pipeline for preprocessing, policy parsing, and simulation;
- anonymized aggregate evidence from three full runs (Runs 1--3) with the final system prompt, an ablation run without ERP planning parameters, hard-limit replay, capacity-trajectory, information-asymmetry and Plant C calendar sensitivity analyses;
- manuscript source, figures, references, highlights, and compiled PDF; and
- prompt specifications documenting the intended LLM interaction.

No operational row, original material identifier, credential,
private inference adapter, or private runtime metadata is included. The masked
panel and masked-run outputs use pseudonymized identifiers and scaled quantities.

## Quick Start

Python 3.10 or newer is sufficient. The public synthetic path uses only the
standard library and makes no network calls.

```bash
python3 -m inventory_llm.synthetic_demo
python3 -m unittest discover -s tests -v
```

The demo recreates `data/synthetic_inventory.csv` with seed `20260718`, builds
three explicitly synthetic candidate artifacts, parses them, and evaluates the
candidate, SAP-derived, and SAP-SLT-informed OR arms. Detailed local outputs are
written to `outputs/synthetic_demo/` and ignored by Git.

The committed fixture summary is `outputs/synthetic_demo_summary.json`. It is a
software demonstration, not study evidence and not an LLM evaluation. A matching
result confirms deterministic public-method reproduction, not regeneration of
the confidential-study results.

## Study Evidence

`outputs/agentic_policy_backtest_summary.json` contains aggregate-only results
from the confidential study cohort. It includes cohort aggregates, anonymized
plant aggregates, demand-concentration sensitivity, shortage totals, and paired
diagnostics. It contains no material rows or failure lists.

`outputs/review_evidence.json` records common-feasibility, outlier, working-day
primary, and calendar-day-arrival sensitivity evidence. `outputs/run_manifest.json` records
aggregate integrity hashes and unavailable inference metadata. `outputs/three_run_evidence.json`
reports aggregate-only policy distribution summaries for the three full runs; it does not
establish verification of the deployed model identifier or inference settings.
`outputs/primary_evidence.json` holds the primary hard-limit replay results for all arms
(including cost decomposition, plant and regime groups, shortage-penalty and calendar
sensitivities), `outputs/information_asymmetry_evidence.json` the ERP-information comparisons
and the ablation without ERP planning parameters, `outputs/capacity_trajectory_evidence.json`
the storage-limit trajectory checks, and `outputs/plantc_calendar_sensitivity.json` the Plant C
calendar sensitivities.

The study inference stage cannot be rerun publicly. It depended on confidential
operational data and a private enterprise LLM deployment. The aggregate evidence
is auditable against the published integrity record, but not independently
regenerable from this repository. See `docs/methodology.md` and
`docs/public_demo.md`.

## Manuscript

The reviewed manuscript is available at `manuscript/main.pdf`. Rebuild it with:

```bash
cd manuscript
pdflatex -interaction=nonstopmode -halt-on-error Figure_1_Workflow.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_2_Cost_Decomposition.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_3_Segments.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_S1_Three_Run_Reproducibility.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

## Repository Layout

```text
data/synthetic_inventory.csv                  deterministic synthetic fixture
inventory_llm/core.py                         data, baselines, simulator
inventory_llm/policy_backtest.py              policy-artifact parser/reference backtest
inventory_llm/synthetic_demo.py                offline public pipeline
outputs/agentic_policy_backtest_summary.json  anonymized study aggregates
outputs/review_evidence.json                  aggregate review evidence
outputs/run_manifest.json                     aggregate integrity manifest
outputs/three_run_evidence.json               aggregate three-run evidence
outputs/primary_evidence.json                 primary hard-limit replay evidence
outputs/information_asymmetry_evidence.json   ERP-information comparisons and ablation
outputs/capacity_trajectory_evidence.json     storage-limit trajectory checks
outputs/plantc_calendar_sensitivity.json      Plant C calendar sensitivities
outputs/synthetic_demo_summary.json            synthetic aggregate demo
manuscript/                                    article source and PDF
prompts/                                       intended prompt specifications
tests/                                         offline regression tests
```
