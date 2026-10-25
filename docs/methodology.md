# Methodology

## Scientific and disclosure HOLD — 25 October 2026

**Major Revision.** All industrial results below are conditional on the frozen
processed recorded series, not validated industrial demand/service performance.
Source grain/additivity, demand semantics, privacy and publication/release rights
are separate unresolved gates; software verification does not close them.

The 233,078 rows form 220,017 pair-date groups. A public-panel diagnostic finds
12,036 repeated groups across 62/411 full-panel pairs, repeating daily quantities
while context varies. The frozen loader sums signed demand, receipts, scrap and
corrections; demand becomes the absolute daily net. Stock is not summed; other
attributes use the last row, and positive lead times are averaged. Additivity,
sign handling, context selection and stock snapshot timing lack source validation.
No deduplication is authorized. Diagnostic one-measure totals are not corrected
demand; affected overlap with 365/346/338 cohorts and ranking impacts are unknown.

Whether the series represents availability-independent requests or fulfilled
issues is unverified. Simulated fill/shortage denominators condition on that
series; no latent-demand or historical lost-sales reconstruction occurred.
Obtain an authorized source dictionary, extract lineage/keys and private grain
reconciliation before scientific clearance. Permission does not validate grain;
valid grain does not grant publication rights.

The masked panel is pseudonymized, not demonstrated anonymous. Quantity factors
and reciprocal unit-price factors preserve economic products before rounding;
dates, lead times, calendars, normalized patterns and stable identifiers retain
linkage exposure. Existing data/narratives remain unchanged, not newly cleared.

## Question

Can a pretrained general-purpose LLM, without project-specific training or fine-tuning, propose material-level replenishment parameters competitive with ERP-derived and operations-research policies in simplified held-out replay? Static admission and trajectory/order-level compliance are separate questions.

## Arms

| Arm | Role |
|---|---|
| SAP-derived | Recomputed reorder point using ERP safety stock and safety lead time, with EOQ quantity |
| SLT-informed OR | Deterministic `(r,Q)` policy that adds the ERP safety lead time to the mean lead time |
| ERP-floor OR | SLT-informed OR with the ERP safety stock as a floor (same ERP inputs as the LLM) |
| History-only OR | Deterministic `(r,Q)` policy computed from demand and lead-time history only, no ERP planning inputs |
| Croston/SBA OR | History-only `(r,Q)` with the Syntetos-Boylan-corrected Croston demand rate (alpha 0.1) and forecast-error spread |
| Empirical-quantile OR | History-only `(r,Q)` with the reorder point set to the service-level quantile of historical rolling lead-time demand |
| Simulation-tuned (r,Q) | Grid search over reserve factor and order-quantity multiples on the last 250 pre-cutoff working days; no post-cutoff data |
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
| Croston/SBA OR | 2,705 | 98.30 | 803 |
| Empirical-quantile OR | 2,489 | 98.35 | 747 |
| Simulation-tuned (r,Q) | 3,266 | 96.05 | 1,973 |
| LLM run 1 / 2 / 3 | 2,928 / 2,931 / 2,929 | 98.11 / 97.89 / 98.16 | 910 / 968 / 890 |
| LLM without ERP | 3,014 | 98.06 | 890 |

The LLM is about 11% cheaper than the SAP-derived arm and about 30% cheaper than the SLT-informed and ERP-floor OR arms, about 6% more expensive than the history-only OR, about 8% more than Croston/SBA and about 18% more than the empirical-quantile OR (the simulation-tuned arm is a different operating point: lower fill, much lower cost once shortages are priced); without ERP planning inputs it is 8.8% cheaper than SAP-derived and 9.0% more expensive than the history-only OR. The saving comes from about 17% lower average inventory at about 13% more stockout days. With shortages priced at one unit cost or more, the simulation-tuned arm is cheapest and SAP-derived is cheapest among the others (the LLM is about 2.4% more expensive than SAP-derived). At Plant C the LLM is 31-36% more expensive than SAP-derived across all three runs and all calendar variants.

Storage limits: in the unconstrained replay the peak on-hand stock exceeds the limit for 178-183 of 346 pairs (LLM, 9-10% of days), 198 (SAP-derived) and 230 (SLT-informed OR). The static check `safety_stock + order_quantity <= max_storage_units` therefore does not guarantee trajectory compliance, which is why the hard-limit replay is primary.

## Repeated runs

Three masked generations (run-m1..m3, 364/365/365 policies produced; 340/342/342 scorable) preserve the main ranking. Ratios near one compare matched masked costs with rescaled frozen originals, not unscaled original means. `outputs/six_run_evidence.json` restricts all six runs and seven comparators to 338 shared pairs; the six generations reuse one underlying dataset. Hash amendments retain original values and amendment histories rather than asserting amended hashes were execution-time provenance.

Three full runs with the same prompt file give nearly identical aggregate results (cost spread below one percentage point). Exact policy equality between runs 2 and 3 holds for only 36 of 365 pairs; median absolute differences are 81 units for reorder point, 6 for order quantity and 3 for safety stock. None of these results establishes prospective operating performance.

## Implementation qualifications

- Arrivals precede demand; at most one order follows demand on each working day. Lead time is a rounded, deterministic working-observation offset, not stochastic realized lead time.
- Shared observed opening inventory and an empty pipeline initialize evaluation; observed receipts, scrap and corrections are ignored.
- Capacity clipping uses `min(Q, capacity - floor(position))` and can release less than MOQ. Static policy feasibility does not establish simultaneous order-level feasibility.
- SLT-informed and ERP-floor arms use effective lead time in both mean demand and lead-time-demand variance.
- The tuned arm tests up to 85 candidates on the last 250 pre-cutoff working days, without capacity clipping, initializing each at its own R+Q. Statistics use all pre-cutoff observations; this is in-sample tuning, not nested validation.
- Positive shortage prices revalue fixed trajectories, not re-optimize policies. Mean material fill and volume-weighted fill differ substantially; comparisons are not at equal service.
- The 10.5% original cost-variation measure is mean within-pair range divided by pair mean, not SD. Policy ratios use +1 smoothing and cannot reveal internal LLM calculations.
- Primary paired percentile-bootstrap intervals use 5,000 resamples, seed 20261006; three plants and within-plant dependence preclude broad population inference.
- Orders are mean counts per material over its observed evaluation horizon, not annualized rates. Frozen table values are unchanged.
