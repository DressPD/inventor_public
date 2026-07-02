# Academic Validation Pack

## Scope
This pack summarizes retrospective validation on the current reproducible InventOR artifacts regenerated from raw data.

## Statistical Evidence
- `fill_gain_vs_sap_pct_pts`: mean 3.9073 with 95% bootstrap CI [1.7691, 6.3698], sign-test p=0.000729, direction=positive.
- `stockout_days_reduction_vs_sap`: mean 1.2857 with 95% bootstrap CI [0.3367, 2.4796], sign-test p=0.001312, direction=positive.
- `shortage_reduction_vs_sap`: mean 9134.4388 with 95% bootstrap CI [1995.7594, 18406.2528], sign-test p=0.000729, direction=positive.
- `cost_delta_vs_sap`: mean 4436.0373 with 95% bootstrap CI [1952.5888, 8018.3597], sign-test p=0.0, direction=negative.

## External Benchmark Evidence
InventOR is compared against SAP static, universal `(r,Q)`, universal `(s,S)`, EOQ, and k-sigma policies in `results/external_benchmark.csv`.

## Ablation Evidence
Best service-gain ablation: `universal_rq_all` with mean fill gain 3.9773 percentage points.
Final governed policy selects 19 items (19.39%) with mean fill gain 3.1789 points and mean cost delta 6.5042.
Final governed fill gain descriptive interval: [1.2474, 5.4262]. Sign-test p=0.003906 is descriptive only because the governed selector enforces a per-item SAP service floor.
Final governed cost delta 95% CI: [-210.3839, 194.4189], sign-test p=1.0.

## LLM Governance Evidence
LLM/governance interventions: 63 items.
Direct optimizations rerouted or blocked: 35 items.
Supplier-contact cases: 51; planner-contact cases: 35.

## Academic Caveat
This is retrospective artifact-level validation, not final causal proof. Human planner validation and prospective holdout deployment remain required for production-grade claims.
