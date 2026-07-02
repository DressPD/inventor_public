---
title: "InventOR 2-Plant Paper-Grade Backtest Appendix"
author: "Aris Dressino"
date: "2026-06-22"
---

# InventOR 2-Plant Paper-Grade Backtest Appendix

## Scope

- Dataset: `20260619_400_Mat_2_plants.csv`
- Train cutoff: `2026-03-10`
- Validation end: `2026-06-19`
- Eligible cohort: `98` plant-material pairs
- Route source: train-window route labels with policy parameters regenerated from raw data under the current reproducible simulator.
- Default CLI mode `paper-backtest` runs the current simulator; `paper-backtest --mode replay` summarizes the refreshed artifact in `results/aggregate_backtest.json`.

## Aggregate Results

| Policy | n | Mean FR % | Agg FR % | >=95% % | Zero SO % | Mean HC | Mean TC | Mean Stockout Days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| InventOR | 98 | 96.7958 | 66.9563 | 91.8367 | 87.7551 | 8763.7771 | 9759.1853 | 3.4592 |
| Universal (r,Q) | 98 | 96.8658 | 66.9763 | 91.8367 | 89.7959 | 8664.2292 | 9674.4333 | 3.3061 |
| Universal (s,S) | 98 | 99.7743 | 99.9971 | 98.9796 | 96.9388 | 23579.1452 | 24396.7473 | 0.1224 |
| SAP Legacy | 98 | 92.8885 | 64.1735 | 84.6939 | 82.6531 | 4420.8520 | 5323.1479 | 4.7449 |
| k-sigma | 98 | 92.8250 | 59.3018 | 83.6735 | 66.3265 | 1905.4118 | 2817.4016 | 5.7041 |
| EOQ-only no SS | 98 | 89.7763 | 57.2218 | 70.4082 | 44.8980 | 1180.4514 | 2012.3391 | 8.0306 |

## Pairwise Comparison Versus InventOR

| Baseline | Eligible Items | FR Wins | FR Losses | FR Ties | Cost Better Count | Mean FR Delta | Mean TC Delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| Universal (r,Q) | 98 | 2 | 0 | 96 | 2 | 0.0700 | -84.7519 |
| Universal (s,S) | 98 | 12 | 0 | 86 | 29 | 2.9786 | 14637.5620 |
| SAP Legacy | 98 | 2 | 17 | 79 | 85 | -3.9073 | -4436.0373 |
| EOQ-only no SS | 98 | 0 | 52 | 46 | 94 | -7.0194 | -7746.8461 |
| k-sigma | 98 | 2 | 32 | 64 | 94 | -3.9708 | -6941.7836 |

Interpretation:

- Routed InventOR is statistically indistinguishable from universal `(r,Q)`: 2 wins, 0 losses, 96 ties, mean fill delta 0.07 pp, mean cost delta -84.75. Routing is therefore not the contribution.
- InventOR improves service relative to SAP (17 wins, 2 losses), but SAP remains much cheaper on mean total cost.
- Universal `(s,S)` is the service-maximizing comparator and the most expensive major policy.
- EOQ-only and `k-sigma` are cheapest, but accept materially weaker service.

## Route Diagnostics

| Branch | n | Mean FR % | Mean TC | Mean Stockout Days |
|---|---:|---:|---:|---:|
| (r,Q) | 87 | 96.4695 | 10174.4025 | 3.7241 |
| (s,S) | 7 | 100.0000 | 9805.5309 | 0.0000 |
| EOQ | 4 | 98.2846 | 647.1063 | 3.7500 |

Interpretation:

- `(r,Q)` is the dominant default branch on this cohort and now absorbs the 24 items formerly routed to the negative-binomial branch.
- `(s,S)` achieves perfect service on a small subset but at high cost.
- The `NB branch` was retired after a controlled ablation: on the same 24 items its negative-binomial reorder point delivered only 86.18% fill versus 94.18% for the `(r,Q)` normal-approximation reorder point (0 wins, 10 losses, 14 ties), i.e. it under-provisioned rather than dominating. Those items were consolidated into `(r,Q)`.
- `EOQ` appears only on a very small subset.

