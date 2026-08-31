from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from inventory_llm.synthetic_demo import generate_synthetic_csv, publish_fixture, run_demo


class SyntheticDemoTest(unittest.TestCase):
    def test_generation_is_seeded_and_full_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.csv"
            second = root / "second.csv"
            different = root / "different.csv"
            generate_synthetic_csv(first, 123)
            generate_synthetic_csv(second, 123)
            generate_synthetic_csv(different, 124)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertNotEqual(first.read_bytes(), different.read_bytes())
            self.assertEqual(len(first.read_text(encoding="utf-8").splitlines()), 454)
            self.assertEqual(len(first.read_text(encoding="utf-8").splitlines()[0].split(";")), 24)

    def test_offline_demo_scores_all_synthetic_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = publish_fixture(root)
            result = run_demo(root)
            self.assertEqual(summary["n_targets"], 3)
            self.assertEqual(summary["n_backtested"], 3)
            self.assertEqual(result["n_backtested"], 3)
            self.assertEqual(result["calendar_repair"]["calendar_repaired_plants"], ["SYN_C"])
            self.assertTrue((root / "outputs/synthetic_demo/backtest.json").is_file())
            published = json.loads((root / "outputs/synthetic_demo_summary.json").read_text())
            self.assertNotIn("results", published)
            self.assertNotIn("artifacts", published)


if __name__ == "__main__":
    unittest.main()
