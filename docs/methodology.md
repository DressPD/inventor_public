# Methodology

## Question

Can a general-purpose LLM, without training or fine-tuning, receive one material trace and produce replenishment parameters that backtest well?

## Arms

| Arm | Role |
|---|---|
| SAP-derived | Recomputed reorder point and quantity with source safety stock |
| SAP-SLT-informed OR | Deterministic `(r,Q)` comparator retaining source SAP safety lead time |
| LLM-emitted | Validated LLM artifact; every scoreable artifact in this study resolved to `(r,Q)` |

## Workflow

1. Load the confidential operational CSV extract.
2. Repair all 39,451 all-zero Plant C calendar rows from Plant A/B same-date votes; ties count as working days.
3. Select eligible plant-materials using the working-day rule.
4. Send one material at a time to the enterprise LLM platform with prompt variables and a material-scoped CSV.
5. Extract `inventory_optimization_output.json`.
6. Convert valid LLM policy values to `(r,Q)` or `(s,S)` simulator policies; reject and retry malformed, inconsistent, MOQ-, or storage-violating artifacts. In this study all 365 scoreable artifacts resolved to `(r,Q)`, so the order-up-to branch is supported but unexercised.
7. Project each deterministic comparator to the same MOQ and per-material storage rule; exclude pairs where comparator safety stock plus MOQ cannot fit.
8. Simulate LLM-emitted, SAP-derived, and SAP-SLT-informed OR on the same post-cutoff horizon and shared observed opening inventory.
9. Report failures, malformed outputs, and outliers without imputation.

## Active Eligibility

The active data contain 411 plant-material pairs. Plant C has rows for the full date range but an all-zero `is_working_day` field, so its working-day calendar is derived from same-date calendars in Plants A and B. With at least 20 pre-cutoff working days and 40 validation working days, 365 materials are eligible: 234 from Plant A, 65 from Plant B, and 66 from Plant C.

## Final Run State

All 365 eligible pairs have scoreable, LLM-capacity-feasible artifacts after retry handling. The equal-feasibility comparison covers 346 pairs: 19 pairs are excluded because a comparator safety stock plus MOQ cannot fit its supplied storage limit. All included arms satisfy `MOQ <= order_quantity` and `safety_stock + order_quantity <= max_storage_units` when supplied. LLM-emitted reaches 77.52% aggregate fill at 2,848.04 mean simulated holding/order cost, compared with SAP-derived at 79.99% and 3,184.20, and SAP-SLT-informed OR at 79.58% and 3,852.22. Stockout-day totals are 936, 741, and 799, respectively. The top five materials represent 40.34% of demand; excluding them raises aggregate fill to 91.82%, 95.80%, and 95.11%, respectively.

Every arm starts with observed on-hand inventory and an empty on-order pipeline. Observed receipts, corrections, and scrap are excluded after cutoff. Primary results use rounded source lead time as a working-day offset; calendar-day offsets give aggregate fill of 77.77%, 80.25%, and 79.84%, respectively. Excluding the plant with an imputed working-day calendar leaves 280 native-calendar pairs with aggregate fill of 74.03%, 76.55%, and 76.35%, and mean holding/order cost of 2,893.39, 3,471.66, and 4,168.76. The primary holding/order cost uses zero shortage penalty; one-times-unit-cost lost-sales penalties yield mean total costs of 1,688,921.83, 1,631,321.28, and 1,692,746.91, respectively. The storage limit is per material, not shared capacity. The 365-artifact audit finds 42 diagnostic outliers and 91.51% normalized family agreement. These choices and the SAP safety-lead-time input prevent causal or independent-comparator claims.

## Three-Run Evidence

The three-run common material cohort contains 365 plant-material artifact identifiers with parseable policy triples in Runs 1, 2, and 3. All three-run distributions and provenance counts use only this cohort. Runs 2 and 3 retain 359 artifacts with complete matching provenance contracts and exclude six with incomplete provenance. Only 38 of 359 policy triples are numerically identical; median absolute differences are 122 units for reorder point, 5 for order quantity, and 4 for safety stock. On the 338-pair outcome-common cohort, LLM aggregate fill is 79.05% in Run 2 and 79.09% in Run 3. Runs 2 and 3 demonstrate repeated completion under the instrumented runner; Run 1 predates provenance instrumentation and none of the three runs establishes prospective operating performance.
