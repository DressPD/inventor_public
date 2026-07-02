from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT.parent / "results"
INTERNAL_DIR = ROOT.parent / "sample_artifacts"
CSV_PATH = ROOT / "data" / "20260619_400_Mat_2_plants.csv"
ROUTE_CACHE_DIR = ROOT / "batches" / "backtest_routes"
TARGETS_CSV = INTERNAL_DIR / "target_ranking.csv"
REVIEW_OUTPUT_DIR = ROOT.parent / "outputs" / "review_flags"


def cmd_summary(_: argparse.Namespace) -> None:
    summary = {
        "paper_backtest_json": str(RESULTS_DIR / "aggregate_backtest.json"),
        "target_ranking_csv": str(INTERNAL_DIR / "target_ranking.csv"),
        "material_flags_csv": str(INTERNAL_DIR / "material_flags.csv"),
        "material_flags_jsonl": str(INTERNAL_DIR / "material_flags.jsonl"),
        "flagging_baselines_csv": str(RESULTS_DIR / "baseline_metrics.csv"),
        "targeted_evaluation_csv": str(RESULTS_DIR / "targeted_evaluation.csv"),
        "workflow_overview_md": str(RESULTS_DIR / "workflow_overview.md"),
        "backtest_appendix_md": str(RESULTS_DIR / "backtest_appendix.md"),
    }
    print(json.dumps(summary, indent=2))


def cmd_paper_backtest(args: argparse.Namespace) -> None:
    output = Path(args.output or str(RESULTS_DIR / "aggregate_backtest.json"))
    if args.mode == "replay":
        from inventor_tests.deterministic_method.paper_grade_summary import build_paper_grade_summary

        result = build_paper_grade_summary(TARGETS_CSV, RESULTS_DIR / "aggregate_backtest.json", output)
        print(f"\nReplayed: {result['items_evaluated']} items | Skipped: {result['items_skipped']}")
        print("Policy source: paper_grade_replay")
        for name in result["policies"]:
            ag = result["aggregate"].get(name, {})
            print(
                f"  {name:22s}: fill={ag.get('mean_fill_rate_pct', 0):7.3f}%  "
                f"cost={ag.get('mean_total_cost', 0):12.0f}  "
                f"stockout_days={ag.get('mean_stockout_days', 0):.2f}"
            )
        print(f"\nOutput: {output}")
        return

    from inventor_tests.deterministic_method.backtest_simulator import (
        load_cached_route_payloads,
        load_grouped_rows,
        load_targets_policies,
        run_backtest,
    )

    grouped = load_grouped_rows(CSV_PATH)

    route_payloads: dict = {}
    targets_policies: dict = {}
    selected_item_keys: set[str] | None = None
    if args.route_source == "targets_csv":
        targets_policies = load_targets_policies(TARGETS_CSV)
        if not targets_policies:
            raise SystemExit(f"No target policies found in {TARGETS_CSV}")
        selected_item_keys = set(targets_policies)
        print(f"  Loaded {len(targets_policies)} paper-grade policies from targets CSV")
    elif args.route_source == "route_cache":
        route_payloads = load_cached_route_payloads(ROUTE_CACHE_DIR, args.train_cutoff)
        print(f"  Loaded {len(route_payloads)} cached routes")
    else:
        print("  Using fallback (r,Q) policy for all items")

    result = run_backtest(
        grouped, args.train_cutoff, args.valid_end,
        route_payloads=route_payloads,
        targets_policies=targets_policies,
        selected_item_keys=selected_item_keys,
    )
    result["csv_path"] = str(CSV_PATH)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"\nEvaluated: {result['items_evaluated']} items | Skipped: {result['items_skipped']}")
    print(f"Policy source: {result['route_source']}")
    for name in result["policies"]:
        ag = result["aggregate"].get(name, {})
        print(
            f"  {name:22s}: fill={ag.get('mean_fill_rate_pct', 0):7.3f}%  "
            f"cost={ag.get('mean_total_cost', 0):12.0f}  "
            f"stockout_days={ag.get('mean_stockout_days', 0):.2f}"
        )
    print(f"\nOutput: {output}")


def cmd_rank_targets(args: argparse.Namespace) -> None:
    from inventor_tests.deterministic_method.export_optimization_targets import export_material_targets

    output = args.output or str(TARGETS_CSV)
    print(json.dumps(export_material_targets(output), indent=2))


