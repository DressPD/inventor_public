"""Core inventory policy solvers: (r,Q), (s,S), NB branch, Croston, EOQ."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import scipy.stats

from inventor_tests.deterministic_method.stats_calculator import infer_demand_sign_inversion, normalized_row_demand

DEFAULT_SERVICE_LEVEL: float = 0.95
CROSTON_ALPHA: float = 0.10
GAMMA: float = 0.50
SPIKE_PERCENTILE: float = 95.0

_NAME_MAP: dict[str, str] = {
    "(r,q)": "(r,Q)", "rq": "(r,Q)", "r,q": "(r,Q)", "r-q": "(r,Q)",
    "reorder-point": "(r,Q)", "reorder point": "(r,Q)",
    "(s,s)": "(s,S)", "ss": "(s,S)", "s,s": "(s,S)", "s-s": "(s,S)",
    "order-up-to": "(s,S)", "order up to": "(s,S)",
    "negbin": "negbin", "negative binomial": "negbin", "neg-bin": "negbin",
    "nb": "negbin", "negativebinomial": "negbin", "nb branch": "negbin",
    "croston": "croston", "croston's method": "croston", "croston method": "croston", "intermittent": "croston",
    "eoq": "eoq", "economic order quantity": "eoq", "wilson": "eoq",
    "base-stock": "(s,S)", "basestock": "(s,S)", "base stock": "(s,S)",
}


def _normalise_model_name(model: str) -> str:
    key = (model or "").strip().lower()
    return _NAME_MAP.get(key, model)


def _extract_daily_demand(rows: list[dict]) -> np.ndarray:
    sign_inverted = infer_demand_sign_inversion(rows)
    vals = [normalized_row_demand(r, sign_inverted) for r in rows]
    return np.array([v for v in vals if v > 0], dtype=float)


def _solve_rq(stats: dict[str, Any], service_level: float) -> dict[str, Any]:
    mean_d = max(float(stats.get("mean_daily_demand", 0.0)), 0.0)
    robust_std = max(float(stats.get("robust_std_daily", stats.get("std_daily_demand", 0.0))), 0.0)
    mean_lt = max(float(stats.get("mean_lead_time", 0.0)), 0.0)
    effective_lt = max(float(stats.get("effective_lead_time", mean_lt)), 0.0)
    std_lt = max(float(stats.get("std_lead_time", 0.0)), 0.0)
    d_max = max(float(stats.get("d_max_wd", stats.get("d_max_calendar", 0.0))), 0.0)
    z = float(scipy.stats.norm.ppf(service_level)) if 0 < service_level < 1 else float(scipy.stats.norm.ppf(DEFAULT_SERVICE_LEVEL))
    sigma_ltd_rob = math.sqrt(max(mean_lt * (robust_std ** 2) + (mean_d ** 2) * (std_lt ** 2), 0.0)) if mean_lt > 0 else 0.0
    ss_normal = z * sigma_ltd_rob
    ss_spike = GAMMA * max(0.0, d_max - mean_d) * math.sqrt(mean_lt) if mean_lt > 0 else 0.0
    ss = max(0.0, ss_normal + ss_spike)
    rop = mean_d * effective_lt + ss
    oq = max(int(stats.get("order_quantity", 1) or 1), int(stats.get("moq", 1) or 1))
    return {
        "safety_stock": int(round(ss)),
        "reorder_point": int(round(rop)),
        "order_quantity": oq,
        "order_up_to": None,
        "policy_note": f"(r,Q): σ_LTD_rob={sigma_ltd_rob:.1f}, SS={ss:.1f}, ROP={rop:.1f}, OQ={oq}",
    }


def _solve_ss(stats: dict[str, Any], service_level: float) -> dict[str, Any]:
    base = _solve_rq(stats, service_level)
    oq = int(base["order_quantity"])
    rop = int(base["reorder_point"])
    return {
        **base,
        "order_up_to": rop + oq,
        "policy_note": f"(s,S): R={rop}, S={rop + oq}, OQ={oq}",
    }


def _solve_eoq(stats: dict[str, Any], service_level: float) -> dict[str, Any]:
    _ = service_level
    oq = max(int(stats.get("order_quantity", 1) or 1), int(stats.get("moq", 1) or 1))
    mean_d = max(float(stats.get("mean_daily_demand", 0.0)), 0.0)
    mean_lt = max(float(stats.get("mean_lead_time", 0.0)), 0.0)
    rop = mean_d * mean_lt
    return {
        "safety_stock": 0,
        "reorder_point": int(round(rop)),
        "order_quantity": oq,
        "order_up_to": None,
        "policy_note": f"EOQ: ROP={rop:.1f}, OQ={oq}",
    }


def _solve_negbin(stats: dict[str, Any], service_level: float) -> dict[str, Any]:
    mean_d = max(float(stats.get("mean_daily_demand", 0.0)), 0.0)
    var_d = max(float(stats.get("std_daily_demand", 0.0)) ** 2, 0.0)
    mean_lt = max(float(stats.get("mean_lead_time", 0.0)), 0.0)
    std_lt = max(float(stats.get("std_lead_time", 0.0)), 0.0)
    eff_lt = max(float(stats.get("effective_lead_time", mean_lt)), 0.0)
    oq = max(int(stats.get("order_quantity", 1) or 1), int(stats.get("moq", 1) or 1))

    ltd_mean = mean_d * mean_lt
    ltd_var = max(mean_lt * var_d + (mean_d ** 2) * (std_lt ** 2), ltd_mean + 1e-9)

    if ltd_mean <= 0.0 or ltd_var <= ltd_mean:
        fallback = _solve_rq(stats, service_level)
        fallback["policy_note"] = f"NB branch fallback ({fallback['policy_note']})"
        return fallback

    p_lt = ltd_mean / ltd_var
    r_lt = ltd_mean * p_lt / (1.0 - p_lt)
    q = min(max(service_level, 1e-6), 0.999999)
    rop_lt = float(scipy.stats.nbinom.ppf(q, r_lt, p_lt))
    rop = rop_lt + mean_d * max(eff_lt - mean_lt, 0.0)
    ss = max(0.0, rop - round(mean_d * eff_lt))
    return {
        "safety_stock": int(round(ss)),
        "reorder_point": int(round(rop)),
        "order_quantity": oq,
        "order_up_to": None,
        "policy_note": f"NB branch: LTD_mean={ltd_mean:.1f}, LTD_var={ltd_var:.1f}, r_lt={r_lt:.2f}, p_lt={p_lt:.4f}, ROP={rop:.1f}, SS={ss:.1f}, OQ={oq}",
    }


def _solve_croston(stats: dict[str, Any], rows: list[dict], service_level: float) -> dict[str, Any]:
    _ = service_level
    demand = _extract_daily_demand(rows)
    if len(demand) == 0:
        return _solve_rq(stats, DEFAULT_SERVICE_LEVEL)
    mean_d = float(np.mean(demand))
    mean_lt = max(float(stats.get("mean_lead_time", 0.0)), 0.0)
    eff_lt = max(float(stats.get("effective_lead_time", mean_lt)), 0.0)
    oq = max(int(stats.get("order_quantity", 1) or 1), int(stats.get("moq", 1) or 1))
    rop = mean_d * eff_lt
    return {
        "safety_stock": 0,
        "reorder_point": int(round(rop)),
        "order_quantity": oq,
        "order_up_to": None,
        "policy_note": f"Croston-style intermittent fallback: ROP={rop:.1f}, OQ={oq}",
    }


def route_to_solver(model: str, confidence: str, stats: dict[str, Any], rows: list[dict], service_level: float | None = None) -> dict[str, Any]:
    service = float(service_level or stats.get("service_level") or DEFAULT_SERVICE_LEVEL)
    model_key = _normalise_model_name(model)
    if confidence == "UNCERTAIN":
        model_key = "(r,Q)"
    if model_key == "(r,Q)":
        return _solve_rq(stats, service)
    if model_key == "(s,S)":
        return _solve_ss(stats, service)
    if model_key == "negbin":
        return _solve_negbin(stats, service)
    if model_key == "croston":
        return _solve_croston(stats, rows, service)
    return _solve_eoq(stats, service)
