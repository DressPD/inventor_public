"""Record a runner-code hash change for already finished materials.

The resume check in inventory_llm/runner.py compares `runner_code_sha256` in each
material's run_metadata.json with the hash of the current runner.py, so any edit to
runner.py makes finished outputs look stale. This script updates the stored hash only
for records whose other provenance fields (schema, cutoff, system prompt hash,
application version, model identifier, generation settings) still match the current
configuration, and keeps the audit trail: the previous hash is appended to
`runner_hash_history` together with the reason and the date.

Usage (dry run by default):
  python3 scripts/amend_runner_hash.py run-m1 [run-m2 ...] --reason "auth handling only" [--apply]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "inventory_llm" / "runner.py"
SYSTEM_PROMPT = ROOT / "prompts" / "system_prompt.txt"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--reason", required=True, help="why runner.py changed (must not touch prompt, data or call logic)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    runner_hash = sha256(RUNNER)
    prompt_hash = sha256(SYSTEM_PROMPT)
    env = {
        "application_version": os.environ.get("INVENTOR_APPLICATION_VERSION"),
        "model_runtime_identifier": os.environ.get("INVENTOR_MODEL_RUNTIME_IDENTIFIER"),
        "inference_generation_settings": os.environ.get("INVENTOR_GENERATION_SETTINGS_JSON"),
    }
    today = datetime.date.today().isoformat()
    total = {"current": 0, "amended": 0, "skipped": 0}
    for run in a.runs:
        for f in sorted((ROOT / "outputs" / "runs" / run / "agentic_runs").glob("*/run_metadata.json")):
            m = json.loads(f.read_text(encoding="utf-8"))
            if m.get("runner_code_sha256") == runner_hash:
                total["current"] += 1
                continue
            ok = (
                m.get("schema_version") == 2
                and m.get("system_prompt_sha256") == prompt_hash
                and all(m.get(k) == v for k, v in env.items())
            )
            if not ok:
                total["skipped"] += 1
                print("SKIP (other provenance fields differ):", f.parent.name)
                continue
            if a.apply:
                m.setdefault("runner_hash_history", []).append(
                    {"previous_runner_code_sha256": m.get("runner_code_sha256"), "updated_on": today, "reason": a.reason}
                )
                m["runner_code_sha256"] = runner_hash
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(m, indent=2), encoding="utf-8")
                tmp.replace(f)
            total["amended"] += 1
    print(("APPLIED" if a.apply else "DRY RUN"), total, "runner", runner_hash[:12])
    return 0


if __name__ == "__main__":
    sys.exit(main())
