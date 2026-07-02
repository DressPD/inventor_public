"""Deterministic escalation rules."""

from __future__ import annotations

CV_WD_HIGH_THRESHOLD = 0.70
CV_LT_SEVERE_THRESHOLD = 0.80
DELIVERY_OBS_THIN_THRESHOLD = 10


def evaluate_hard_flag(stats: dict, policy_values: dict, slt: dict) -> dict:
    reason_codes: list[str] = []
    reasons: list[str] = []

    milp_trigger = policy_values.get("milp_trigger") or stats.get("milp_pretrigger")
    if milp_trigger:
        reason_codes.append(f"MILP_{milp_trigger}")
        reasons.append("MILP trigger active")

    if slt.get("override_flag"):
        reason_codes.append("SLT_OVERRIDE")
        reasons.append("Safety lead time override requested")

    high_boundary_profile = (
        stats.get("lead_time_stability") == "Unstable"
        and float(stats.get("cv_wd", 0.0) or 0.0) > CV_WD_HIGH_THRESHOLD
    )
    if high_boundary_profile:
        if int(stats.get("delivery_observations", 0) or 0) < DELIVERY_OBS_THIN_THRESHOLD:
            reason_codes.append("UNSTABLE_LT_THIN_DATA")
            reasons.append("Unstable lead time with thin delivery evidence")
        if float(stats.get("cv_lead_time", 0.0) or 0.0) > CV_LT_SEVERE_THRESHOLD:
            reason_codes.append("UNSTABLE_LT_SEVERE_VARIANCE")
            reasons.append("Unstable lead time with severe variance")
        if slt.get("comparison_action") == "INCREASE":
            reason_codes.append("UNSTABLE_LT_SLT_INCREASE")
            reasons.append("Unstable lead time and SLT increase recommended")

    return {
        "hard_escalation_flag": "YES" if reason_codes else "NO",
        "reason_codes": reason_codes,
        "reasons": reasons,
        "input_snapshot": {
            "cv_wd": stats.get("cv_wd"),
            "cv_lead_time": stats.get("cv_lead_time"),
            "delivery_observations": stats.get("delivery_observations"),
            "lead_time_stability": stats.get("lead_time_stability"),
            "comparison_action": slt.get("comparison_action"),
            "milp_trigger": milp_trigger,
        },
    }
