"""Isolated offline sensitivities. Nothing here changes the frozen core replay."""
from __future__ import annotations

import hashlib
import math
import random
from statistics import mean
from datetime import date, timedelta
from typing import Any

from inventory_llm import core

SEEDS = (20261025, 20261026, 20261027, 20261028, 20261029)
PENALTIES = (0, 1, 5)


def finite(value: Any) -> None:
    """Reject nonfinite numeric trees before simulation or serialization."""
    if isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            finite(child)
    elif isinstance(value, (float, int)) and not math.isfinite(value):
        raise ValueError("nonfinite numeric input/output")


def lead_stream(train: list[dict], stats: dict, length: int, key: str, seed: int) -> tuple[list[int], bool]:
    """One draw per working observation, not per order; paired across arms."""
    observations = [core.f(r.get("delivery_time")) for r in train]
    finite(observations)
    values = [value for value in observations if value > 0]
    finite([values, stats])
    fallback = not values
    values = values or [stats["mean_lead_time"]]
    rng = random.Random(int.from_bytes(hashlib.sha256(f"{seed}:{key}".encode()).digest()))
    return [max(1, int(round(rng.choice(values)))) for _ in range(length)], fallback


def simulate(test: list[dict], policy: dict, stats: dict, initial_inventory: float,
             *, strict: bool = True, warmup: list[dict] | None = None,
             leads: list[int] | None = None) -> dict:
    """Working-observation replay, optionally carrying a hypothetical warm-up.

    Strict=False reproduces frozen capacity clipping, including its sub-MOQ
    releases. Strict=True floors headroom (not position) and defers below MOQ.
    Lead streams index the combined warm-up/evaluation working observations.
    Costs, demand and order counts exclude warm-up; outstanding orders survive.
    """
    finite([policy, stats, initial_inventory])
    for row in [*(warmup or []), *test]:
        finite([core.f(row.get(field)) for field in ("actual_demand", "delivery_time")])
    before = [r for r in (warmup or []) if core.is_working_day(r)]
    working = before + [r for r in test if core.is_working_day(r)]
    if any(a["date"] >= b["date"] for a, b in zip(working, working[1:])):
        raise ValueError("working dates must be strictly chronological")
    if leads is not None and (len(leads) < len(working) or
                              any(not isinstance(x, int) or x < 1 for x in leads)):
        raise ValueError("lead stream must cover every working day with positive integer offsets")
    lead = max(1, int(round(stats["mean_lead_time"])))
    inventory = max(0, initial_inventory)
    capacity = max(0, int(stats.get("max_storage_units", 0)))
    moq = max(1, int(stats.get("moq", 1)))
    rop, oq = int(policy.get("rop", 0)), max(1, int(policy.get("oq", 1)))
    out_to = policy.get("out_to")
    if out_to is not None and int(out_to) <= rop:
        raise ValueError("order-up-to level must exceed reorder point")
    dates = [core.parse_date(r["date"]) for r in working]
    pending: list[tuple[date, int]] = []
    res = dict(total_demand=0.0, shortage_units=0.0, stockout_days=0, num_orders=0,
               moq_deferrals=0, capacity_deferrals=0, sub_moq_orders=0,
               peak_on_hand=inventory, peak_inventory_position=inventory, days_over_capacity=0,
               physical_post_order_peak_position=inventory,
               max_excess_units=0.0, initial_excess_units=0.0,
               cutoff_pending_units=0, cutoff_inventory=inventory, test_days=len(working) - len(before))
    inventory_sum = 0.0
    for index, row in enumerate(working):
        current = dates[index]
        evaluate = index >= len(before)
        if index == len(before):
            res["cutoff_inventory"] = inventory
            res["cutoff_pending_units"] = sum(q for _, q in pending)
            res["initial_excess_units"] = max(0.0, inventory - capacity) if capacity else 0.0
            res["peak_on_hand"] = inventory
            res["peak_inventory_position"] = inventory + sum(q for _, q in pending)
            res["physical_post_order_peak_position"] = res["peak_inventory_position"]
            res["max_excess_units"] = res["initial_excess_units"]
        inventory += sum(q for due, q in pending if due <= current)
        pending = [(due, q) for due, q in pending if due > current]
        if evaluate:
            res["peak_on_hand"] = max(res["peak_on_hand"], inventory)
            if capacity and inventory > capacity:
                res["days_over_capacity"] += 1
                res["max_excess_units"] = max(res["max_excess_units"], inventory - capacity)
        demand = core.demand(row)
        fulfilled = min(inventory, demand)
        inventory -= fulfilled
        if evaluate:
            res["total_demand"] += demand
            res["shortage_units"] += demand - fulfilled
            res["stockout_days"] += int(fulfilled < demand)
        position = inventory + sum(q for _, q in pending)
        if evaluate:
            res["peak_inventory_position"] = max(res["peak_inventory_position"], position)
        if position <= rop:
            quantity = int(max(0, int(out_to) - position)) if out_to is not None else oq
            if capacity:
                headroom = math.floor(capacity - position) if strict else capacity - int(position)
                quantity = min(quantity, max(0, headroom))
            if strict and quantity < moq:
                if evaluate:
                    res["moq_deferrals"] += 1
                    res["capacity_deferrals"] += int(bool(capacity) and capacity - position < moq)
            elif quantity > 0:
                offset = leads[index] if leads is not None else lead
                due_index = index + offset
                due = dates[due_index] if due_index < len(dates) else current + timedelta(days=offset * 7)
                pending.append((due, quantity))
                if evaluate:
                    res["num_orders"] += 1
                    res["sub_moq_orders"] += int(quantity < moq)
                    if strict:
                        res["peak_inventory_position"] = max(res["peak_inventory_position"], position + quantity)
        if evaluate:
            res["physical_post_order_peak_position"] = max(
                res["physical_post_order_peak_position"], inventory + sum(q for _, q in pending))
            inventory_sum += inventory
    if not res["test_days"]:
        # No evaluation iteration reaches the boundary; retain warm-up state.
        # Leave legacy simulator fields/costs unchanged for empty evaluations.
        res["cutoff_inventory"] = inventory
        res["cutoff_pending_units"] = sum(q for _, q in pending)
        res["initial_excess_units"] = max(0.0, inventory - capacity) if capacity else 0.0
        res["physical_post_order_peak_position"] = inventory + res["cutoff_pending_units"]
    n = max(res["test_days"], 1)
    res.update(avg_inventory=inventory_sum / n,
               holding_cost=inventory_sum * stats["annual_holding_cost_per_unit"] / core.ANNUAL_WORKING_DAYS,
               ordering_cost=res["num_orders"] * stats["ordering_cost"], shortage_cost=0.0,
               max_storage_units=capacity)
    # Match core's operation order as well as its trajectory in compatibility mode.
    if not strict:
        res["holding_cost"] = res["avg_inventory"] * stats["annual_holding_cost_per_unit"] * n / core.ANNUAL_WORKING_DAYS
    res["fill_rate_pct"] = 100 * (1 - res["shortage_units"] / res["total_demand"]) if res["total_demand"] else 100.0
    res["total_cost"] = res["holding_cost"] + res["ordering_cost"]
    res["shortage_exposure"] = res["shortage_units"] * stats["unit_cost"]
    res["costs_by_penalty"] = {str(p): res["total_cost"] + p * res["shortage_exposure"] for p in PENALTIES}
    finite(res)
    return res


