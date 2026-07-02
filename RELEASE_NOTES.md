# Release Notes

This is the cleaned public snapshot of the InventOR workflow.

## Purpose

This repository now keeps only the public reproduction subset of the final two-plant InventOR work:
- deterministic OR diagnostics and backtest
- deterministic material targeting and flagging
- LLM review layer for flagged materials
- generic aggregate evaluation artifacts
- masked deterministic inputs needed for public smoke runs

Old one-plant data, smoke outputs, token-check artifacts, and deprecated legacy wrappers are out of the final publish set.

## Active Code

### Deterministic layer
- `inventor_tests/deterministic_method/stats_calculator.py`
- `inventor_tests/deterministic_method/slt_calculator.py`
- `inventor_tests/deterministic_method/hard_flag.py`
- `inventor_tests/deterministic_method/model_solvers.py`
- `inventor_tests/deterministic_method/backtest_simulator.py`
- `inventor_tests/deterministic_method/export_optimization_targets.py`
- `run_sensitivity.py`

### LLM-facing layer
- `inventor_tests/flagging_method/export_material_flags.py`
- `inventor_tests/flagging_method/review_material_flags.py`
- `inventor_tests/flagging_method/baseline_flagging_models.py`
- `inventor_tests/flagging_method/evaluate_targeted_improvement.py`
- `inventor_tests/flagging_method/constraint_decision_card_test.py`
- `inventor_tests/flagging_method/llm_flagging_prompt.md`

### Shared active modules
- `inventor_tests/_utils.py`
- `inventor_tests/orchestration/llm_api_client.py`
- `inventor_tests/orchestration/ensemble_runner.py`
- `inventor_tests/orchestration/ensemble_aggregator.py`
- `inventor_tests/orchestration/run_ensemble_test.py`
- `inventor_tests/orchestration/inventor_cli.py`
- `inventor_tests/prompts/system_prompt.txt`
- `inventor_tests/prompts/tool_prompt.txt`

## Final Public Outputs

- `results/aggregate_backtest.json`
- `results/baseline_metrics.csv`
- `results/targeted_evaluation.csv`
- `results/workflow_overview.md`
- `results/backtest_appendix.md`

Record-level proprietary material outputs and manuscript sources are intentionally excluded from the public snapshot. Masked target and flag inputs are included under `sample_artifacts/` so deterministic public commands can run without private identifiers.

## Removed In Final Cleanup

- old 100-material source CSV
- buffer recommendation CSV
- smoke review artifacts
- reviewed LLM fallback artifacts with transport errors
- token-check review artifacts
- deprecated legacy wrappers
- legacy folder contents
- deprecated robust solver wrapper

## Main Commands

```bash
python3 inventor_tests/inventor_cli.py summary
python3 inventor_tests/inventor_cli.py paper-backtest
python3 inventor_tests/inventor_cli.py paper-backtest --mode simulate --output /tmp/inventor_backtest.json
python3 inventor_tests/inventor_cli.py rank-targets
python3 inventor_tests/inventor_cli.py material-flags
python3 inventor_tests/inventor_cli.py review-flags --limit 5
python3 inventor_tests/inventor_cli.py baseline-flags
python3 inventor_tests/inventor_cli.py evaluate-targeting
```
