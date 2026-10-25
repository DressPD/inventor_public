"""Verify release hashes and optionally reproduce masked evidence without credentials."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(root: Path, recompute: bool = False, *, strict: bool = False) -> None:
    root = root.resolve()
    try:
        document = json.loads((root / "PUBLIC_MANIFEST.json").read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit("Release integrity failed: unreadable manifest") from exc
    if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1 or not isinstance(document.get("files"), dict)
            or not document["files"]):
        raise SystemExit("Release integrity failed: invalid or empty manifest schema")
    manifest = document["files"]
    bad = []
    for name, expected in manifest.items():
        if (not name or "\\" in name or PurePosixPath(name).is_absolute()
                or any(part in {"", ".", ".."} for part in name.split("/"))
                or name == "PUBLIC_MANIFEST.json" or name.split("/")[0] == ".git"
                or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
            bad.append(name)
            continue
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            bad.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            bad.append(name)
    if strict:
        # Only local Git administration is outside a clean snapshot inventory.
        # Normal mode allows generated demo/cache files; strict mode does not.
        for path in root.rglob("*"):
            rel = path.relative_to(root)
            if path.is_symlink():
                bad.append(str(rel))
            elif rel.parts[0] != ".git" and path.is_file() and str(rel) not in manifest and str(rel) != "PUBLIC_MANIFEST.json":
                bad.append(str(rel))
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
    parser.add_argument("--strict", action="store_true", help="Reject unlisted files and symlinks (except local .git administration)")
    args = parser.parse_args()
    verify(ROOT, args.recompute, strict=args.strict)
