"""
llm_api_client.py - Provider-agnostic LLM chat client for InventOR.
Uses the OpenAI Python SDK. Fully local: point OPENAI_BASE_URL at
Ollama, vLLM, LocalAI, or any OpenAI-compatible endpoint.
Config via env vars (or .env file):
  OPENAI_API_KEY  — API key (required; use "sk-no-key-required" for local)
  OPENAI_BASE_URL — base URL (e.g. http://localhost:11434/v1 for Ollama)
  LLM_MODEL       — model name (default: gpt-4o)
"""

import csv
import io
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "batches" / "results" / "materials"
ALLOWED_DISTRIBUTIONS = frozenset({"Poisson", "Normal", "Negative Binomial", "Lognormal", "Gamma"})


def _env_file_candidates() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("INVENTOR_ENV_FILE") or os.environ.get("ENV_PATH")
    if explicit:
        candidates.append(Path(explicit).expanduser())
    candidates.append(ROOT.parent / ".env")
    candidates.append(Path.cwd() / ".env")
    return candidates


def _load_env_file() -> Path | None:
    for candidate in _env_file_candidates():
        if candidate.exists():
            load_dotenv(dotenv_path=candidate, override=False)
            return candidate
    return None


def _output_dir() -> Path:
    output_dir = os.environ.get("LLM_OUTPUT_DIR", "").strip()
    return Path(output_dir).expanduser() if output_dir else DEFAULT_OUTPUT_DIR


def validate_credentials() -> tuple[str, str]:
    """Check that an API key is available."""
    _load_env_file()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not found. Set OPENAI_API_KEY in environment or .env file. "
            "For local LLMs (Ollama etc.) use any placeholder like 'sk-no-key-required'."
        )
    return (api_key, "")


def llm_chat(prompt: str, system_prompt: str | None = None, api_key: str | None = None) -> str:
    """Send a chat completion request via the OpenAI SDK.

    Fully local: set OPENAI_BASE_URL to your local endpoint
    (e.g. http://localhost:11434/v1 for Ollama).
    """
    client_kwargs = {}
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            client_kwargs["api_key"] = api_key

    client = OpenAI(**client_kwargs)
    model = os.environ.get("LLM_MODEL", "gpt-4o")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    resp = client.chat.completions.create(model=model, messages=messages)
    return resp.choices[0].message.content