def cmd_decision_card(args: argparse.Namespace) -> None:
    from inventor_tests.flagging_method.constraint_decision_card_test import load_csv, run_decision_card_test
    from inventor_tests.orchestration.llm_api_client import validate_credentials

    api_key, bearer = validate_credentials()
    output_dir = Path(args.output_dir or str(ROOT / "batches" / "decision_card_tests"))
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped = load_csv(str(CSV_PATH), "plant-material")
    if args.item not in grouped:
        raise SystemExit(f"Item not found: {args.item}")
    result = run_decision_card_test(args.item, grouped[args.item], api_key, bearer)
    (output_dir / f"{args.item}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"item_key": args.item, "status": result["status"]}, indent=2))


def cmd_material_flags(args: argparse.Namespace) -> None:
    from inventor_tests.flagging_method.export_material_flags import export_material_flags

    output_csv = Path(args.output_csv or str(INTERNAL_DIR / "material_flags.csv"))
    output_jsonl = Path(args.output_jsonl or str(INTERNAL_DIR / "material_flags.jsonl"))
    res = export_material_flags(Path(args.input), output_csv, output_jsonl)
    print(json.dumps(res, indent=2))


def cmd_review_flags(args: argparse.Namespace) -> None:
    from inventor_tests.flagging_method.review_material_flags import export_reviews
    from inventor_tests.orchestration.llm_api_client import validate_credentials

    output_csv = Path(args.output_csv or str(REVIEW_OUTPUT_DIR / "reviewed_flags.csv"))
    output_jsonl = Path(args.output_jsonl or str(REVIEW_OUTPUT_DIR / "reviewed_flags.jsonl"))
    api_key, bearer = validate_credentials()
    summary = export_reviews(
        Path(args.input_jsonl), output_jsonl, output_csv, api_key, bearer, args.limit,
        None,
        args.n_runs,
        args.max_workers,
    )
    print(json.dumps(summary, indent=2))


def cmd_baseline_flags(args: argparse.Namespace) -> None:
    from inventor_tests.flagging_method.baseline_flagging_models import run_baselines

    output_json = Path(args.output_json or str(INTERNAL_DIR / "baseline_metrics.json"))
    output_csv = Path(args.output_csv or str(RESULTS_DIR / "baseline_metrics.csv"))
    summary = run_baselines(Path(args.targets_csv), Path(args.flags_csv), output_json, output_csv)
    print(json.dumps(summary, indent=2))


def cmd_evaluate_targeting(args: argparse.Namespace) -> None:
    from inventor_tests.flagging_method.evaluate_targeted_improvement import evaluate_targeted_improvement

    output_json = Path(args.output_json or str(INTERNAL_DIR / "targeted_evaluation.json"))
    output_csv = Path(args.output_csv or str(RESULTS_DIR / "targeted_evaluation.csv"))
    summary = evaluate_targeted_improvement(
        Path(args.targets_csv), Path(args.flags_csv), Path(args.reviewed_csv), output_json, output_csv,
    )
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="InventOR consolidated human-facing CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("summary", help="Show core artifact paths")
    s.set_defaults(func=cmd_summary)

    b = sub.add_parser("paper-backtest", help="Replay paper-grade artifact or run simulator")
    b.add_argument("--mode", choices=["replay", "simulate"], default="replay")
    b.add_argument("--train-cutoff", default="2026-03-10")
    b.add_argument("--valid-end", default="2026-06-19")
    b.add_argument("--route-source", choices=["targets_csv", "route_cache", "fallback_rq"], default="targets_csv")
    b.add_argument("--output")
    b.set_defaults(func=cmd_paper_backtest)

    r = sub.add_parser("rank-targets", help="Summarize current optimization target ranking")
    r.add_argument("--output", help="Existing target-ranking CSV to summarize")
    r.set_defaults(func=cmd_rank_targets)

    d = sub.add_parser("decision-card", help="Run experimental LLM decision-card test")
    d.add_argument("--item", required=True)
    d.add_argument("--output-dir")
    d.set_defaults(func=cmd_decision_card)

    f = sub.add_parser("material-flags", help="Export material-flag queue for LLM review")
    f.add_argument("--input", default=str(INTERNAL_DIR / "target_ranking.csv"))
    f.add_argument("--output-csv")
    f.add_argument("--output-jsonl")
    f.set_defaults(func=cmd_material_flags)

    rv = sub.add_parser("review-flags", help="Run LLM/fallback review over material flag queue")
    rv.add_argument("--input-jsonl", default=str(INTERNAL_DIR / "material_flags.jsonl"))
    rv.add_argument("--output-csv")
    rv.add_argument("--output-jsonl")
    rv.add_argument("--limit", type=int)
    rv.add_argument("--n-runs", type=int, default=5)
    rv.add_argument("--max-workers", type=int, default=5)
    rv.set_defaults(func=cmd_review_flags)

    bl = sub.add_parser("baseline-flags", help="Compare deterministic flagging with simple ML baselines")
    bl.add_argument("--targets-csv", default=str(INTERNAL_DIR / "target_ranking.csv"))
    bl.add_argument("--flags-csv", default=str(INTERNAL_DIR / "material_flags.csv"))
    bl.add_argument("--output-json")
    bl.add_argument("--output-csv")
    bl.set_defaults(func=cmd_baseline_flags)

    ti = sub.add_parser("evaluate-targeting", help="Evaluate targeted optimization strategies versus SAP")
    ti.add_argument("--targets-csv", default=str(INTERNAL_DIR / "target_ranking.csv"))
    ti.add_argument("--flags-csv", default=str(INTERNAL_DIR / "material_flags.csv"))
    ti.add_argument("--reviewed-csv", default=str(INTERNAL_DIR / "reviewed_flags.csv"))
    ti.add_argument("--output-json")
    ti.add_argument("--output-csv")
    ti.set_defaults(func=cmd_evaluate_targeting)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
