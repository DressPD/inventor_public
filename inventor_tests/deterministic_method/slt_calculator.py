"""Safety lead time calculations."""

from __future__ import annotations

import math


def compute_slt(stats: dict) -> dict:
    mean_lt = float(stats.get("mean_lead_time", 0.0) or 0.0)
    std_lt = float(stats.get("std_lead_time", 0.0) or 0.0)
    delivery_observations = int(stats.get("delivery_observations", 0) or 0)
    current_slt = float(stats.get("current_sap_slt_days", 0.0) or 0.0)
    distance_km = float(stats.get("distance_km", 0.0) or 0.0)
    supplier_reliability = float(stats.get("supplier_reliability", 0.0) or 0.0)

    if mean_lt <= 0.0:
        return {
            "recommended_days": 0.0,
            "sigma_eff_days": 0.0,
            "dominant_factor": "NO_BASELINE",
            "dominant_pct": 0.0,
            "variance_components": {},
            "disruption_premium": 0.0,
            "comparison_action": "NO_BASELINE",
            "override_flag": False,
        }

    supplier_component = max((1.0 - supplier_reliability), 0.0) * 2.0
    transport_component = min(distance_km / 1000.0, 2.0)
    variance_component = std_lt
    sigma_eff_days = math.sqrt(supplier_component ** 2 + transport_component ** 2 + variance_component ** 2)
    recommended_days = round(max(mean_lt + sigma_eff_days, 0.0) / 0.5) * 0.5

    components = {
        "supplier": supplier_component,
        "transport": transport_component,
        "variance": variance_component,
    }
    dominant_factor = max(components, key=components.get) if components else "variance"
    total = sum(components.values()) or 1.0
    dominant_pct = 100.0 * components[dominant_factor] / total
    override_flag = delivery_observations < 10 and std_lt > 0.8

    return {
        "recommended_days": recommended_days,
        "sigma_eff_days": sigma_eff_days,
        "dominant_factor": dominant_factor,
        "dominant_pct": dominant_pct,
        "variance_components": components,
        "disruption_premium": supplier_component,
        "comparison_action": compare_slt_vs_sap(stats, {"recommended_days": recommended_days}),
        "override_flag": override_flag,
    }


def compare_slt_vs_sap(stats: dict, slt: dict) -> str:
    current_slt = float(stats.get("current_sap_slt_days", 0.0) or 0.0)
    rec = float(slt.get("recommended_days", 0.0) or 0.0)
    if rec > current_slt + 0.25:
        return "INCREASE"
    if rec < current_slt - 0.25:
        return "DECREASE"
    return "MAINTAIN"