def tune(rows: list[dict], penalty: int) -> dict:
    """Fit earlier 80% of pre-cutoff working days; select on remaining 20%."""
    if penalty not in (1, 5):
        raise ValueError("tuning penalty must be 1 or 5")
    train = sorted((r for r in rows if r["date"] < core.TRAIN_CUTOFF), key=lambda r: r["date"])
    working = [r for r in train if core.is_working_day(r)]
    split = int(len(working) * 0.8)
    record = dict(fit_days=split, selection_days=len(working) - split, penalty=penalty,
                  candidate_count=0, feasible_candidates=0, policy=None)
    if split < 20 or len(working) - split < 10:
        return {**record, "status": "insufficient_history"}
    boundary = working[split - 1]["date"]
    fit = [r for r in train if r["date"] <= boundary]
    selection = [r for r in train if r["date"] > boundary]
    stats = core.compute_stats(fit)
    finite(stats)
    lt = max(stats["mean_lead_time"], 0.1)
    sigma = math.sqrt(max(lt * stats["std_daily_demand"] ** 2 +
                          stats["mean_daily_demand"] ** 2 * stats["std_lead_time"] ** 2, 0.0))
    base_oq = core._order_quantity(stats)
    base = core.make_cold_rq_policy(stats)
    opening = core.opening_inventory(selection, base["rop"] + base["oq"])
    target = 100 * stats["service_level"]
    candidates = []
    for z in core.TUNING_RESERVE_Z:
        for multiple in core.TUNING_ORDER_MULTIPLES:
            record["candidate_count"] += 1
            policy = core.project_policy_to_feasibility(dict(
                policy=f"offline_tuned_p{penalty}",
                rop=max(0, math.ceil(stats["mean_daily_demand"] * lt + z * sigma)),
                ss=max(0, math.ceil(z * sigma)), oq=math.ceil(base_oq * multiple), out_to=None), stats)
            if policy is None:
                continue
            result = simulate(selection, policy, stats, opening)
            fill, cost = result["fill_rate_pct"], result["costs_by_penalty"][str(penalty)]
            # Candidate index is final deterministic tie break; no silent deduplication.
            score = (0, cost, -fill, record["candidate_count"]) if fill >= target else (
                1, -fill, cost, record["candidate_count"])
            candidates.append((score, policy, result))
    record["feasible_candidates"] = len(candidates)
    record.update(fit_end=boundary, selection_start=selection[0]["date"],
                  selection_end=selection[-1]["date"], selection_opening=opening, target_fill_pct=target)
    if not candidates:
        return {**record, "status": "no_feasible_candidate"}
    _, chosen, result = min(candidates, key=lambda x: x[0])
    record.update(policy=chosen, selection_fill_pct=result["fill_rate_pct"],
                  selection_cost=result["costs_by_penalty"][str(penalty)],
                  status="target_met" if result["fill_rate_pct"] >= target else "target_failure_max_fill_fallback")
    return record


