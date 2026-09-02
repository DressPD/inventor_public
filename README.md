# InventOR

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22262052.svg)](https://doi.org/10.5281/zenodo.22262052)

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

## Release Contents

- deterministic synthetic inventory data generated from a fixed seed;
- a credential-free execution pipeline for preprocessing, policy parsing, and simulation;
- anonymized aggregate evidence from Run 1 and two current-runner reruns (Run 2 and Run 3);
- manuscript source, figures, references, highlights, and compiled PDF; and
- prompt specifications documenting the intended LLM interaction.

No operational row, material identifier, material-level study artifact, credential,
private inference adapter, or private runtime metadata is included.

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
reports aggregate-only policy distribution summaries for Run 1 and two
post-hoc current-runner reruns (Run 2 and Run 3); it does not establish reproduction of the Run 1 deployment.

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
pdflatex -interaction=nonstopmode -halt-on-error Figure_2_Comparison.tex
pdflatex -interaction=nonstopmode -halt-on-error Figure_3_Three_Run_Reproducibility.tex
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
outputs/synthetic_demo_summary.json            synthetic aggregate demo
manuscript/                                    article source and PDF
prompts/                                       intended prompt specifications
tests/                                         offline regression tests
```
