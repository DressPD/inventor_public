# Methodology

## Question

Can a general-purpose LLM, without training or fine-tuning, receive one material trace and produce replenishment parameters that backtest well?

## Arms

| Arm | Role |
|---|---|
| SAP-derived | Recomputed reorder point and quantity with source safety stock |
| SAP-SLT-informed OR | Deterministic `(r,Q)` comparator retaining source SAP safety lead time |
| LLM-emitted | LLM artifact converted into simulator policy |

## Workflow

1. Load the confidential operational CSV extract.
2. Repair all 39,451 all-zero Plant C calendar rows from Plant A/B same-date votes; ties count as working days.
3. Select eligible plant-materials using the working-day rule.
4. Send one material at a time to the enterprise LLM platform with prompt variables and a material-scoped CSV.
5. Extract `inventory_optimization_output.json`.
6. Convert valid LLM policy values to simulator policies; reject and retry artifacts violating MOQ or supplied storage capacity.
7. Project each deterministic comparator to the same MOQ and per-material storage rule; exclude pairs where comparator safety stock plus MOQ cannot fit.
8. Simulate LLM-emitted, SAP-derived, and SAP-SLT-informed OR on the same post-cutoff horizon and shared observed opening inventory.
9. Report failures, malformed outputs, and outliers without imputation.

## Active Eligibility

The active data contain 411 plant-material pairs. Plant C has rows for the full date range but an all-zero `is_working_day` field, so its working-day calendar is derived from same-date calendars in Plants A and B. With at least 20 pre-cutoff working days and 40 validation working days, 365 materials are eligible: 234 from Plant A, 65 from Plant B, and 66 from Plant C.

## Final Run State

All 365 eligible pairs have scoreable, LLM-capacity-feasible artifacts after retry handling. The equal-feasibility comparison covers 346 pairs: 19 pairs are excluded because a comparator safety stock plus MOQ cannot fit its supplied storage limit. All included arms satisfy `MOQ <= order_quantity` and `safety_stock + order_quantity <= max_storage_units` when supplied. LLM-emitted reaches 77.77% aggregate fill at 3,002.40 mean simulated cost, compared with SAP-derived at 80.25% and 3,346.87, and SAP-SLT-informed OR at 79.84% and 4,016.81. Stockout-day totals are 860, 699, and 754, respectively. The top five materials represent 40.34% of demand; excluding them raises aggregate fill to 91.92%, 95.91%, and 95.22%, respectively.

Every arm starts with observed on-hand inventory and an empty on-order pipeline. Observed receipts, corrections, and scrap are excluded after cutoff. Primary results use rounded source lead time as a calendar-day offset; working-day offsets give aggregate fill of 77.53%, 79.99%, and 79.58%, respectively. The storage limit is per material, not shared capacity. The 365-artifact audit finds 42 diagnostic outliers and 90.68% normalized family agreement. These choices and the SAP safety-lead-time input prevent causal or independent-comparator claims.
