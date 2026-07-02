# AI Assistant Instructions

## Implementation
- Use `ensemble_runner.py` for bulk execution.
- Use `llm_api_client.py` for single-material LLM calls.
- Use deterministic math in `model_solvers.py`.

## Testing
- Run `python -m inventor_tests.orchestration.run_ensemble_test --count 3 --periods 36` for a small smoke test.
- Use `pytest inventor_tests/ -v` for unit tests.

## Environment
- API credentials: `LLM_API_URL`, `LLM_API_KEY`, `LLM_APP_ID` env vars or `.env` file.
- Public artifacts land under `results/`.
