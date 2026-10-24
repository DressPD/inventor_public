"""Aggregate reporting must compare the same feasible pairs in all six runs."""
import unittest

from scripts.build_six_run_report import ARMS, RUNS, summarize


def record(cost=100.0, fill=98.0):
    metrics = dict(total_cost=cost, holding_cost=cost * .6,
                   ordering_cost=cost * .4, fill_rate_pct=fill,
                   shortage_units=2.0, total_demand=100.0)
    return {arm: dict(metrics) for arm in ["llm_pure", *ARMS]}


class SixRunReportTest(unittest.TestCase):
    def test_uses_intersection_and_preserves_run_order(self):
        runs = {r: {"by_key": {"PL1__x": record(), "PL2__y": record(200)}}
                for r in RUNS}
        del runs["run-m1"]["by_key"]["PL2__y"]
        evidence = summarize(runs, {"PL1__x": 10, "PL2__y": 20})
        self.assertEqual(evidence["n_common"], 1)
        self.assertEqual(list(evidence["runs"]), RUNS)
        for row in evidence["runs"].values():
            self.assertEqual(row["groups"]["ALL"]["n"], 1)
            self.assertEqual(row["groups"]["ALL"]["arms"]["llm_pure"]["mean_cost"], 100)
            self.assertEqual(row["groups"]["ALL"]["arms"]["llm_pure"]["shortage_exposure"], 20)
        self.assertNotIn("PL2__y", str(evidence))

    def test_missing_comparator_excludes_pair_from_every_run(self):
        runs = {r: {"by_key": {"PL1__x": record(), "PL2__y": record()}}
                for r in RUNS}
        del runs["mf-02"]["by_key"]["PL2__y"]["or_sba"]
        self.assertEqual(summarize(runs, {"PL1__x": 1})["n_common"], 1)

    def test_empty_cohort_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "common"):
            summarize({r: {"by_key": {}} for r in RUNS}, {})


if __name__ == "__main__":
    unittest.main()
