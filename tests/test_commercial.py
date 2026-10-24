"""Offline commercial boundaries and immutable-source regressions."""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from inventory_llm import commercial, core
from inventory_llm.synthetic_demo import generate_synthetic_csv


class CommercialTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        override = patch.object(commercial, "PROJECT_ROOT", self.root)
        override.start()
        self.addCleanup(override.stop)
        self.csv = self.root / "source.csv"
        generate_synthetic_csv(self.csv)
        self.dest = self.root / "commercial_workspaces" / "handoff"
        self.key = "SYN_A__MAT_SMOOTH"

    def prepare(self):
        return commercial.prepare(self.csv, self.key, self.dest)

    def candidate(self):
        bundle = commercial.load_bundle(self.dest)
        return dict(material_id=self.key, bundle_sha256=bundle["bundle_sha256"],
                    policy_family="rq", reorder_point=100, order_quantity=25,
                    safety_stock=20, order_up_to=None, rationale="Synthetic test only")

    def rewrite(self, change):
        with self.csv.open(newline="") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        change(rows)
        with self.csv.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=rows[0], delimiter=";")
            writer.writeheader()
            writer.writerows(rows)

    def test_prepare_training_only_and_replay(self):
        def change(rows):
            for row in rows:
                row["material_note"] = "DO_NOT_UPLOAD_FREE_TEXT"
                if row["date"] >= core.TRAIN_CUTOFF:
                    row.update(actual_demand="987654321", unit_cost="123456789")
        self.rewrite(change)
        self.prepare()
        training = (self.dest / "training.csv").read_text()
        for forbidden in ("987654321", "DO_NOT_UPLOAD", "inventory_on_hand"):
            self.assertNotIn(forbidden, training)
        self.assertNotIn("123456789", (self.dest / "parameters.json").read_text())
        report = commercial.validate(self.dest, json.dumps(self.candidate()), self.csv)
        self.assertTrue(report["accepted"])
        self.assertFalse(report["paper_evidence"])
        self.assertFalse(report["joint_feasibility_proven"])
        self.assertEqual(set(report["replay"]), {"unclipped", "capacity_clipped"})

    def test_strict_json_fields_constraints_and_ss(self):
        self.prepare()
        good = self.candidate()
        bad = [json.dumps(good)[:-1] + ',"material_id":"duplicate"}']
        for update in ({"order_quantity": True}, {"reorder_point": float("nan")},
                       {"safety_stock": float("inf")}, {"material_id": "other"},
                       {"bundle_sha256": "0" * 64}, {"unknown": 1}, {"order_quantity": 1},
                       {"reorder_point": 0}, {"order_up_to": 200},
                       {"policy_family": "ss", "order_up_to": 110}):
            bad.append(json.dumps({**good, **update}))
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError):
                commercial.validate(self.dest, text)
        with self.assertRaises(ValueError):
            commercial.strict_json('{"x":1e999}')
        self.assertEqual(commercial.validate(self.dest, json.dumps({**good, "policy_family": "ss", "order_up_to": 125}))["policy"]["out_to"], 125)

    def test_unknown_insufficient_and_malformed(self):
        with self.assertRaises(ValueError):
            commercial.prepare(self.csv, "missing", self.dest)
        for demand in ("bad", "1"):
            self.csv.write_text("date;plant_code;material;actual_demand;is_working_day\n"
                                f"2026-01-01;P;M;{demand};1\n")
            with self.assertRaises(ValueError):
                commercial.prepare(self.csv, "P__M", self.dest)
        self.assertFalse(self.dest.exists())

    def test_workspace_escape_existing_and_symlink_refused(self):
        for path in (self.root / "outputs" / "runs" / "run-01",
                     self.root / "commercial_workspaces" / ".." / "escape"):
            with self.assertRaises(ValueError):
                commercial.prepare(self.csv, self.key, path)
        self.prepare()
        before = (self.dest / "bundle.json").read_bytes()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(before, (self.dest / "bundle.json").read_bytes())
        link = self.dest.with_name("link")
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            commercial.prepare(self.csv, self.key, link / "escape")

    def test_bundle_tamper_and_replay_source_mismatch(self):
        self.prepare()
        text = json.dumps(self.candidate())
        self.csv.write_text(self.csv.read_text() + "\n")
        with self.assertRaises(ValueError):
            commercial.validate(self.dest, text, self.csv)
        (self.dest / "training.csv").write_text("tampered")
        with self.assertRaises(ValueError):
            commercial.validate(self.dest, text)

    def test_reorder_point_must_cover_safety_stock(self):
        self.prepare()
        for family, out_to in (("rq", None), ("ss", 35)):
            value = {**self.candidate(), "reorder_point": 10, "safety_stock": 20,
                     "policy_family": family, "order_up_to": out_to}
            with self.subTest(family=family), self.assertRaisesRegex(ValueError, "safety stock"):
                commercial.validate(self.dest, json.dumps(value))
            value.update(reorder_point=20, order_up_to=45 if family == "ss" else None)
            self.assertTrue(commercial.validate(self.dest, json.dumps(value))["accepted"])

    def test_rehashed_bundle_pair_absent_from_replay_is_value_error(self):
        self.prepare()
        value = self.candidate()
        training = self.dest / "training.csv"
        training.write_bytes(training.read_bytes().replace(b"SYN_A;MAT_SMOOTH", b"ABSENT;PAIR"))
        parameters = self.dest / "parameters.json"
        data = json.loads(parameters.read_text())
        data["material_id"] = "ABSENT__PAIR"
        parameters.write_text(json.dumps(data))
        self.tamper_manifest(lambda m: m.update(material_id="ABSENT__PAIR", files={
            **m["files"], "training.csv": commercial._sha(training.read_bytes()),
            "parameters.json": commercial._sha(parameters.read_bytes())}))
        value.update(material_id="ABSENT__PAIR", bundle_sha256=commercial.load_bundle(self.dest)["bundle_sha256"])
        self.assertTrue(commercial.validate(self.dest, json.dumps(value))["accepted"])
        with self.assertRaisesRegex(ValueError, "pair.*replay"):
            commercial.validate(self.dest, json.dumps(value), self.csv)

    def test_capacity_rejection_without_repair(self):
        self.rewrite(lambda rows: [row.update(max_storage_units="50") for row in rows])
        self.prepare()
        with self.assertRaises(ValueError):
            commercial.validate(self.dest, json.dumps({**self.candidate(), "order_quantity": 40, "safety_stock": 20}))

    def test_training_calendar_ignores_future_flags(self):
        def change(rows):
            for row in rows:
                if row["plant_code"] == "SYN_C" and row["date"] >= core.TRAIN_CUTOFF:
                    row["is_working_day"] = "1"
        self.rewrite(change)
        commercial.prepare(self.csv, "SYN_C__MAT_REPAIRED", self.dest)
        self.assertIn("SYN_C", commercial.load_bundle(self.dest)["calendar_repair"]["calendar_repaired_plants"])

    def test_prepare_and_replay_use_single_source_snapshot(self):
        original, read, reads = self.csv.read_bytes(), commercial._bytes, []

        def mutate(path, limit=commercial.MAX_FILE_BYTES):
            data = read(path, limit)
            if path == self.csv:
                reads.append(path)
                self.csv.write_bytes(b"malformed replacement")
            return data

        with patch.object(commercial, "_bytes", side_effect=mutate):
            self.prepare()
        self.assertEqual(len(reads), 1)
        self.assertEqual(commercial.load_bundle(self.dest)["source_sha256"], commercial._sha(original))
        self.csv.write_bytes(original)
        text = json.dumps(self.candidate())
        reads.clear()
        with patch.object(commercial, "_bytes", side_effect=mutate):
            self.assertTrue(commercial.validate(self.dest, text, self.csv)["accepted"])
        self.assertEqual(len(reads), 1)

    def tamper_manifest(self, change):
        path = self.dest / "bundle.json"
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))

    def test_required_provenance_hash_shape_and_types(self):
        self.prepare()
        path = self.dest / "bundle.json"
        original = path.read_text()
        for name, value in (("source_sha256", None), ("source_sha256", "bad"),
                            ("software_sha256", {}), ("calendar_repair", {}),
                            ("training_rows", True), ("format", True),
                            ("calendar_repair", {"working_day_derivation_mode": [],
                             "calendar_repaired_plants": [], "calendar_repaired_rows": 0,
                             "calendar_derived_row_dates": 0})):
            path.write_text(original)
            self.tamper_manifest(lambda m: m.update({name: value}))
            with self.subTest(name=name), self.assertRaises(ValueError):
                commercial.load_bundle(self.dest)
        path.write_text(original)
        self.tamper_manifest(lambda m: m.pop("source_sha256"))
        with self.assertRaises(ValueError):
            commercial.load_bundle(self.dest)

    def test_bundle_parameter_ranges_and_derived_relationships(self):
        self.prepare()
        path = self.dest / "parameters.json"
        original = path.read_bytes()
        for name, value in (("service_level", 1.5), ("moq", 0), ("moq", 1.5),
                            ("effective_lead_time", 99), ("sigma_ltd", 0),
                            ("annual_holding_cost_per_unit", 999), ("unit_cost", 0)):
            parameters = json.loads(original)
            parameters["stats"][name] = value
            path.write_text(json.dumps(parameters))
            self.tamper_manifest(lambda m: m["files"].update({"parameters.json": commercial._sha(path.read_bytes())}))
            with self.subTest(name=name), self.assertRaises(ValueError):
                commercial.load_bundle(self.dest)

    def test_aggregated_normalized_limit_rejects_before_writes(self):
        def change(rows):
            first = {**rows[0], "actual_demand": "1000000000000"}
            rows.extend(first.copy() for _ in range(1001))
        self.rewrite(change)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.dest.exists())

    def run_cli_failure(self, args, out):
        with patch("sys.argv", ["commercial", *args]), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit) as err:
            commercial.main()
        self.assertEqual(err.exception.code, 2)
        self.assertNotIn("Traceback", stderr.getvalue())
        if out.exists():
            self.assertEqual([p.name for p in out.iterdir()], ["validation.json"])
            self.assertFalse(json.loads((out / "validation.json").read_text())["accepted"])

    def test_cli_failure_only_report_and_calendar_overflow(self):
        self.rewrite(lambda rows: [row.update(delivery_time="1000000000000") for row in rows])
        self.prepare()
        candidate = self.dest / "candidate.json"
        candidate.write_text(json.dumps(self.candidate()))
        out = self.dest.with_name("failure-report")
        self.run_cli_failure(["validate", "--bundle", str(self.dest), "--candidate", str(candidate),
                              "--csv", str(self.csv), "--dest", str(out)], out)
        self.assertTrue(out.exists())

    def test_cli_oversized_csv_cell_is_safe(self):
        self.csv.write_text("date;plant_code;material;actual_demand;is_working_day;note\n"
                            "2026-01-01;P;M;1;1;" + "x" * (csv.field_size_limit() + 1))
        self.run_cli_failure(["prepare", "--csv", str(self.csv), "--pair", "P__M", "--dest", str(self.dest)], self.dest)
        self.assertFalse(self.dest.exists())

    def test_ambiguous_pair_collision_rejects_before_grouping(self):
        def change(rows):
            rows[0].update(plant_code="P_", material="M")
            rows[1].update(plant_code="P", material="_M")
        self.rewrite(change)
        with self.assertRaises(ValueError):
            commercial.prepare(self.csv, "P___M", self.dest)
        self.assertFalse(self.dest.exists())

    def test_bundle_training_ambiguous_identity_rejected(self):
        self.prepare()
        training = self.dest / "training.csv"
        training.write_bytes(training.read_bytes().replace(b"SYN_A;MAT_SMOOTH", b"P_;M"))
        parameters = self.dest / "parameters.json"
        value = json.loads(parameters.read_text())
        value["material_id"] = "P___M"
        parameters.write_text(json.dumps(value))
        self.tamper_manifest(lambda m: m.update(material_id="P___M", files={
            **m["files"], "training.csv": commercial._sha(training.read_bytes()),
            "parameters.json": commercial._sha(parameters.read_bytes())}))
        with self.assertRaises(ValueError):
            commercial.load_bundle(self.dest)

    def test_capacity_below_moq_rejects_before_workspace(self):
        self.rewrite(lambda rows: [row.update(max_storage_units="1", minimum_order_quantity="25") for row in rows])
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertFalse(self.dest.exists())

    def test_replay_discloses_opening_stock_fallback(self):
        self.rewrite(lambda rows: [row.update(inventory_on_hand="") for row in rows])
        self.prepare()
        report = commercial.validate(self.dest, json.dumps(self.candidate()), self.csv)
        expected = core.make_rq_policy(commercial.load_bundle(self.dest)["stats"])
        self.assertEqual(report["opening_inventory_source"], "formula_rop_plus_q_fallback")
        self.assertEqual(report["opening_inventory_units"], expected["rop"] + expected["oq"])


if __name__ == "__main__":
    unittest.main()
