# Methodology

## Question

Can a general-purpose LLM, without training or fine-tuning, receive one material trace and produce replenishment parameters that are admissible, storage-feasible and competitive with ERP-derived and operations-research policies when replayed on held-out data?

## Arms

| Arm | Role |
|---|---|
| SAP-derived | Recomputed reorder point and quantity with the ERP safety stock |
| SLT-informed OR | Deterministic `(r,Q)` policy that adds the ERP safety lead time to the mean lead time |
| ERP-floor OR | SLT-informed OR with the ERP safety stock as a floor (same ERP inputs as the LLM) |
| History-only OR | Deterministic `(r,Q)` policy computed from demand and lead-time history only, no ERP planning inputs |
| LLM (runs 1-3) | Validated LLM artifact; every artifact resolved to `(r,Q)` |
| LLM without ERP | Ablation: the two ERP planning fields (safety stock, safety lead time) are blanked and marked `not_supplied` |

## Workflow

1. Load the confidential operational CSV extract.
2. Repair all 39,451 all-zero Plant C calendar rows from Plant A/B same-date votes; ties count as working days.
3. Select eligible plant-materials (at least 20 pre-cutoff and 40 validation working days).
4. Send one material at a time to the enterprise LLM platform with prompt variables and a material-scoped CSV. The system prompt is `prompts/system_prompt.txt`.
5. Extract `inventory_optimization_output.json`.
6. Gate: reject and retry malformed artifacts, non-positive reorder point or order quantity, negative safety stock, reorder point below safety stock, and safety stock plus order quantity above the storage limit. The backtest additionally requires the order quantity to be at least the MOQ.
7. Project each deterministic comparator to the same MOQ and storage rule; exclude pairs where comparator safety stock plus MOQ cannot fit.
8. Replay every arm on the same post-cutoff horizon from the shared observed opening inventory. Primary basis: hard-limit replay, in which orders are truncated to storage limit minus inventory position; the unconstrained replay is reported only for the capacity-trajectory check.
9. Report failures and outliers without imputation.

## Eligibility

411 plant-material pairs; 365 eligible (Plant A 234, Plant B 65, Plant C 66). 19 Plant A pairs are excluded because a comparator safety stock plus MOQ exceeds the storage limit, leaving a common-feasible cohort of 346 pairs.

## Primary results (hard-limit replay, 346 pairs, zero shortage penalty)

| Arm | Mean cost | Mean fill (%) | Stockout days |
|---|---:|---:|---:|
| SAP-derived | 3,305 | 98.30 | 804 |
| SLT-informed OR | 4,211 | 98.23 | 831 |
| ERP-floor OR | 4,248 | 98.23 | 831 |
| History-only OR | 2,764 | 98.14 | 874 |
| LLM run 1 / 2 / 3 | 2,928 / 2,931 / 2,929 | 98.11 / 97.89 / 98.16 | 910 / 968 / 890 |
| LLM without ERP | 3,014 | 98.06 | 890 |

The LLM is about 11% cheaper than the SAP-derived arm and about 30% cheaper than the SLT-informed and ERP-floor OR arms, and about 6% more expensive than the history-only OR; without ERP planning inputs it is 8.8% cheaper than SAP-derived and 9.0% more expensive than the history-only OR. The saving comes from about 17% lower average inventory at about 13% more stockout days. With shortages priced at one unit cost or more, the SAP-derived arm is cheapest (the LLM is about 2.4% more expensive). At Plant C the LLM is 31-36% more expensive than SAP-derived across all three runs and all calendar variants.

Storage limits: in the unconstrained replay the peak on-hand stock exceeds the limit for 178-183 of 346 pairs (LLM, 9-10% of days), 198 (SAP-derived) and 230 (SLT-informed OR). The static check `safety_stock + order_quantity <= max_storage_units` therefore does not guarantee trajectory compliance, which is why the hard-limit replay is primary.

## Repeated runs

Three full runs with the same prompt file give nearly identical aggregate results (cost spread below one percentage point). Exact policy equality between runs 2 and 3 holds for only 36 of 365 pairs; median absolute differences are 81 units for reorder point, 6 for order quantity and 3 for safety stock. None of these results establishes prospective operating performance.