def summarize(metrics: list[dict]) -> dict:
    """Aggregate paired trajectories, without treating seeds/runs as subjects."""
    if not metrics:
        return {"n": 0}
    demand = sum(m["total_demand"] for m in metrics)
    shortage = sum(m["shortage_units"] for m in metrics)
    return {"n": len(metrics), "mean_fill_pct": mean(m["fill_rate_pct"] for m in metrics),
            "volume_weighted_fill_pct": 100 * (1 - shortage / demand) if demand else 100.0,
            "costs_by_penalty": {str(p): mean(m["costs_by_penalty"][str(p)] for m in metrics) for p in PENALTIES},
            **{field: sum(m[field] for m in metrics) for field in (
                "total_demand", "shortage_units", "stockout_days", "num_orders", "holding_cost", "ordering_cost",
                "moq_deferrals", "capacity_deferrals", "sub_moq_orders", "days_over_capacity", "initial_excess_units",
                "cutoff_pending_units")},
            "pairs_over_capacity": sum(m["days_over_capacity"] > 0 for m in metrics),
            "max_excess_units": max(m["max_excess_units"] for m in metrics),
            "max_peak_on_hand": max(m["peak_on_hand"] for m in metrics),
            "max_peak_inventory_position": max(m["peak_inventory_position"] for m in metrics),
            "max_physical_post_order_peak_position": max(m["physical_post_order_peak_position"] for m in metrics)}