## Targeted And Cost-Aware Intervention

| Strategy | Selected | Mean FR % | Mean TC | SO-day Reduction | SAP Choices | InventOR Choices | Universal (r,Q) Choices |
|---|---:|---:|---:|---:|---:|---:|---:|
| SAP only | 0 | 92.8885 | 5323.1479 | 0 | 98 | 0 | 0 |
| InventOR for all | 98 | 96.7958 | 9759.1853 | 126 | 0 | 98 | 0 |
| Deterministic `OPTIMIZE_NOW` | 35 | 96.3334 | 8923.2826 | 130 | 63 | 35 | 0 |
| Ensemble LLM `OPTIMIZE_NOW` | 33 | 96.2242 | 7504.8675 | 117 | 65 | 33 | 0 |
| Governed cost-aware service floor | 19 | 96.0674 | 5329.6521 | 99 | 79 | 18 | 1 |

Interpretation:

- Direct selective optimization improves service but still carries a material cost premium.
- The governed cost-aware service-floor strategy applies only to LLM-reviewed `OPTIMIZE_NOW` and `LLM_REVIEW` rows.
- The strategy keeps SAP when no candidate meets the per-material SAP fill rate, and otherwise chooses among SAP, InventOR, and universal `(r,Q)` by service-cost score.

## Temporal Holdout Robustness Check

- Design: train policy parameters on pre-cutoff data, select on the first post-cutoff segment, evaluate on a held-out second segment.
- Midpoint split (`2026-04-30`): all-eligible held-out fill gain vs SAP `+2.8610` percentage points, held-out stockout-day reduction `+0.9286`, mean cost delta `-2.9318`.
- Selected-only (`17` non-SAP choices): held-out fill gain `+16.4927`, held-out stockout-day reduction `+5.3529`, mean cost delta `-16.9007`.
- Multi-split robustness sweep over five split dates (`2026-04-09`, `2026-04-19`, `2026-04-29`, `2026-05-10`, `2026-05-20`) shows:
  - all-eligible mean fill gain positive in `5/5` splits, range `+2.1497` to `+2.8790`
  - all-eligible mean stockout reduction positive in `5/5` splits, range `+0.5918` to `+1.2143`
  - all-eligible mean cost delta near parity, range `-33.6946` to `+1.6947`

Interpretation:

- This robustness check supports the governed selector more strongly than the original single in-sample reading.
- It is still retrospective evidence on one cohort, so it should be treated as a robustness check rather than as definitive prospective validation.

## Generalization: Site Holdout And Rolling Origins

Two checks probe whether the governed gain transfers across sites and time (no refitting).

Leave-one-plant-out replication (governed rule applied independently per plant):

| Plant | n | Governed selected | SAP fill % | Governed fill gain (pp) | Cost delta vs SAP | Stockout-days cut |
|-------|---|-------------------|------------|-------------------------|-------------------|-------------------|
| A (PLANT_A) | 73 | 12 | 97.03 | +1.66 | -23.44 | 17 |
| B (PLANT_B) | 25 | 7 | 80.79 | +7.62 | +93.94 | 82 |

- The gain replicates independently in both a high-service and a low-service plant; it is not a pooling artifact.

Rolling-origin (walk-forward), quantitative service-floor form of the rule, ~100-day windows:

| Cutoff | Test end | n eligible | Governed selected | Fill gain (pp) | Cost delta vs SAP | Informative |
|--------|----------|-----------|-------------------|----------------|-------------------|-------------|
| 2025-10-01 | 2026-01-09 | 7 | 0 | 0.00 | 0.00 | no |
| 2025-11-15 | 2026-02-23 | 8 | 0 | 0.00 | 0.00 | no |
| 2026-01-01 | 2026-04-11 | 75 | 12 | +0.36 | -73.24 | yes |
| 2026-02-15 | 2026-05-26 | 93 | 20 | +1.30 | -102.67 | yes |
| 2026-03-10 | 2026-06-18 | 98 | 21 | +3.18 | +4.18 | yes |