def build_prompt(stats: dict, policy_values: dict, slt: dict) -> str:
    """Pure variable injection block. Zero instructions. LLM system_prompt.txt handles pipeline."""
    material_id          = stats.get("material_id", "UNKNOWN")
    plant_code           = stats.get("plant_code")
    mean_daily_demand    = float(stats.get("mean_daily_demand") or 0.0)
    std_daily_demand     = float(stats.get("std_daily_demand") or 0.0)
    robust_std_daily     = float(stats.get("robust_std_daily") or std_daily_demand)
    annual_demand_days   = float(stats.get("annual_demand_days") or 365.0)
    cv_wd                = float(stats.get("cv_wd") or 0.0)
    non_zero_fraction_wd = float(stats.get("non_zero_fraction_wd") or 0.0)
    trend_detected       = bool(stats.get("trend_flag", stats.get("trend_detected", False)))
    regime               = str(stats.get("regime") or "")
    distribution_type    = str(stats.get("distribution_type") or "")
    d_max_calendar       = float(stats.get("d_max_calendar") or mean_daily_demand)
    d_max_wd             = float(stats.get("d_max_wd") or d_max_calendar)
    total_rows           = int(stats.get("total_rows") or 0)
    working_days         = int(stats.get("working_days") or 0)
    delivery_observations = int(stats.get("delivery_observations") or 0)
    outliers_detected    = int(stats.get("outliers_detected") or 0)
    lower_bound          = float(stats.get("lower_bound") or 0.0)
    upper_bound          = float(stats.get("upper_bound") or 0.0)
    milp_pretrigger      = stats.get("milp_pretrigger")
    mean_lead_time       = float(stats.get("mean_lead_time") or 0.0)
    std_lead_time        = float(stats.get("std_lead_time") or 0.0)
    cv_lead_time         = float(stats.get("cv_lead_time") or 0.0)
    supplier_reliability = float(stats.get("supplier_reliability") or 0.0)
    stability            = str(stats.get("lead_time_stability") or stats.get("stability") or "")
    effective_lead_time  = float(stats.get("effective_lead_time") or mean_lead_time)
    z                    = float(stats.get("z_score") or 1.645)
    service_level        = float(stats.get("service_level") or 0.95)
    ordering_cost        = float(stats.get("ordering_cost") or 0.0)
    annual_holding       = float(stats.get("annual_holding_cost_per_unit") or 0.0)
    unit_cost            = float(stats.get("unit_cost") or 0.0)
    holding_cost_rate    = float(stats.get("holding_cost_rate") or 0.0)
    moq                  = int(stats.get("moq") or 0)
    lot_size             = int(stats.get("lot_size") or 1)
    max_stock            = policy_values.get("max_stock")
    current_safety_stock = int(stats.get("current_safety_stock_units") or 0)
    current_sap_slt_days = stats.get("current_sap_slt_days")
    slt_days             = float(slt.get("recommended_days") or 0.0)
    slt_sigma_eff        = float(slt.get("sigma_eff_days") or 0.0)
    slt_dominant_factor  = str(slt.get("dominant_factor") or "")
    slt_dominant_pct     = float(slt.get("dominant_pct") or 0.0)
    vc                   = slt.get("variance_components", {})
    slt_var_transport    = float(vc.get("transport") or 0.0)
    slt_var_supplier     = float(vc.get("supplier") or 0.0)
    slt_var_quality      = float(vc.get("quality") or 0.0)
    slt_disruption_premium = float(slt.get("disruption_premium") or 0.0)
    slt_comparison_action  = str(slt.get("comparison_action") or "NO_BASELINE")
    slt_override_flag      = slt.get("override_flag")

    r = repr
    return (
        f"import math, json\n"
        f"\n"
        f"# === MATERIAL ===\n"
        f"material_id           = {r(material_id)}\n"
        f"plant_code            = {r(plant_code)}\n"
        f"\n"
        f"# === DATA QUALITY ===\n"
        f"total_rows            = {total_rows}\n"
        f"working_days          = {working_days}\n"
        f"delivery_observations = {delivery_observations}\n"
        f"outliers_detected     = {outliers_detected}\n"
        f"winsor_lower          = {r(lower_bound)}\n"
        f"winsor_upper          = {r(upper_bound)}\n"
        f"\n"
        f"# === DEMAND (pre-computed, do NOT recalculate) ===\n"
        f"mean_daily_demand     = {r(mean_daily_demand)}\n"
        f"std_daily_demand      = {r(std_daily_demand)}\n"
        f"robust_std_daily     = {r(robust_std_daily)}\n"
        f"annual_demand_days    = {r(annual_demand_days)}\n"
        f"cv_wd                 = {r(cv_wd)}\n"
        f"non_zero_fraction_wd  = {r(non_zero_fraction_wd)}\n"
        f"trend_detected        = {r(trend_detected)}\n"
        f"d_max_calendar        = {r(d_max_calendar)}\n"
        f"d_max_wd              = {r(d_max_wd)}\n"
        f"regime                = {r(regime)}\n"
        f"distribution_type     = {r(distribution_type)}\n"
        f"\n"
        f"# === LEAD TIME (pre-computed, do NOT recalculate) ===\n"
        f"mean_lead_time        = {r(mean_lead_time)}\n"
        f"std_lead_time         = {r(std_lead_time)}\n"
        f"cv_lead_time          = {r(cv_lead_time)}\n"
        f"supplier_reliability  = {r(supplier_reliability)}\n"
        f"stability             = {r(stability)}\n"
        f"effective_lead_time   = {r(effective_lead_time)}\n"
        f"\n"
        f"# === COST AND POLICY PARAMS ===\n"
        f"z                     = {r(z)}          # norm.ppf({r(service_level)})\n"
        f"service_level         = {r(service_level)}\n"
        f"ordering_cost         = {r(ordering_cost)}\n"
        f"annual_holding        = {r(annual_holding)}\n"
        f"unit_cost             = {r(unit_cost)}\n"
        f"holding_cost_rate     = {r(holding_cost_rate)}\n"
        f"moq                   = {r(moq)}\n"
        f"lot_size              = {r(lot_size)}\n"
        f"max_stock             = {r(max_stock)}\n"
        f"current_safety_stock  = {r(current_safety_stock)}\n"
        f"current_sap_slt_days  = {r(current_sap_slt_days)}\n"
        f"milp_pretrigger       = {r(milp_pretrigger)}\n"
        f"\n"
        f"# === SAFETY LEAD TIME (pre-computed -- copy verbatim to output schema) ===\n"
        f"slt_days              = {r(slt_days)}\n"
        f"slt_sigma_eff         = {r(slt_sigma_eff)}\n"
        f"slt_dominant_factor   = {r(slt_dominant_factor)}\n"
        f"slt_dominant_pct      = {r(slt_dominant_pct)}\n"
        f"slt_var_transport     = {r(slt_var_transport)}\n"
        f"slt_var_supplier      = {r(slt_var_supplier)}\n"
        f"slt_var_quality       = {r(slt_var_quality)}\n"
        f"slt_disruption_premium= {r(slt_disruption_premium)}\n"
        f"slt_comparison_action = {r(slt_comparison_action)}\n"
        f"slt_override_flag     = {r(slt_override_flag)}\n"
        f"\n"
        f"# === FORMULA APPLICATION ===\n"
        f"gamma                 = 0.50\n"
        f"sigma_ltd             = math.sqrt(\n"
        f"    mean_lead_time * std_daily_demand**2\n"
        f"    + mean_daily_demand**2 * std_lead_time**2\n"
        f")\n"
        f"safety_stock          = z * sigma_ltd\n"
        f"safety_stock_robust   = (\n"
        f"    safety_stock\n"
        f"    + gamma * max(0.0, d_max_wd - mean_daily_demand)"
        f" * math.sqrt(mean_lead_time)\n"
        f")\n"
        f"annual_demand         = mean_daily_demand * annual_demand_days\n"
        f"eoq_raw               = (\n"
        f"    math.sqrt(2 * ordering_cost * annual_demand / annual_holding)\n"
        f"    if annual_holding > 0 else float('inf')\n"
        f")\n"
        f"q_base                = max(eoq_raw, moq)\n"
        f"order_quantity        = (\n"
        f"    math.ceil(q_base / lot_size) * lot_size if lot_size > 0"
        f" else int(math.ceil(q_base))\n"
        f")\n"
        f"if max_stock is not None and max_stock > 0 and order_quantity > max_stock:\n"
        f"    order_quantity    = max_stock\n"
        f"    milp_trigger      = 'T2'\n"
        f"else:\n"
        f"    milp_trigger      = milp_pretrigger\n"
        f"\n"
        f"policy_safety_stock   = math.ceil(safety_stock_robust)\n"
        f"policy_reorder_point  = math.ceil(mean_daily_demand * effective_lead_time + safety_stock_robust)\n"
        f"warnings              = []\n"
        f"if delivery_observations < 10:\n"
        f"    warnings.append('Thin lead-time evidence: fewer than 10 delivery observations.')\n"
        f"if supplier_reliability < 0.85:\n"
        f"    warnings.append(f'Low supplier reliability ({supplier_reliability:.4f}) may increase service risk.')\n"
        f"if slt_comparison_action == 'INCREASE':\n"
        f"    warnings.append(f'SLT increase recommended versus SAP baseline (current={current_sap_slt_days}, recommended={slt_days}).')\n"
        f"if current_safety_stock > 0 and policy_safety_stock > current_safety_stock:\n"
        f"    warnings.append('Recommended safety stock exceeds current ERP value (' + str(current_safety_stock) + ' -> ' + str(policy_safety_stock) + ').')\n"
        f"if milp_trigger is not None:\n"
        f"    warnings.append('Planner review required due to trigger ' + str(milp_trigger) + '.')\n"
        f"result = {{\n"
        f"  'material_id': material_id,\n"
        f"  'data_quality': {{\n"
        f"    'total_rows': total_rows,\n"
        f"    'working_days': working_days,\n"
        f"    'outliers_detected': outliers_detected,\n"
        f"    'winsorisation': {{'lower_bound': winsor_lower, 'upper_bound': winsor_upper}}\n"
        f"  }},\n"
        f"  'demand_analysis': {{\n"
        f"    'mean_daily_demand': round(mean_daily_demand, 4),\n"
        f"    'std_daily_demand': round(std_daily_demand, 4),\n"
        f"    'robust_std_daily': round(robust_std_daily, 4),\n"
        f"    'cv_wd': round(cv_wd, 4),\n"
        f"    'non_zero_fraction_wd': round(non_zero_fraction_wd, 4),\n"
        f"    'trend_detected': bool(trend_detected),\n"
        f"    'regime': regime,\n"
        f"    'distribution_type': distribution_type\n"
        f"  }},\n"
        f"  'lead_time_analysis': {{\n"
        f"    'mean_lead_time': round(mean_lead_time, 4),\n"
        f"    'std_lead_time': round(std_lead_time, 4),\n"
        f"    'cv_lead_time': round(cv_lead_time, 4),\n"
        f"    'stability': stability,\n"
        f"    'effective_lead_time': round(effective_lead_time, 4)\n"
        f"  }},\n"
        f"  'buffer_analysis': {{\n"
        f"    'sigma_ltd': round(sigma_ltd, 4),\n"
        f"    'safety_stock': round(safety_stock, 4),\n"
        f"    'safety_stock_robust': round(safety_stock_robust, 4)\n"
        f"  }},\n"
        f"  'order_quantity': {{\n"
        f"    'eoq_raw': round(eoq_raw, 4),\n"
        f"    'order_quantity': int(order_quantity)\n"
        f"  }},\n"
        f"  'cost_analysis': {{\n"
        f"    'unit_cost': round(unit_cost, 4),\n"
        f"    'ordering_cost': round(ordering_cost, 4),\n"
        f"    'holding_cost_rate': round(holding_cost_rate, 4),\n"
        f"    'annual_holding_cost_per_unit': round(annual_holding, 4)\n"
        f"  }},\n"
        f"  'policy': {{\n"
        f"    'safety_stock': int(policy_safety_stock),\n"
        f"    'reorder_point': int(policy_reorder_point),\n"
        f"    'order_quantity': int(order_quantity),\n"
        f"    'review_period_days': int(lot_size)\n"
        f"  }},\n"
        f"  'safety_lead_time': {{\n"
        f"    'recommended_days': round(slt_days, 4),\n"
        f"    'sigma_eff_days': round(slt_sigma_eff, 4),\n"
        f"    'dominant_factor': slt_dominant_factor,\n"
        f"    'dominant_pct': round(slt_dominant_pct, 4),\n"
        f"    'variance_components': {{\n"
        f"      'transport': round(slt_var_transport, 4),\n"
        f"      'supplier': round(slt_var_supplier, 4),\n"
        f"      'quality': round(slt_var_quality, 4)\n"
        f"    }},\n"
        f"    'disruption_premium': round(slt_disruption_premium, 4),\n"
        f"    'comparison_action': slt_comparison_action,\n"
        f"    'override_flag': slt_override_flag\n"
        f"  }},\n"
        f"  'milp_trigger': milp_trigger,\n"
        f"  'narrative': '',\n"
        f"  'warnings': warnings,\n"
        f"  'errors': [],\n"
        f"  'research_insights': {{\n"
        f"    'selected_model': '',\n"
        f"    'selection_rationale': '',\n"
        f"    'boundary_risk': '',\n"
        f"    'escalation_flag': 'YES' if milp_trigger is not None or warnings else 'NO'\n"
        f"  }}\n"
        f"}}\n"
        f"print(json.dumps(result, indent=2))\n"
        f"print(f'sigma_ltd={{sigma_ltd:.4f}}, SS={{safety_stock:.4f}},"
        f" SS_robust={{safety_stock_robust:.4f}}')\n"
        f"print(f'ROP={{mean_daily_demand * effective_lead_time + safety_stock_robust:.4f}},"
        f" EOQ={{eoq_raw:.4f}}, OQ={{order_quantity}}')\n"
        f"print(f'milp_trigger={{milp_trigger}}, regime={{regime}}, dist={{distribution_type}}')\n"
    )


