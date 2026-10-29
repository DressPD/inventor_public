"""Independent finite-state checks, not empirical or real-world safety evidence."""
from datetime import date, timedelta
from fractions import Fraction
from itertools import product
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from inventory_llm import robustness as rb
from scripts import build_secondary_admission as secondary


def rows(demands):
    return [dict(date=(date(2026, 3, 11) + timedelta(days=i)).isoformat(),
                 actual_demand=float(d), is_working_day=1) for i, d in enumerate(demands)]


def oracle(demands, opening, capacity, moq, rop, oq, lead, *, out_to=None, calendar=None):
    """Exact rational state transitions; enumerate admissible integer orders."""
    stock, pipeline = Fraction(opening), []
    shortage, inventory_sum, orders, peak, deferrals = Fraction(0), Fraction(0), 0, stock, 0
    on_hand_peak, capacity_days = stock, 0
    working = [d for d, flag in zip(demands, calendar or [1] * len(demands)) if flag]
    for day, demand in enumerate(working):
        stock += sum(q for due, q in pipeline if due == day)
        pipeline = [(due, q) for due, q in pipeline if due != day]
        on_hand_peak = max(on_hand_peak, stock)
        capacity_days += int(bool(capacity) and stock > capacity)
        unmet = max(Fraction(demand) - stock, 0)
        stock = max(stock - Fraction(demand), 0)
        shortage += unmet
        position = stock + sum(q for _, q in pipeline)
        if position <= rop:
            proposed = oq if out_to is None else Fraction(out_to) - position
            admissible = [q for q in range(1, max(oq, out_to or 0) + 1)
                          if q <= proposed and (not capacity or position + q <= capacity)]
            quantity = max(admissible, default=0)
            if quantity >= moq:
                pipeline.append((day + lead, quantity))
                orders += 1
            else:
                deferrals += 1
        peak = max(peak, stock + sum(q for _, q in pipeline))
        inventory_sum += stock
    return dict(shortage_units=float(shortage), num_orders=orders, moq_deferrals=deferrals,
                physical_post_order_peak_position=float(peak), avg_inventory=float(inventory_sum / len(working)),
                peak_on_hand=float(on_hand_peak), days_over_capacity=capacity_days, test_days=len(working))


