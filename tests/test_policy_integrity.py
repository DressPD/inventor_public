"""Synthetic historical-parser and cross-call comparator regressions."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inventory_llm import core, policy_backtest as backtest


class PolicyIntegrityTest(unittest.TestCase):
    def setUp(self):
        backtest._POLICY_CACHE.clear()
        self.addCleanup(backtest._POLICY_CACHE.clear)

    def rows(self, training="2", validation="3"):
        return [{"date": date, "actual_demand": demand, "is_working_day": "1",
                 "delivery_time": "1", "unit_cost": "1", "minimum_order_quantity": "1"}
                for date, demand in (("2026-03-01", training), ("2026-03-10", validation))]

    def artifact(self, rop=10):
        return {"recommended_policy": {"reorder_point": rop, "order_quantity": "20.4", "safety_stock": "2"}}

    def test_nonfinite_scalars_rejected_with_legacy_coercions_preserved(self):
        for scalar in (float("inf"), float("-inf"), "1e999", "NaN"):
            with self.subTest(scalar=scalar):
                self.assertIsNone(backtest.parse_policy_artifact(self.artifact(scalar), {"moq": 1}))
        self.assertEqual(backtest.parse_policy_artifact(self.artifact("10.4"), {"moq": 1})["rop"], 10)

    def test_invalid_item_does_not_abort_other_materials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for item, rop in (("bad", "1e999"), ("good", 10)):
                (root / item).mkdir()
                (root / item / "output.json").write_text(json.dumps(self.artifact(rop)))
            with patch.object(backtest, "RUNS_DIR", root), \
                    patch.object(backtest, "_load_targets", return_value=["bad", "good"]), \
                    patch.object(core, "load_grouped_rows", return_value={key: self.rows() for key in ("bad", "good")}):
                result = backtest.build_backtest()
            self.assertEqual(result["invalid_outputs"], ["bad"])
            self.assertEqual(result["n_backtested"], 1)

    def test_all_trained_comparators_follow_training_content_not_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "same").mkdir()
            (root / "same" / "output.json").write_text(json.dumps(self.artifact()))
            with patch.object(backtest, "RUNS_DIR", root), \
                    patch.object(backtest, "_load_targets", return_value=["same"]), \
                    patch.object(core, "load_grouped_rows") as load, \
                    patch.object(core, "make_sba_rq_policy", wraps=core.make_sba_rq_policy) as sba, \
                    patch.object(core, "make_empirical_rq_policy", wraps=core.make_empirical_rq_policy) as empirical, \
                    patch.object(core, "make_tuned_rq_policy", wraps=core.make_tuned_rq_policy) as tuned:
                for train, test, calls in (("2", "3", 1), ("2", "7", 1), ("8", "7", 2)):
                    load.return_value = {"same": self.rows(train, test)}
                    result = backtest.build_backtest()
                    self.assertEqual(result["n_backtested"], 1)
                    for builder in (sba, empirical, tuned):
                        self.assertEqual(builder.call_count, calls)
                # Stats also participate, even if supplied independently of rows.
                stats = core.compute_stats(self.rows()[:1])
                with patch.object(core, "compute_stats", return_value=stats):
                    backtest.build_backtest()
                for builder in (sba, empirical, tuned):
                    self.assertEqual(builder.call_count, 3)
