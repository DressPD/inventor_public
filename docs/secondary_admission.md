# Supplementary File S2: secondary strict-admission validation

Protocol: 29 October 2026. This is a separately identified offline intervention,
not a replacement for the original experiment or the archived software/paper.
No new inference, training, policy tuning or independent industrial dataset is used.

## Reproduction

Use Python 3.14.9 and the supplied masked panel and frozen policies. Only stdlib
is required. From the support/repository root, choose an absent destination:

```sh
python3 -B -S scripts/build_secondary_admission.py --dest /absolute/absent/scratch
python3 -B -S -m unittest discover -s tests -p test_secondary_admission.py -v
```

In the private repository, use an absent external scratch directory or an absent
directory under `outputs/secondary_admission/`. In the anonymous support ZIP,
use an external scratch directory. The runner refuses existing destinations,
symlink paths and writes into protected project paths. Input hashes are recorded
and rechecked; no frozen output is written. Two runs must produce identical
`evidence.json` and `report.md`. Source integrity is checked by the enclosing
public manifest or reviewer-support `SUPPORT_MANIFEST.json`.
When the reviewer-support manifest is present, replay and the extracted-support
test require its complete inventory and every digest before reading replay inputs.
The private packager also matches every bundled panel/policy/baseline input byte
against the evidence's complete `input_sha256` map, rejecting stale/missing provenance.

The runner checks every legacy simulator field against `core.simulate` under
frozen clipping, then checks the complete frozen six-run summary (relative
tolerance 1e-10, absolute 1e-7). It aborts before publishing on mismatch or
nonfinite input. It uses the same all-arm/six-run intersection of 338 pairs,
shared observed opening stock, empty pipeline, pre-cutoff statistics, fixed
policy constructors, processed demand and deterministic working-observation
lead-time arrivals. Comparator reconstruction uses the historical algorithm,
not new held-out tuning. Run exclusions and non-common pairs are explicit.

The intervention reuses `inventory_llm/robustness.py`: replace
`capacity - int(position)` with `floor(capacity - position)` and defer releases
below MOQ. Order dates/quantities can therefore change; parameters do not.
Zero capacity means unspecified capacity, not a zero-stock bound. Costs p0/p1/p5
revalue each resulting trajectory; they are not retuned or equal-service results.
Results include per-pair metrics and pooled/plant summaries, mean and volume
fill, costs, deferrals, sub-MOQ releases, initial excess and capacity days.
Physical post-order peak position is comparable across modes; the legacy
`peak_inventory_position` field is not (clipping omits post-order updates).

## Conditional admission invariant

Assume a single item with known integer capacity C > 0, integer MOQ m >= 1,
finite nonnegative on-hand stock I and outstanding quantities P, and initial
inventory position x = I + sum(P) <= C. Each receipt transfers a pending
quantity to on hand exactly once; it creates no stock. Nonnegative lost-sales
demand only reduces on hand. No other stock corrections, scrap, external
receipts, reservations or capacity changes occur. Leads are positive and the
simulator releases at most one order per observation. Arithmetic in this
argument is exact; floating implementation checks use 1e-9 tolerance.

At admission let a be the proposed nonnegative integer quantity (fixed Q or
the integer order-up-to gap). Set q = min(a, max(0, floor(C - x))). Release q
only if q >= m. A deferral leaves x unchanged. A release gives x' = x + q <= C
and q >= m. Receipts preserve position; demand reduces it. Induction therefore
bounds on hand and total position by C, and every positive release meets MOQ.
This proves only these simulator properties under these assumptions. Neither
the reorder point nor the static safety-stock-plus-Q test alone proves them.

Initial stock above C violates the induction base. It is retained in descriptive
results, reported and excluded from invariant checks, not silently clipped.
Unspecified capacity is also excluded. Exogenous receipts, changed capacity,
negative demand interpreted as returns or incorrect pipeline accounting can
invalidate the proof. No guarantee concerns fill, service, cost or optimality.

## Independent finite checks and counterexamples

Receipt peaks and over-capacity observations are checked explicitly, not inferred
only from post-demand inventory position. Sixty-four additional independent
order-up-to cases span nonworking calendar gaps, fractional opening stock, MOQ,
capacities and lead offsets, carrying pending receipts across working observations.
These extend the original finite grid without changing the simulator or policies.

`tests/test_secondary_admission.py` independently constructs a rational-arithmetic
oracle: enumerate admissible integer quantities rather than duplicate the
simulator's headroom formula. It checks 1,728 three-observation trajectories
over capacities 2/3, MOQ 1/2, opening 0/1.5, triggers 0/2, quantities 1/3,
leads 1/2 and demand 0/0.5/2. It compares orders, shortages, average stock,
deferrals and physical peak position, including pending orders. Finite tests
exercise implementation behavior; they do not prove an infinite-state theorem.

Counterexample: C=3, x=2.5, Q=2, m=2 and a triggered order. Frozen clipping
releases one unit, below MOQ, and position becomes 3.5. Strict admission defers.
If m>C and demand continues, no order can be admitted and fill can be zero.
If opening stock is 4 with C=3, the initial breach remains. Capacity=0 has no
capacity guarantee. These adverse cases prevent a universal safety claim.

## Interpretation and access boundaries

The report additionally derives per-arm/group paired fill-deterioration counts,
worst fill losses and cost-increase counts at penalties 0/1/5 from existing metrics.
It shows both mode means and mean paired cost deltas, including positive shortage
prices. Mean pair cost averages item-horizon costs; capacity days sum over-capacity
pre-demand receipt observations over item-working-days, not distinct calendar dates. MOQ
deferrals count repeated triggered observations, not unique blocked orders.
These are reporting additions only; all secondary numerical outcomes remain fixed.

On these 338 pairs no opening-excess or unspecified-capacity exclusions occur;
the initial-feasibility exceptions are still tested independently. Strict mode
has no sub-MOQ orders or over-capacity days in any arm. For M1, clipping versus
strict mean cost is 2897.57 versus 2895.06, mean fill 98.326% versus 98.323%, and
volume fill 76.337% versus 76.331%; strict admission causes 48 MOQ deferrals.
Plant C M1 cost remains higher than ERP-derived (2598.83 versus 1844.94).
An adverse cost example is Plant A empirical-quantile: 1962.87 rises to 1963.25.
These masked-unit descriptive observations show no Pareto or service guarantee.

Read `outputs/secondary_admission/report.md` for both modes, all arms and plants;
`evidence.json` retains detailed results and exclusions. Do not pool six LLM
policies as six independent datasets or substitute this intervention for the
346-pair original results. Deferrals may improve one metric while worsening
another. The recorded series, additive grain, request-versus-issue meaning,
latent demand and deployment assumptions remain unvalidated. Pseudonymization
does not establish anonymity, privacy or release rights. Synthetic checks and
this conditional argument establish neither human benefits nor acceptance.

Local working support differs from archived preprint v3 and software v1.3.0;
archives, tags and identifiers remain unchanged. The reviewer support supplies
masked data/policies, code, tests, methods and results without identifying links.
It supports numerical replay, not reconstruction of historical proprietary LLM
inference. Other local robustness scenarios are outside this support.