def build_csv(material_id: str, rows: list[dict]) -> tuple[str, bytes]:
    file_name = f"{material_id}_data.csv"
    if not rows:
        return (file_name, b"")
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return (file_name, buf.getvalue().encode("utf-8"))


def flatten_response_json(artifact: dict) -> dict:
    policy   = artifact.get("policy", {})
    research = artifact.get("research_insights", {})
    demand   = artifact.get("demand_analysis", {})
    slt_out  = artifact.get("safety_lead_time", {})
    return {
        "material_id":          artifact.get("material_id"),
        "regime":               demand.get("regime"),
        "distribution_type":    demand.get("distribution_type"),
        "safety_stock":         policy.get("safety_stock"),
        "reorder_point":        policy.get("reorder_point"),
        "order_quantity":       policy.get("order_quantity"),
        "slt_recommended_days": slt_out.get("recommended_days"),
        "slt_comparison_action":slt_out.get("comparison_action"),
        "milp_trigger":         artifact.get("milp_trigger"),
        "selected_model":       research.get("selected_model"),
        "selection_rationale":  research.get("selection_rationale"),
        "boundary_risk":        research.get("boundary_risk"),
        "escalation_flag":      research.get("escalation_flag"),
        "narrative":            artifact.get("narrative"),
        "warnings":             artifact.get("warnings", []),
        "errors":               artifact.get("errors", []),
    }

def process_material(
    material_id: str,
    stats: dict,
    policy_values: dict,
    slt: dict,
    api_key: str,
    bearer: str,
) -> dict:
    try:
        prompt = build_prompt(stats, policy_values, slt)
        response_text = llm_chat(prompt, api_key=api_key)
        artifact = json.loads(response_text)
        output_dir = _output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        with open(output_dir / f"{material_id}.json", "w", encoding="utf-8") as fh:
            json.dump(artifact, fh, indent=2)
        return flatten_response_json(artifact)
    except Exception as exc:
        print(f"ERROR process_material [{material_id}]: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    api_key, _ = validate_credentials()
    print(f"Credentials loaded. OPENAI_API_KEY set, model={os.environ.get('LLM_MODEL', 'gpt-4o')}")
