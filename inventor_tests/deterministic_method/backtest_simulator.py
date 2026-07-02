from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median
from typing import Any

from inventor_tests._utils import safe_float as _f


ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT.parent / "results"
INTERNAL_DIR = ROOT.parent / "sample_artifacts"
DEFAULT_BACKTEST_JSON = RESULTS_DIR / "aggregate_backtest.json"
CSV_PATH = ROOT / "data" / "20260619_400_Mat_2_plants.csv"

DEFAULT_SHORTAGE_PENALTY_RATE = 0.35


def _parse_date(s: str) -> date:
    return date.fromisoformat(str(s).strip())


def load_grouped_rows(csv_path: str | Path) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            plant = row.get("plant_code", "").strip()
            material = row.get("material", "").strip()
            if not plant or not material:
                continue
            grouped[f"{plant}__{material}"].append(dict(row))
    for rows in grouped.values():
        rows.sort(key=lambda r: r.get("date", ""))
    return dict(grouped)


def load_cached_route_payloads(
    cache_dir: str | Path, train_cutoff: str
) -> dict[str, dict[str, Any]]:
    cache_path = Path(cache_dir)
    if not cache_path.exists():
        return {}
    suffix = train_cutoff.replace("-", "")
    payloads: dict[str, dict[str, Any]] = {}
    for path in cache_path.glob(f"*{suffix}.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        key = payload.get("item_key") or path.stem.split("__cutoff_")[0]
        payloads[key] = payload
    return payloads


# ── stats ─────────────────────────────────────────────────────────────────────

def _infer_sign_inverted(rows: list[dict[str, str]]) -> bool:
    vals = [_f(r.get("actual_demand")) for r in rows]
    return all(v <= 0 for v in vals) and any(v < 0 for v in vals)


def _demand(row: dict[str, str], inverted: bool) -> float:
    d = _f(row.get("actual_demand"))
    return max(0.0, -d if inverted else d)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mu = mean(values)
    return math.sqrt(sum((x - mu) ** 2 for x in values) / (len(values) - 1))


def _iqr_std(vals: list[float]) -> float:
    if len(vals) < 4:
        return _std(vals)
    s = sorted(vals)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[(3 * n) // 4]
    return (q3 - q1) / 1.35


def compute_item_stats(rows: list[dict[str, str]]) -> dict[str, Any]:
    inverted = _infer_sign_inverted(rows)
    demands = [_demand(r, inverted) for r in rows]
    wd = [d for r, d in zip(rows, demands) if _f(r.get("is_working_day"), 0) == 1]
    nonzero_wd = [d for d in wd if d > 0]
    lts = [_f(r.get("delivery_time")) for r in rows if _f(r.get("delivery_time")) > 0]

    mu_d = mean(demands) if demands else 0.0
    std_d = _std(demands)
    mu_lt = mean(lts) if lts else 1.0
    std_lt = _std(lts)
    robust_std = _iqr_std(wd) if wd else std_d

    unit_cost = _f(rows[-1].get("unit_cost"))
    hcr = _f(rows[-1].get("holding_cost_rate")) or 0.12
    ordering_cost = _f(rows[-1].get("ordering_cost")) or 75.0
    moq = max(1, int(_f(rows[-1].get("minimum_order_quantity"), 1.0) or 1))
    sap_ss = _f(rows[-1].get("safety_stock_units"))
    sap_slt = _f(rows[-1].get("safety_time_workdays_actual"))
    reliability = _f(rows[-1].get("reliability_calc"), 1.0) or 1.0
    return {
        "mean_daily_demand": mu_d, "std_daily_demand": std_d, "robust_std_daily": robust_std,
        "mean_lead_time": mu_lt, "std_lead_time": std_lt,
        "cv_lead_time": (std_lt / mu_lt if mu_lt > 0 else 0.0),
        "delivery_observations": len(lts),
        "non_zero_fraction_wd": (len(nonzero_wd) / len(wd) if wd else 0.0),
        "unit_cost": unit_cost, "holding_cost_rate": hcr,
        "annual_holding_cost_per_unit": unit_cost * hcr,
        "ordering_cost": ordering_cost, "moq": moq,
        "sap_safety_stock": sap_ss, "sap_slt": sap_slt,
        "reliability": reliability,
        "annual_demand": mu_d * 252.0,
        "effective_lead_time": mu_lt + max(sap_slt, 0.0),
        "order_quantity": moq,
        "service_level": _f(rows[-1].get("service_level_target") or rows[-1].get("service_level"), 0.95) or 0.95,
    }


# ── policy builders ───────────────────────────────────────────────────────────

def _z(sl: float) -> float:
    """Rational approximation of the normal quantile (Abramowitz & Stegun §26.2.17)."""
    sl = max(0.001, min(0.999, sl))
    if sl < 0.5:
        return -_z(1.0 - sl)
    t = math.sqrt(-2.0 * math.log(1.0 - sl))
    c = (2.515517, 0.802853, 0.010328)
    d = (1.432788, 0.189269, 0.001308)
    return t - (c[0] + c[1] * t + c[2] * t ** 2) / (1.0 + d[0] * t + d[1] * t ** 2 + d[2] * t ** 3)


def _make_rq_policy(stats: dict[str, Any], sl: float | None = None) -> dict[str, Any]:
    sl = sl or stats.get("service_level", 0.95)
    z = _z(sl)
    mu = stats["mean_daily_demand"]
    sigma = max(stats["robust_std_daily"], stats["std_daily_demand"])
    lt = max(stats["mean_lead_time"], 0.0)
    std_lt = stats["std_lead_time"]
    eff_lt = stats["effective_lead_time"]
    sigma_ltd = math.sqrt(max(lt * sigma ** 2 + mu ** 2 * std_lt ** 2, 0.0))
    ss = max(0.0, z * sigma_ltd)
    rop = math.ceil(mu * eff_lt + ss)
    annual_holding = max(stats["annual_holding_cost_per_unit"], 1e-6)
    annual_demand = max(stats["annual_demand"], 0.0)
    eoq_raw = math.sqrt(2 * stats["ordering_cost"] * annual_demand / annual_holding) if annual_demand > 0 else stats["moq"]
    oq = max(stats["moq"], int(math.ceil(eoq_raw)))
    return {"policy": "(r,Q)", "rop": rop, "oq": oq, "ss": int(round(ss)), "out_to": None}


def _make_ss_policy(stats: dict[str, Any], sl: float | None = None) -> dict[str, Any]:
    base = _make_rq_policy(stats, sl)
    s = base["rop"]
    S = s + base["oq"]
    return {"policy": "(s,S)", "rop": s, "oq": base["oq"], "ss": base["ss"], "out_to": S}


def _make_sap_policy(stats: dict[str, Any]) -> dict[str, Any]:
    sap_ss = max(0.0, stats["sap_safety_stock"])
    mu = stats["mean_daily_demand"]
    eff_lt = stats["effective_lead_time"]
    rop = math.ceil(mu * eff_lt + sap_ss)
    return {"policy": "sap_static", "rop": rop, "oq": stats["moq"], "ss": int(sap_ss), "out_to": None}


def _make_eoq_policy(stats: dict[str, Any]) -> dict[str, Any]:
    mu = stats["mean_daily_demand"]
    lt = max(stats["mean_lead_time"], 0.0)
    rop = math.ceil(mu * lt)
    return {"policy": "eoq_pure", "rop": rop, "oq": stats["moq"], "ss": 0, "out_to": None}


def _make_k_sigma_policy(stats: dict[str, Any], k: float = 1.65) -> dict[str, Any]:
    sigma = stats["std_daily_demand"]
    lt = max(stats["mean_lead_time"], 0.0)
    mu = stats["mean_daily_demand"]
    ss = max(0.0, k * sigma * math.sqrt(lt) if lt > 0 else 0.0)
    rop = math.ceil(mu * lt + ss)
    return {"policy": "k_sigma", "rop": rop, "oq": stats["moq"], "ss": int(round(ss)), "out_to": None}


def _policy_from_cache(payload: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    """Extract policy parameters from a cached route payload."""
    route = (payload.get("route_used") or payload.get("model_selected") or "").lower()
    conf = (payload.get("model_confidence") or payload.get("confidence") or "").upper()
    sl = payload.get("service_level") or stats.get("service_level", 0.95)
    # If LLM recommended (s,S) or negbin via route, honour it; otherwise RQ
    if route in {"(s,s)", "ss", "s,s", "order_up_to"}:
        pol = _make_ss_policy(stats, sl)
    elif route in {"negbin", "nb branch", "nb", "negative binomial"}:
        # Use (r,Q) as safe stand-in when scipy not available in this context
        pol = _make_rq_policy(stats, sl)
        pol["policy"] = "NB branch"
    elif conf == "UNCERTAIN":
        pol = _make_rq_policy(stats, sl)
    else:
        pol = _make_rq_policy(stats, sl)
        pol["policy"] = route or "(r,Q)"
    # Override with explicit numeric params if provided
    for src_key, dst_key in [
        ("recommended_reorder_point", "rop"),
        ("recommended_safety_stock", "ss"),
        ("recommended_order_quantity", "oq"),
        ("order_up_to", "out_to"),
    ]:
        v = payload.get(src_key)
        if v is not None:
            try:
                pol[dst_key] = int(round(float(v)))
            except (TypeError, ValueError):
                pass
    return pol


# ── targets CSV policy source ─────────────────────────────────────────────────

def load_targets_policies(targets_csv: Path) -> dict[str, dict[str, Any]]:
    """Read per-item recommended policy from an existing targets CSV (paper-grade source)."""
    if not targets_csv.exists():
        return {}
    policies: dict[str, dict[str, Any]] = {}
    with targets_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row.get("item_key", "").strip()
            if not key:
                continue
            route = row.get("route_used") or row.get("solver_used") or "(r,Q)"
            out_to: int | None = None
            if route in {"(s,S)", "ss"}:
                out_to = int(float(row["recommended_reorder_point"] or 0) + float(row["recommended_order_quantity"] or 0))
            policies[key] = {
                "policy": route,
                "rop": int(float(row.get("recommended_reorder_point") or 0)),
                "oq": int(float(row.get("recommended_order_quantity") or 1)),
                "ss": int(float(row.get("recommended_safety_stock") or 0)),
                "out_to": out_to,
            }
    return policies


# ── simulation ────────────────────────────────────────────────────────────────

def simulate(
    test_rows: list[dict[str, str]],
    policy: dict[str, Any],
    stats: dict[str, Any],
    shortage_penalty_rate: float = DEFAULT_SHORTAGE_PENALTY_RATE,
) -> dict[str, float]:
    if not test_rows:
        return _empty()
    inverted = _infer_sign_inverted(test_rows)

    rop = max(0, policy.get("rop") or 0)
    oq = max(1, policy.get("oq") or 1)
    out_to = policy.get("out_to")  # for (s,S): S level
    is_ss = out_to is not None

    lt_days = max(1, int(round(stats.get("mean_lead_time", 1.0))))
    inventory = float(max(rop + oq, policy.get("ss", 0)))
    on_order: list[tuple[int, float]] = []

    total_demand = 0.0
    served = 0.0
    shortage_units = 0.0
    stockout_days = 0
    inventory_sum = 0.0
    num_orders = 0

    for day_idx, row in enumerate(test_rows):
        for due, qty in on_order:
            if due <= day_idx:
                inventory += qty
        on_order = [(due, qty) for due, qty in on_order if due > day_idx]

        demand = _demand(row, inverted)
        total_demand += demand
        fill = min(inventory, demand)
        inventory -= fill
        served += fill
        short = demand - fill
        shortage_units += short
        if short > 1e-9:
            stockout_days += 1

        ip = inventory + sum(qty for _, qty in on_order)
        if ip <= rop:
            if is_ss:
                order_size = max(0, int(out_to) - int(ip))  # order up to S
            else:
                order_size = oq
            if order_size > 0:
                on_order.append((day_idx + lt_days, float(order_size)))
                num_orders += 1

        inventory_sum += inventory

    n = len(test_rows)
    avg_inv = inventory_sum / n
    holding = avg_inv * stats.get("annual_holding_cost_per_unit", 0.0) * n / 252.0
    ordering = num_orders * stats.get("ordering_cost", 75.0)
    shortage_cost = shortage_units * stats.get("unit_cost", 0.0) * shortage_penalty_rate
    total_cost = holding + ordering + shortage_cost
    fill_rate = served / total_demand if total_demand > 0 else 1.0
    return {
        "fill_rate_pct": round(fill_rate * 100.0, 4),
        "total_cost": round(total_cost, 4),
        "holding_cost": round(holding, 4),
        "ordering_cost": round(ordering, 4),
        "shortage_cost": round(shortage_cost, 4),
        "stockout_days": float(stockout_days),
        "shortage_units": shortage_units,
        "avg_inventory": avg_inv,
        "num_orders": num_orders,
        "test_days": n,
        "total_demand": total_demand,
    }


def _empty() -> dict[str, float]:
    return {k: 0.0 for k in (
        "fill_rate_pct", "total_cost", "holding_cost", "ordering_cost", "shortage_cost",
        "stockout_days", "shortage_units", "avg_inventory", "num_orders", "test_days", "total_demand",
    )}


# ── aggregate ─────────────────────────────────────────────────────────────────

def _aggregate(results: list[dict[str, Any]], policy_key: str) -> dict[str, Any]:
    rows = [r[policy_key] for r in results if policy_key in r]
    if not rows:
        return {}
    fill_rates = [r["fill_rate_pct"] for r in rows]
    costs = [r["total_cost"] for r in rows]
    stockout = [r["stockout_days"] for r in rows]
    shortage = [r["shortage_units"] for r in rows]
    total_demand = sum(r["total_demand"] for r in rows)
    total_served = sum(r["total_demand"] * r["fill_rate_pct"] / 100.0 for r in rows)
    return {
        "n_materials": len(rows),
        "mean_fill_rate_pct": round(mean(fill_rates), 4),
        "median_fill_rate_pct": round(median(fill_rates), 4),
        "agg_fill_rate_pct": round(total_served / total_demand * 100.0, 4) if total_demand > 0 else 0.0,
        "pct_ge_95": round(100.0 * sum(1 for x in fill_rates if x >= 95.0) / len(rows), 4),
        "zero_stockout_pct": round(100.0 * sum(1 for x in stockout if x == 0) / len(rows), 4),
        "mean_total_cost": round(mean(costs), 4),
        "total_cost_sum": round(sum(costs), 4),
        "mean_holding_cost": round(mean(r["holding_cost"] for r in rows), 4),
        "mean_ordering_cost": round(mean(r["ordering_cost"] for r in rows), 4),
        "total_stockout_days": int(sum(stockout)),
        "mean_stockout_days": round(mean(stockout), 4),
        "mean_shortage_units": round(mean(shortage), 4),
    }


# ── main backtest ─────────────────────────────────────────────────────────────

def run_backtest(
    grouped_rows: dict[str, list[dict[str, str]]],
    train_cutoff: str,
    valid_end: str,
    route_payloads: dict[str, dict[str, Any]] | None = None,
    targets_policies: dict[str, dict[str, Any]] | None = None,
    selected_item_keys: set[str] | None = None,
    shortage_penalty_rate: float = DEFAULT_SHORTAGE_PENALTY_RATE,
) -> dict[str, Any]:
    """Run reproducible inventory backtest for all plant-material pairs.

    Policy resolution order for inventor_selected:
      1. Per-item numeric params from targets_policies (paper-grade CSV if available)
      2. Cached LLM route payloads from route_payloads
      3. Fall back to universal (r,Q)
    """
    cutoff = _parse_date(train_cutoff)
    end = _parse_date(valid_end)
    route_payloads = route_payloads or {}
    targets_policies = targets_policies or {}

    per_item: list[dict[str, Any]] = []
    skipped = 0

    for item_key, all_rows in grouped_rows.items():
        if selected_item_keys is not None and item_key not in selected_item_keys:
            continue
        train = [r for r in all_rows if _parse_date(r["date"]) < cutoff]
        test = [r for r in all_rows if cutoff <= _parse_date(r["date"]) <= end]
        pre_wd = sum(1 for r in train if _f(r.get("is_working_day"), 0) == 1)
        post_wd = sum(1 for r in test if _f(r.get("is_working_day"), 0) == 1)
        if pre_wd < 20 or post_wd < 60:
            skipped += 1
            continue

        stats = compute_item_stats(train)

        # Policy resolution
        if item_key in targets_policies:
            inv_policy = targets_policies[item_key]
        elif item_key in route_payloads:
            inv_policy = _policy_from_cache(route_payloads[item_key], stats)
        else:
            inv_policy = _make_rq_policy(stats)

        sl = stats["service_level"]
        policies = {
            "inventor_selected": inv_policy,
            "universal_rq":      _make_rq_policy(stats, sl),
            "universal_ss":      _make_ss_policy(stats, sl),
            "sap_static":        _make_sap_policy(stats),
            "eoq_pure":          _make_eoq_policy(stats),
            "k_sigma":           _make_k_sigma_policy(stats),
        }

        item_result: dict[str, Any] = {"item_key": item_key}
        for name, pol in policies.items():
            item_result[name] = simulate(test, pol, stats, shortage_penalty_rate)

        item_result["train_days"] = len(train)
        item_result["test_days"] = len(test)
        item_result["route_used"] = inv_policy.get("policy", "(r,Q)")
        per_item.append(item_result)

    policy_names = ["inventor_selected", "universal_rq", "universal_ss", "sap_static", "eoq_pure", "k_sigma"]
    aggregate = {name: _aggregate(per_item, name) for name in policy_names}

    # Build comparison vs inventor_selected
    ref_costs = {r["item_key"]: r["inventor_selected"]["total_cost"] for r in per_item}
    ref_fill = {r["item_key"]: r["inventor_selected"]["fill_rate_pct"] for r in per_item}
    comparison: dict[str, Any] = {}
    for name in [n for n in policy_names if n != "inventor_selected"]:
        eligible = [r for r in per_item if name in r]
        fill_wins = sum(1 for r in eligible if r[name]["fill_rate_pct"] > ref_fill[r["item_key"]])
        fill_losses = sum(1 for r in eligible if r[name]["fill_rate_pct"] < ref_fill[r["item_key"]])
        cost_better = sum(1 for r in eligible if r[name]["total_cost"] < ref_costs[r["item_key"]])
        comparison[name] = {
            "eligible_items": len(eligible),
            "fill_rate_wins": fill_wins,
            "fill_rate_losses": fill_losses,
            "fill_rate_ties": len(eligible) - fill_wins - fill_losses,
            "cost_better_count": cost_better,
            "mean_fill_rate_delta": round(
                mean(r[name]["fill_rate_pct"] - ref_fill[r["item_key"]] for r in eligible), 4
            ) if eligible else 0.0,
            "mean_total_cost_delta": round(
                mean(r[name]["total_cost"] - ref_costs[r["item_key"]] for r in eligible), 4
            ) if eligible else 0.0,
        }

    # Branch summary by route_used
    branch_counts: dict[str, list[dict[str, float]]] = defaultdict(list)
    for r in per_item:
        branch_counts[r["route_used"]].append(r["inventor_selected"])
    branch_summary = {
        branch: {
            "n": len(items),
            "mean_fill_rate_pct": round(mean(x["fill_rate_pct"] for x in items), 4),
            "mean_total_cost": round(mean(x["total_cost"] for x in items), 4),
            "mean_stockout_days": round(mean(x["stockout_days"] for x in items), 4),
        }
        for branch, items in branch_counts.items()
    }

    return {
        "csv_path": None,
        "route_source": "targets_csv" if targets_policies else ("route_cache" if route_payloads else "fallback_rq"),
        "train_cutoff": train_cutoff,
        "valid_end": valid_end,
        "policies": policy_names,
        "items_evaluated": len(per_item),
        "items_skipped": skipped,
        "results": per_item,
        "aggregate": aggregate,
        "comparison": comparison,
        "branch_summary": branch_summary,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run reproducible inventory backtest simulation.")
    parser.add_argument("--csv-path", default=str(CSV_PATH))
    parser.add_argument("--train-cutoff", default="2026-03-10",
                        help="Last date inclusive for training data (ISO format)")
    parser.add_argument("--valid-end", default="2026-06-19",
                        help="Last date inclusive for validation (ISO format)")
    parser.add_argument("--route-source", default="targets_csv",
                        choices=["targets_csv", "route_cache", "fallback_rq"],
                        help="Policy source for inventor_selected: targets_csv uses existing paper CSV")
    parser.add_argument("--route-cache-dir", default=str(ROOT / "batches" / "backtest_routes"))
    parser.add_argument("--targets-csv", default=str(INTERNAL_DIR / "target_ranking.csv"))
    parser.add_argument("--output", default=str(DEFAULT_BACKTEST_JSON))
    parser.add_argument("--shortage-penalty-rate", type=float, default=DEFAULT_SHORTAGE_PENALTY_RATE)
    parser.add_argument("--print-items", action="store_true",
                        help="Include per-item results in JSON output (large)")
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    if not csv_path.exists():
        print(f"Error: CSV not found: {csv_path}", file=sys.stderr)
        raise SystemExit(1)

    print(f"Loading {csv_path}...", file=sys.stderr)
    grouped = load_grouped_rows(csv_path)
    print(f"  {len(grouped)} plant-material pairs", file=sys.stderr)

    route_payloads: dict[str, dict[str, Any]] = {}
    targets_policies: dict[str, dict[str, Any]] = {}

    if args.route_source == "targets_csv":
        targets_policies = load_targets_policies(Path(args.targets_csv))
        if not targets_policies:
            print("Error: no target policies found in targets CSV", file=sys.stderr)
            raise SystemExit(1)
        print(f"  Loaded {len(targets_policies)} policies from targets CSV", file=sys.stderr)
    elif args.route_source == "route_cache":
        route_payloads = load_cached_route_payloads(args.route_cache_dir, args.train_cutoff)
        print(f"  Loaded {len(route_payloads)} cached routes", file=sys.stderr)
    else:
        print("  Using fallback (r,Q) policy for all items", file=sys.stderr)

    result = run_backtest(
        grouped, args.train_cutoff, args.valid_end,
        route_payloads=route_payloads,
        targets_policies=targets_policies,
        selected_item_keys=set(targets_policies) if args.route_source == "targets_csv" else None,
        shortage_penalty_rate=args.shortage_penalty_rate,
    )
    result["csv_path"] = str(csv_path)

    if not args.print_items:
        result.pop("results", None)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nEvaluated: {result['items_evaluated']} items | Skipped: {result['items_skipped']}", file=sys.stderr)
    print(f"Policy source: {result['route_source']}", file=sys.stderr)
    print("\nAggregate (inventor_selected vs baselines):")
    for name in result["policies"]:
        ag = result["aggregate"].get(name, {})
        print(
            f"  {name:22s}: fill={ag.get('mean_fill_rate_pct', 0):7.3f}%  "
            f"cost={ag.get('mean_total_cost', 0):12.0f}  "
            f"stockout_days={ag.get('mean_stockout_days', 0):.2f}"
        )
    print(f"\nOutput: {output}")


if __name__ == "__main__":
    main()
