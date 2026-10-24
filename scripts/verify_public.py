"""Verify release hashes and optionally reproduce masked evidence without credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(root: Path, recompute: bool = False) -> None:
    manifest = json.loads((root / "PUBLIC_MANIFEST.json").read_text())["files"]
    bad = []
    for name, expected in manifest.items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            bad.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            bad.append(name)
    if bad:
        raise SystemExit("Release integrity failed: " + ", ".join(bad))
    if recompute:
        for script in ("build_masked_replication_evidence.py", "build_six_run_report.py"):
            subprocess.run([sys.executable, str(root / "scripts" / script)], cwd=root, check=True)
        for name in ("outputs/masked_replication_evidence.json", "outputs/six_run_evidence.json",
                     "manuscript/Six_Run_Table.tex", "manuscript/Figure_2_Cost_Decomposition.tex",
                     "manuscript/Figure_3_Segments.tex",
                     "manuscript/Figure_S1_Three_Run_Reproducibility.tex"):
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != manifest[name]:
                raise SystemExit("Numerical replay differs: " + name)
    print(f"Verified {len(manifest)} release files; numerical replay={recompute}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recompute", action="store_true")
    verify(ROOT, parser.parse_args().recompute)
