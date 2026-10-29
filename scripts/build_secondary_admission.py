"""Offline secondary MOQ/capacity intervention; never rewrites frozen evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inventory_llm import core, robustness as rb
from inventory_llm.policy_backtest import parse_policy_artifact
from scripts.build_six_run_report import ARMS, RUNS, summarize


def encoded(value) -> bytes:
    rb.finite(value)
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()


def strict_json(text):
    def reject(value):
        raise ValueError('nonfinite JSON constant')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    result = json.loads(text, parse_constant=reject, object_pairs_hook=unique)
    rb.finite(result)
    return result


def assert_match(actual, expected, path='baseline'):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or actual.keys() != expected.keys():
            raise ValueError(f'compatibility mismatch: {path} keys')
        for key in expected:
            assert_match(actual[key], expected[key], f'{path}.{key}')
    elif isinstance(expected, (int, float)):
        if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError(f'compatibility mismatch: {path}')
    elif actual != expected:
        raise ValueError(f'compatibility mismatch: {path}')


def no_symlinks(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('symlink path is not permitted')


def verify_support_manifest(root: Path):
    """When running extracted S2, require its complete, unchanged inventory."""
    manifest_path = root / 'SUPPORT_MANIFEST.json'
    no_symlinks(manifest_path)
    if not manifest_path.exists():
        return
    manifest = strict_json(manifest_path.read_bytes())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError('invalid support manifest')
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('invalid support manifest inventory')
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(root).as_posix())
    if actual != set(manifest):
        raise ValueError('support manifest inventory mismatch')
    for name, digest in manifest.items():
        if (Path(name).is_absolute() or '\\' in name or any(part in ('', '.', '..') for part in name.split('/'))
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                or hashlib.sha256((root / name).read_bytes()).hexdigest() != digest):
            raise ValueError('support manifest digest/path mismatch: ' + name)


def check_invariant(result):
    limit = result['max_storage_units'] + 1e-9
    if (result['sub_moq_orders'] or result['physical_post_order_peak_position'] > limit
            or result['peak_on_hand'] > limit or result['days_over_capacity'] != 0):
        raise ValueError('conditional admission invariant failed')


def publish(dest: Path, evidence: dict, markdown: str):
    no_symlinks(dest)
    if dest.exists():
        raise FileExistsError('destination must be absent')
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.secondary-', dir=dest.parent) as tmp:
        stage = Path(tmp) / 'candidate'
        stage.mkdir()
        (stage / 'evidence.json').write_bytes(encoded(evidence))
        (stage / 'report.md').write_text(markdown, encoding='utf-8')
        no_symlinks(dest)
        if dest.exists():
            raise FileExistsError('destination must be absent')
        os.rename(stage, dest)


def policies(train, stats):
    builders = dict(sap_static=lambda: core.make_sap_policy(stats),
                    universal_rq=lambda: core.make_rq_policy(stats),
                    or_erp_floor=lambda: core.make_erp_floor_rq_policy(stats),
                    or_cold=lambda: core.make_cold_rq_policy(stats),
                    or_sba=lambda: core.make_sba_rq_policy(train, stats),
                    or_empirical=lambda: core.make_empirical_rq_policy(train, stats),
                    or_tuned=lambda: core.make_tuned_rq_policy(train, stats))
    return {arm: core.project_policy_to_feasibility(build(), stats) for arm, build in builders.items()}


def report(evidence):
    lines = ['# Secondary strict-admission replay — 29 October 2026', '',
             'Same recorded masked panel; no new inference, retuning or primary experiment.',
             'Compatibility is checked before the intervention. Costs use masked units.',
             'Positive capacity, initially feasible stock and the stated transition assumptions',
             'are required for the admission invariant; no service or optimality guarantee.', '',
             '| Mode | Group | Arm | n | Cost p0 | Mean fill % | Volume fill % | Sub-MOQ | Deferrals | Initial excess pairs | Capacity days |',
             '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for mode, groups in evidence['summaries'].items():
        for group, arms in groups.items():
            for arm, m in arms.items():
                lines.append(f"| {mode} | {group} | {arm} | {m['n']} | {m['costs_by_penalty']['0']:.2f} | "
                             f"{m['mean_fill_pct']:.3f} | {m['volume_weighted_fill_pct']:.3f} | "
                             f"{m['sub_moq_orders']} | {m['moq_deferrals']} | {m['initially_infeasible_pairs']} | {m['days_over_capacity']} |")
    lines += ['', '## Paired harms: strict minus clipping', '',
              'Counts use the same pairs per arm; differences within 1e-9 are treated as ties.',
              'Worst fill loss is the largest nonnegative clipping-minus-strict loss in percentage points.',
              '| Group | Arm | n | Fill worse pairs | Worst fill loss pp | Cost higher p0 | Cost higher p1 | Cost higher p5 |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    paired = []
    for group, arms in evidence['summaries']['strict'].items():
        keys = [k for k in evidence['cohort'] if group == 'ALL' or k.startswith(group + '__')]
        for arm in arms:
            before = [evidence['per_pair']['clipping'][k][arm] for k in keys]
            after = [evidence['per_pair']['strict'][k][arm] for k in keys]
            losses = [a['fill_rate_pct'] - b['fill_rate_pct'] for a, b in zip(before, after)]
            costs = {p: [b['costs_by_penalty'][p] - a['costs_by_penalty'][p]
                         for a, b in zip(before, after)] for p in ('0', '1', '5')}
            lines.append(f"| {group} | {arm} | {len(keys)} | {sum(x > 1e-9 for x in losses)} | "
                         f"{max([0.0, *losses]):.3f} | " + ' | '.join(str(sum(x > 1e-9 for x in costs[p]))
                                                                    for p in ('0', '1', '5')) + ' |')
            for p in ('0', '1', '5'):
                paired.append(f"| {group} | {arm} | {p} | {mean(a['costs_by_penalty'][p] for a in before):.2f} | "
                              f"{mean(b['costs_by_penalty'][p] for b in after):.2f} | {mean(costs[p]):+.2f} |")
    lines += ['', '## Paired mean costs with priced shortages', '',
              '| Group | Arm | Penalty | Clipping mean | Strict mean | Mean paired delta |',
              '|---|---|---:|---:|---:|---:|', *paired, '',
              'Each mean pair cost is the arithmetic mean of item-horizon costs, not a sum or matched-service cost.',
              'p0 is holding plus ordering; p1/p5 add one/five unit-cost multiples per shortage unit.',
              'Capacity days sum over-capacity pre-demand receipt observations over item-working-days; not unique calendar days.',
              'MOQ counts are repeated deferrals: each triggered working observation below MOQ counts again.',
              'These paired summaries reformat existing metrics only; no trajectory, policy or penalty is retuned.']
    lines += ['', '## Interpretation boundary', '',
              'Compare each arm with itself across modes, not across different cohorts.',
              'All 338 matched pairs remain in descriptive summaries, including initial excess.',
              'Initial excess and unspecified capacity are excluded only from invariant checks.',
              'Per-pair metrics, exclusions, input/policy hashes, p0/p1/p5 accounting and',
              'plant summaries are in evidence.json. Repeated policies are not independent datasets.',
              'The strict rule changes releases, not policy parameters. Deferrals can worsen',
              'service or cost; infeasible opening stock is retained, never silently clipped.',
              'Source grain, latent demand, privacy, rights and historical inference remain unvalidated.',
              'See docs/secondary_admission.md for assumptions, proof and counterexamples.', '']
    return '\n'.join(lines)


def build(dest: Path):
    dest = dest.expanduser()
    no_symlinks(dest)
    dest = dest.resolve(strict=False)
    if dest.exists():
        raise FileExistsError('destination must be absent')
    # No general output writer: only the new secondary namespace or external scratch.
    if (dest.is_relative_to(ROOT) and not dest.is_relative_to(ROOT / 'outputs/secondary_admission')) or ROOT.is_relative_to(dest):
        raise ValueError('destination cannot replace protected project paths')
    verify_support_manifest(ROOT)
    digests = {}

    def read(rel):
        path = ROOT / rel
        no_symlinks(path)
        data = path.read_bytes()
        digests[rel] = hashlib.sha256(data).hexdigest()
        return data

    data = read('data/masked_release/masked_inventory_panel.csv')
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig')), delimiter=';')
    for row in reader:
        if None in row or None in row.values() or row['plant_code'] not in ('PL1', 'PL2', 'PL3') or not re.fullmatch(r'M[0-9A-F]{7}', row['material']) or row['mat_description']:
            raise ValueError('expected frozen masked panel schema and identifiers')
        for key, value in row.items():
            if key not in ('date', 'plant_code', 'material', 'mat_description', 'transportation_network') and value:
                if not math.isfinite(float(value.replace(',', '.'))):
                    raise ValueError('nonfinite panel input')
    grouped = core.load_grouped_rows(snapshot=data)
    if not grouped:
        raise ValueError('empty masked panel')
    end = core.validation_end(grouped)
    targets = sorted(core.eligible_item_keys(grouped, valid_end=end))
    runs = {run: dict(by_key={}, exclusions={}) for run in RUNS}
    items, unit_cost = {}, {}
    for key in targets:
        train, test = core.split_rows(grouped[key], valid_end=end)
        stats = core.compute_stats(train)
        rb.finite(stats)
        arms = policies(train, stats)
        rq = arms['universal_rq']
        opening = core.opening_inventory(test, rq['rop'] + rq['oq'] if rq else 0)
        items[key] = dict(test=test, stats=stats, opening=opening, policies=arms.copy())
        unit_cost[key] = stats['unit_cost']
        reference = {}
        for arm, policy in arms.items():
            if policy is not None:
                result = rb.simulate(test, policy, stats, opening, strict=False)
                old = core.simulate(test, policy, stats, opening, enforce_capacity=True)
                assert_match({field: result[field] for field in old}, old, key + '.' + arm)
                reference[arm] = result
        for run in RUNS:
            rel = f'outputs/runs/{run}/agentic_runs/{key}/output.json'
            if not (ROOT / rel).exists():
                runs[run]['exclusions'][key] = 'missing_artifact'
                continue
            artifact = strict_json(read(rel))
            policy = parse_policy_artifact(artifact, stats) if isinstance(artifact, dict) else None
            if policy is None or arms['sap_static'] is None or rq is None:
                runs[run]['exclusions'][key] = 'invalid_policy' if policy is None else 'infeasible_primary_comparator'
                continue
            result = rb.simulate(test, policy, stats, opening, strict=False)
            old = core.simulate(test, policy, stats, opening, enforce_capacity=True)
            assert_match({field: result[field] for field in old}, old, key + '.' + run)
            runs[run]['by_key'][key] = {**reference, 'llm_pure': result}
            items[key]['policies']['llm:' + run] = policy
    six = summarize(runs, unit_cost)
    assert_match(six, strict_json(read('outputs/six_run_evidence.json')))
    keys = sorted(set.intersection(*[{key for key, rec in runs[run]['by_key'].items()
                                     if all(rec.get(arm) for arm in ['llm_pure', *ARMS])} for run in RUNS]))
    if len(keys) != 338:
        raise ValueError('compatibility mismatch: expected 338 common pairs')
    records, summaries = {}, {}
    invariant_exclusions = {}
    for key in keys:
        item = items[key]
        if not item['stats']['max_storage_units']:
            invariant_exclusions[key] = 'unspecified_capacity'
        elif item['opening'] > int(item['stats']['max_storage_units']):
            invariant_exclusions[key] = 'initial_excess'
    for mode in ('clipping', 'strict'):
        records[mode] = {}
        for key in keys:
            item = items[key]
            records[mode][key] = {arm: rb.simulate(item['test'], policy, item['stats'], item['opening'], strict=mode == 'strict')
                                  for arm, policy in item['policies'].items()}
            if mode == 'strict' and key not in invariant_exclusions:
                for result in records[mode][key].values():
                    check_invariant(result)
        summaries[mode] = {}
        for group in ('ALL', 'PL1', 'PL2', 'PL3'):
            ks = [k for k in keys if group == 'ALL' or k.startswith(group + '__')]
            summaries[mode][group] = {}
            for arm in sorted(items[keys[0]]['policies']):
                metrics = [records[mode][k][arm] for k in ks]
                summaries[mode][group][arm] = {**rb.summarize(metrics),
                    'initially_infeasible_pairs': sum(m['initial_excess_units'] > 0 for m in metrics)}
    # Detect input mutation; never write any of these files.
    if any(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() != digest for rel, digest in digests.items()):
        raise ValueError('input changed during secondary replay')
    evidence = dict(schema_version=1, scope='secondary strict-admission intervention; not replacement frozen evidence',
                    protocol_date='2026-10-29', input_sha256=digests, n_targets=len(targets), n_common=len(keys),
                    compatibility='passed: all core fields and frozen six-run summary; tolerance 1e-10 relative/1e-7 absolute',
                    run_exclusions={r: {**runs[r]['exclusions'], **{k: 'not_common_all_arms' for k in runs[r]['by_key'] if k not in keys}} for r in RUNS},
                    invariant_exclusions=invariant_exclusions, cohort=keys, summaries=summaries, per_pair=records)
    publish(dest, evidence, report(evidence))
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, required=True, help='Absent output directory; never a frozen-output path')
    args = parser.parse_args()
    result = build(args.dest)
    print(json.dumps(dict(n_common=result['n_common'], compatibility=result['compatibility'], destination=str(args.dest))))
