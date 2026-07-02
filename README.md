# InventOR

Governed OR + LLM workflow for single-item inventory decisions.
Public reproduction repository for the InventOR workflow. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository. This repository is generated from the sanitized `public` branch of the private source repository.

**Code:** [github.com/DressPD/inventor_public](https://github.com/DressPD/inventor_public)

## Reproducing The Backtest

### Prerequisites

```bash
pip install -r requirements.txt
```

### LLM Endpoint Configuration

The methodology is provider-agnostic. Uses the `openai` Python SDK.
Set these environment variables (or create a `.env` file):

| Variable | Purpose | Example |
|----------|---------|---------|
| `OPENAI_API_KEY` | API key | `sk-proj-...` or `ollama` (local) |
| `OPENAI_BASE_URL` | API base URL | `https://api.openai.com/v1` or `http://localhost:11434/v1` |
| `LLM_MODEL` | Model name (default: `gpt-4o`) | `gpt-4o` or `llama3` |

**Local setup (Ollama):**
```bash
# Install Ollama: https://ollama.com
ollama pull llama3
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
export LLM_MODEL=llama3
```

**OpenAI:**
```bash
export OPENAI_API_KEY=sk-proj-...
export LLM_MODEL=gpt-4o
```

> Without a configured endpoint, LLM-dependent steps (constraint review,
> decision cards, ensemble review) will fall back to deterministic rules.

### Running the Full Pipeline

```bash
# Summary statistics and data overview
python3 inventor_tests/inventor_cli.py summary

# Replay the frozen paper artifact from bundled masked inputs
python3 inventor_tests/inventor_cli.py paper-backtest

# Optional raw simulator rerun without overwriting paper artifacts
python3 inventor_tests/inventor_cli.py paper-backtest --mode simulate --output /tmp/inventor_backtest.json

# Rank optimization targets
python3 inventor_tests/inventor_cli.py rank-targets

# Export material flag queue
python3 inventor_tests/inventor_cli.py material-flags

# Review flag queue with LLM (requires configured endpoint)
python3 inventor_tests/inventor_cli.py review-flags --limit 10

# Evaluate targeting strategies from bundled masked inputs
python3 inventor_tests/inventor_cli.py evaluate-targeting
```

### Running Without an LLM

Deterministic steps (statistics, backtest, flag export, targeting evaluation)
run without any LLM dependency. Only `review-flags`, `decision-card`, and
the ensemble stages in `orchestration/` require a configured endpoint.

## Repository Structure

```
inventor_tests/
├── inventor_cli.py           # CLI entry point
├── deterministic_method/     # Statistics, solvers, backtest, hard flags
├── flagging_method/          # Material flags, constraint review, targeting
├── orchestration/            # Ensemble runner, LLM client, aggregator
└── prompts/                  # System and tool prompt templates
sample_artifacts/
├── target_ranking.csv        # masked per-item target ranking
├── material_flags.csv        # masked deterministic flag queue
├── material_flags.jsonl      # masked LLM-review input queue
└── reviewed_flags.csv        # masked reviewed flag queue
results/
├── aggregate_backtest.json
├── baseline_metrics.csv
├── targeted_evaluation.csv
├── workflow_overview.md
└── backtest_appendix.md
run_sensitivity.py            # shortage-penalty sensitivity sweep -> outputs/sensitivity/summary.csv
```

## Important Notes

- Plant and material identifiers are masked in public inputs and outputs.
- Raw proprietary identifiers and source records are not included.
- `paper-backtest` defaults to replay mode and reproduces the frozen paper artifact; raw simulator reruns require `--mode simulate`.
- The `.env` file and credential patterns are templates — never commit real tokens.