Interpretation:

- All three informative origins reproduce the property: positive service gain at cost parity or cheaper.
- The two earliest origins are non-informative (7-8 eligible items) due to the data-coverage funnel, not a failure of the rule.
- Effect direction is stable; effect magnitude grows with the window and eligible population and is not constant.
- Eligibility funnel at the reported cutoff: 98 of 301 plant-material pairs qualify; of the 203 excluded, only 27 are intrinsically intermittent (out of scope for continuous-review control), the rest fail the fixed coverage window at that origin.

## Synthetic Panel Replication

The governed selective-intervention mechanism was replicated on a fully disclosed, seeded synthetic panel (seed 20260619, stdlib-only, no private data). Three plants × 40 materials = 120 plant-material pairs across four demand regimes, with a deliberately variance-blind ERP baseline (safety_stock = 0.5 × mean daily demand, no safety lead time) that creates realistic service gaps on high-variability items.

| Regime | n | Governed selected | SAP fill (%) | Fill gain (pp) | Cost delta vs SAP |
|---|---|---|---|---|---|
| Smooth | 46 | 0 | 99.82 | 0.00 | 0 |
| Erratic | 35 | 4 | 95.64 | +0.66 | +43.3 |
| Lumpy | 30 | 2 | 89.29 | +0.67 | +33.0 |
| Intermittent | 9 | 4 | 81.94 | +11.03 | +669.8 |
| **All** | **120** | **10 (8.3%)** | **94.63** | **+1.19** | **+71.1** |

Interpretation: the governed layer leaves the already-adequate smooth items entirely untouched (0/46) and concentrates intervention where the variance-blind baseline under-provisions. The effect is monotone in the size of the underlying service gap. This confirms the selectivity mechanism on fully open data.

## Cost-Model Sensitivity

The reported result was re-run over a 5×5 grid jointly rescaling the per-item holding-cost rate and fixed ordering cost by factors {0.5, 0.75, 1.0, 1.5, 2.0} (25 combinations), with policies, EOQ order quantities, and simulated costs all recomputed consistently at each grid point.

| Metric | Min (over grid) | Max (over grid) |
|---|---|---|
| Governed selected | 18 | 22 |
| Mean fill gain vs SAP (pp) | +1.37 | +3.18 |
| Mean cost delta vs SAP | −171.9 | +70.6 |
| Cost delta as % of SAP cost | −1.61% | +1.22% |

The service gain is strictly positive across all 25 grid points. The cost delta stays within a ±1.6% band of the SAP baseline cost — a small saving-to-slight-premium range. The governed selective-intervention conclusion does not hinge on the estimated cost parameters.

## Artifact Paths

- JSON source: `results/aggregate_backtest.json`
- Target ranking CSV: `sample_artifacts/target_ranking.csv`
- Value table CSV: `sample_artifacts/optimized_material_value_vs_sap.csv`
- Material flags CSV: `sample_artifacts/material_flags.csv`
- Material flags JSONL: `sample_artifacts/material_flags.jsonl`
- Ensemble-reviewed flags CSV: `sample_artifacts/reviewed_flags.csv`
- Ensemble-reviewed flags JSONL: `sample_artifacts/reviewed_flags.jsonl`
- Targeted evaluation JSON: `sample_artifacts/targeted_evaluation.json`
- OOS robustness summary CSV: `results/out_of_sample_validation.csv`
- OOS robustness summary JSON: `results/out_of_sample_validation.json`
- Plant holdout CSV/JSON: `results/plant_holdout.csv`, `results/plant_holdout.json`
- Rolling-origin CSV/JSON: `results/rolling_origin.csv`, `results/rolling_origin.json`
- Synthetic panel CSV: `inventor_tests/data/synthetic_panel.csv`
- Synthetic replication CSV/JSON: `results/synthetic_replication.csv`, `results/synthetic_replication.json`
- Cost-model sensitivity CSV/JSON: `results/cost_model_sensitivity.csv`, `results/cost_model_sensitivity.json`