class SecondaryAdmissionTests(unittest.TestCase):
    def test_reviewer_support_is_manifested_anonymous_and_contains_replay_inputs(self):
        import hashlib
        import json
        import zipfile
        try:
            from scripts import build_submission_packages as package
        except ImportError:
            root = Path(__file__).resolve().parents[1]
            secondary.verify_support_manifest(root)
            for name in ('data/masked_release/masked_inventory_panel.csv', 'docs/secondary_admission.md',
                         'outputs/secondary_admission/evidence.json'):
                self.assertTrue((root / name).is_file())
            return
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / 'support.zip'
            package.build_secondary_support(archive)
            package.validate_anonymous(archive)
            with zipfile.ZipFile(archive) as z:
                manifest = json.loads(z.read('SUPPORT_MANIFEST.json'))
                self.assertEqual(set(z.namelist()) - {'SUPPORT_MANIFEST.json'}, set(manifest))
                for name, digest in manifest.items():
                    self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)
                self.assertIn('data/masked_release/masked_inventory_panel.csv', manifest)
                self.assertIn('docs/secondary_admission.md', manifest)
                self.assertIn('outputs/secondary_admission/evidence.json', manifest)
                self.assertNotIn('scripts/build_offline_robustness.py', manifest)

    def test_support_manifest_rejects_tampering_and_incomplete_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'input').write_bytes(b'frozen')
            manifest = {'input': hashlib.sha256(b'frozen').hexdigest()}
            (root / 'SUPPORT_MANIFEST.json').write_text(json.dumps(manifest))
            secondary.verify_support_manifest(root)
            for name, data in (('input', b'tampered'), ('unlisted', b'extra')):
                with self.subTest(name=name):
                    (root / name).write_bytes(data)
                    with self.assertRaisesRegex(ValueError, 'support manifest'):
                        secondary.verify_support_manifest(root)
                    if name == 'input':
                        (root / name).write_bytes(b'frozen')
                    else:
                        (root / name).unlink()
            (root / 'input').unlink()
            with self.assertRaisesRegex(ValueError, 'support manifest'):
                secondary.verify_support_manifest(root)

    def test_secondary_support_replays_in_isolation(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            scratch = Path(tmp).resolve()
            tree = scratch / 'extracted'
            try:
                from scripts import build_submission_packages as package
            except ImportError:
                secondary.verify_support_manifest(root)
                names = set(secondary.strict_json((root / 'outputs/secondary_admission/evidence.json').read_bytes())['input_sha256'])
                names.update(('inventory_llm/__init__.py', 'inventory_llm/core.py',
                              'inventory_llm/policy_backtest.py', 'inventory_llm/robustness.py',
                              'scripts/build_secondary_admission.py', 'scripts/build_six_run_report.py',
                              'tests/test_secondary_admission.py', 'docs/secondary_admission.md',
                              'outputs/secondary_admission/evidence.json', 'outputs/secondary_admission/report.md'))
                manifest = {}
                for name in names:
                    target = tree / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(root / name, target)
                    manifest[name] = hashlib.sha256(target.read_bytes()).hexdigest()
                (tree / 'SUPPORT_MANIFEST.json').write_text(json.dumps(manifest))
            else:
                archive = scratch / 'support.zip'
                package.build_secondary_support(archive)
                with zipfile.ZipFile(archive) as z:
                    z.extractall(tree)
            manifest_path = tree / 'SUPPORT_MANIFEST.json'
            original_manifest = manifest_path.read_bytes()

            def run(destination):
                return subprocess.run([sys.executable, '-I', '-B', '-S',
                    str(tree / 'scripts/build_secondary_admission.py'), '--dest', str(destination)],
                    cwd=tree, env={'PATH': os.defpath}, capture_output=True, timeout=180)

            destination = scratch / 'external-results'
            self.assertFalse(destination.exists())
            result = run(destination)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            for name in ('evidence.json', 'report.md'):
                self.assertEqual((destination / name).read_bytes(),
                                 (root / 'outputs/secondary_admission' / name).read_bytes())
            manifest = secondary.strict_json(original_manifest)
            policy = next(name for name in manifest if name.startswith('outputs/runs/'))
            manifest[policy] = '0' * 64
            manifest_path.write_text(json.dumps(manifest))
            for failure in ('corrupt_manifest', 'missing_policy'):
                if failure == 'missing_policy':
                    manifest_path.write_bytes(original_manifest)
                    (tree / policy).unlink()
                failed_dest = scratch / failure
                result = run(failed_dest)
                self.assertNotEqual(result.returncode, 0, failure)
                self.assertIn(b'support manifest', result.stderr)
                self.assertFalse(failed_dest.exists())

    def test_output_namespace_escape_rejected_before_input_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'project'
            root.mkdir()
            escape = root / 'outputs/secondary_admission/../../prompts/new'
            with patch.object(secondary, 'ROOT', root), patch.object(Path, 'read_bytes') as read:
                with self.assertRaisesRegex(ValueError, 'protected project paths'):
                    secondary.build(escape)
                read.assert_not_called()
            link = root / 'link'
            link.symlink_to(root, target_is_directory=True)
            with patch.object(secondary, 'ROOT', root), patch.object(Path, 'read_bytes') as read:
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    secondary.build(link / '../new')
                read.assert_not_called()

    def test_empty_masked_panel_rejects_before_default_source_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / 'project'
            path = root / 'data/masked_release/masked_inventory_panel.csv'
            path.parent.mkdir(parents=True)
            path.write_text('plant_code;material;mat_description\n')
            with patch.object(secondary, 'ROOT', root), patch.object(secondary.core, 'load_grouped_rows', return_value={}) as load, \
                 patch.object(secondary.core, 'eligible_item_keys') as eligible:
                with self.assertRaisesRegex(ValueError, 'empty masked panel'):
                    secondary.build(root.parent / 'results')
                eligible.assert_not_called()
                self.assertEqual(load.call_count, 1)
                self.assertIn('snapshot', load.call_args.kwargs)

    def test_duplicate_json_keys_rejected_at_root_and_nested_levels(self):
        for text in ('{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                secondary.strict_json(text)

    def test_invariant_rejects_pre_demand_peaks_and_capacity_days(self):
        base = dict(max_storage_units=3, sub_moq_orders=0,
                    physical_post_order_peak_position=3, peak_on_hand=3, days_over_capacity=0)
        secondary.check_invariant(base)
        for changes in ({'peak_on_hand': 4}, {'days_over_capacity': 1},
                        {'physical_post_order_peak_position': 4}, {'sub_moq_orders': 1}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'admission invariant'):
                secondary.check_invariant({**base, **changes})

    def test_order_up_to_oracle_with_nonworking_days_and_pending_receipts(self):
        demands = [0, 999, Fraction(1, 2), 2, 999, 0]
        calendar = [1, 0, 1, 1, 0, 1]
        for cap, moq, opening, rop, out_to, lead in product(
                (3, 5), (1, 2), (Fraction(0), Fraction(3, 2)), (0, 2), (3, 4), (1, 2)):
            expected = oracle(demands, opening, cap, moq, rop, 3, lead, out_to=out_to, calendar=calendar)
            test = [{**row, 'is_working_day': flag} for row, flag in zip(rows(demands), calendar)]
            actual = rb.simulate(test, dict(rop=rop, oq=3, out_to=out_to),
                dict(max_storage_units=cap, moq=moq, mean_lead_time=lead,
                     annual_holding_cost_per_unit=1, ordering_cost=1, unit_cost=1), float(opening))
            for field, value in expected.items():
                self.assertAlmostEqual(actual[field], value, msg=str((cap, moq, opening, rop, out_to, lead, field)))
        self.assertEqual(actual['test_days'], 4)
        self.assertGreater(actual['peak_on_hand'], float(opening))

    def test_report_exposes_paired_harm_and_priced_deltas_without_changing_evidence(self):
        metric = rb.simulate(rows([0]), dict(rop=1, oq=1),
            dict(max_storage_units=3, moq=1, mean_lead_time=1,
                 annual_holding_cost_per_unit=1, ordering_cost=1, unit_cost=1), 0)
        def m(fill, costs):
            return {**metric, 'fill_rate_pct': fill, 'costs_by_penalty': dict(zip(('0', '1', '5'), costs))}
        records = {'clipping': {'PL1__a': {'arm': m(90, (10, 20, 50))}, 'PL1__b': {'arm': m(80, (30, 80, 200))}},
                   'strict': {'PL1__a': {'arm': m(80, (9, 25, 60))}, 'PL1__b': {'arm': m(95, (31, 70, 180))}}}
        evidence = dict(cohort=['PL1__a', 'PL1__b'], per_pair=records, summaries={})
        for mode in records:
            evidence['summaries'][mode] = {'ALL': {'arm': {**rb.summarize([v['arm'] for v in records[mode].values()]),
                                                          'initially_infeasible_pairs': 0}}}
        before = secondary.encoded(evidence)
        text = secondary.report(evidence)
        self.assertIn('| ALL | arm | 2 | 1 | 10.000 | 1 | 1 | 1 |', text)
        self.assertIn('| ALL | arm | 1 | 50.00 | 47.50 | -2.50 |', text)
        self.assertIn('| ALL | arm | 5 | 125.00 | 120.00 | -5.00 |', text)
        for definition in ('mean pair cost', 'item-working-day', 'repeated deferrals'):
            self.assertIn(definition, text)
        self.assertEqual(secondary.encoded(evidence), before)

    def test_independent_rational_small_state_oracle(self):
        # 1,728 trajectories; fractional stocks, MOQ, trigger and pipeline.
        for cap, moq, opening, rop, oq, lead, demands in product(
                (2, 3), (1, 2), (Fraction(0), Fraction(3, 2)), (0, 2), (1, 3), (1, 2),
                product((Fraction(0), Fraction(1, 2), Fraction(2)), repeat=3)):
            expected = oracle(demands, opening, cap, moq, rop, oq, lead)
            actual = rb.simulate(rows(demands), dict(rop=rop, oq=oq),
                                 dict(max_storage_units=cap, moq=moq, mean_lead_time=lead,
                                      annual_holding_cost_per_unit=1, ordering_cost=1, unit_cost=1), float(opening))
            for field, value in expected.items():
                self.assertAlmostEqual(actual[field], value, msg=str((cap, moq, opening, rop, oq, lead, demands, field)))
            self.assertLessEqual(actual['physical_post_order_peak_position'], cap)
            self.assertEqual(actual['sub_moq_orders'], 0)

    def test_counterexamples_and_no_service_guarantee(self):
        stats = dict(max_storage_units=3, moq=2, mean_lead_time=1,
                     annual_holding_cost_per_unit=1, ordering_cost=1, unit_cost=1)
        policy = dict(rop=3, oq=2)
        clipped = rb.simulate(rows([0, 2]), policy, stats, 2.5, strict=False)
        strict = rb.simulate(rows([0, 2]), policy, stats, 2.5)
        self.assertEqual(clipped['physical_post_order_peak_position'], 3.5)
        self.assertGreater(clipped['sub_moq_orders'], 0)
        starved = rb.simulate(rows([4, 4]), policy, {**stats, 'moq': 4}, 0)
        self.assertEqual(starved['num_orders'], 0)
        self.assertEqual(starved['fill_rate_pct'], 0)
        excess = rb.simulate(rows([0]), policy, stats, 4)
        self.assertEqual(excess['initial_excess_units'], 1)
        self.assertEqual(excess['days_over_capacity'], 1)
        unspecified = rb.simulate(rows([0]), policy, {**stats, 'max_storage_units': 0}, 10)
        self.assertEqual(unspecified['max_storage_units'], 0)
        self.assertLessEqual(strict['physical_post_order_peak_position'], 3)

    def test_compatibility_mismatch_and_nonfinite_fail_closed(self):
        secondary.assert_match({'cost': 1.0}, {'cost': 1.0})
        with self.assertRaisesRegex(ValueError, 'compatibility'):
            secondary.assert_match({'cost': 2.0}, {'cost': 1.0})
        for value in ('NaN', 'Infinity', '-Infinity'):
            with self.assertRaises(ValueError):
                secondary.strict_json('{"value":' + value + '}')
        with self.assertRaises(ValueError):
            rb.simulate(rows([float('nan')]), dict(rop=1, oq=1), dict(mean_lead_time=1), 0)

    def test_output_is_deterministic_and_never_replaces_existing(self):
        evidence = {'scope': 'secondary, not frozen evidence', 'n': 338}
        with tempfile.TemporaryDirectory() as tmp:
            one, two = Path(tmp).resolve() / 'one', Path(tmp).resolve() / 'two'
            secondary.publish(one, evidence, 'report\n')
            secondary.publish(two, evidence, 'report\n')
            self.assertEqual((one / 'evidence.json').read_bytes(), (two / 'evidence.json').read_bytes())
            with self.assertRaises(FileExistsError):
                secondary.publish(one, evidence, 'changed\n')
            link = Path(tmp).resolve() / 'link'
            link.symlink_to(two, target_is_directory=True)
            with self.assertRaises(ValueError):
                secondary.publish(link / 'new', evidence, 'changed\n')

    def test_public_allowlist_contains_only_secondary_support_not_local_study(self):
        try:
            from scripts import export_public
        except ImportError:
            # Anonymous support/public snapshot excludes the private exporter.
            self.assertFalse((Path(__file__).resolve().parents[1] / 'scripts/build_offline_robustness.py').exists())
            return
        for path in ('inventory_llm/robustness.py', 'scripts/build_secondary_admission.py',
                     'tests/test_secondary_admission.py', 'docs/secondary_admission.md',
                     'outputs/secondary_admission/evidence.json', 'outputs/secondary_admission/report.md'):
            self.assertIn(path, export_public.TEXT_COPY_FILES)
        self.assertNotIn('scripts/build_offline_robustness.py', export_public.TEXT_COPY_FILES)


if __name__ == '__main__':
    unittest.main()
