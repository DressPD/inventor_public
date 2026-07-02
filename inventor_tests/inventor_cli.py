# Thin re-export shim. Edit inventor_tests/orchestration/inventor_cli.py, not here.
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from inventor_tests.orchestration.inventor_cli import *  # noqa: F401,F403

if __name__ == "__main__":
    from inventor_tests.orchestration.inventor_cli import main

    main()
