"""Mocked raw provider contracts and real fork deadlines; no paid/network calls."""

import json
import io
import multiprocessing
import os
import socket
import threading
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from inventory_llm import commercial, commercial_api as api
from tests import test_commercial


FORK_AVAILABLE = os.name == "posix" and "fork" in multiprocessing.get_all_start_methods()


def stalled_worker(provider, method, path, key, data, content_type, shared, size):
    time.sleep(30)
    Path(key).write_text("late upload")


def successful_worker(provider, method, path, key, data, content_type, shared, size):
    value = b'{"ok":true,"body":{"id":"file-own"}}'
    shared[:len(value)] = value
    size.value = len(value)


class CommercialAPITests(unittest.TestCase):
    prepare = test_commercial.CommercialTests.prepare
    candidate = test_commercial.CommercialTests.candidate

    def setUp(self):
        test_commercial.CommercialTests.setUp(self)
        self.prepare()
        self.out = self.dest.with_name("generation")
        self.preflight = patch.object(api, "_transport_context", return_value=None)
        self.preflight.start()
        self.addCleanup(self.preflight.stop)

    def response(self, provider):
        text = json.dumps(self.candidate(), separators=(",", ":"))
        if provider == "openai":
            return {"id": "resp_1", "model": "gpt-4.1-2025-04-14", "status": "completed",
                    "output": [{"id": "ci_1", "type": "code_interpreter_call", "status": "completed",
                                "container_id": "cntr_1", "outputs": [{"type": "logs", "logs": "ok"}]},
                               {"type": "message", "role": "assistant", "status": "completed", "content": [
                                   {"type": "output_text", "text": text}]}],
                    "usage": {"input_tokens": 20, "output_tokens": 100}}
        return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-6",
                "stop_reason": "end_turn", "container": {"id": "container_1"}, "content": [
                    {"type": "server_tool_use", "id": "srv_1", "name": "bash_code_execution"},
                    {"type": "bash_code_execution_tool_result", "tool_use_id": "srv_1", "content": {
                        "type": "bash_code_execution_result", "stdout": "not final JSON", "stderr": "", "return_code": 0,
                        "content": [{"type": "bash_code_execution_output", "file_id": "file-generated"}]}},
                    {"type": "text", "text": text}], "usage": {"input_tokens": 20}}

    def generate(self, provider, response, out=None, delete_error=False):
        self.calls = []

        def exchange(p, method, path, key, body=None, content_type="application/json"):
            self.calls.append((method, path, body, content_type))
            if method == "DELETE":
                if delete_error:
                    raise api.ProviderError("Cleanup failed")
                return {}
            if path == "/v1/files":
                return {"id": "file-own"}
            if isinstance(response, Exception):
                raise response
            return response

        model = "gpt-4.1" if provider == "openai" else "claude-sonnet-4-6"
        with patch.dict("os.environ", {"OPENAI_API_KEY": "TEST_SECRET", "ANTHROPIC_API_KEY": "TEST_SECRET"}), patch.object(api, "_request", side_effect=exchange):
            return api.generate(self.dest, provider, model, out or self.out,
                                live=True, allow_upload=True, allow_paid=True)

    def test_provider_contracts_cleanup_and_persisted_candidate_hash(self):
        for provider in ("openai", "anthropic"):
            out = self.out.with_name(provider)
            with self.subTest(provider=provider):
                report = self.generate(provider, self.response(provider), out)
                self.assertTrue(report["accepted"])
                self.assertTrue(report["provider_execution_checked"])
                self.assertTrue(json.loads((out / "provenance.json").read_text())["accepted"])
                self.assertEqual(report["candidate_sha256"], commercial._sha((out / "candidate.json").read_bytes()))
                self.assertNotIn("TEST_SECRET", "".join(p.read_text() for p in out.iterdir()))
                request = self.calls[1][2]
                deletes = {c[1] for c in self.calls if c[0] == "DELETE"}
                if provider == "openai":
                    self.assertIn(b'name="purpose"\r\n\r\nassistants', self.calls[0][2])
                    self.assertFalse(request["store"])
                    self.assertEqual(request["include"], ["code_interpreter_call.outputs"])
                    self.assertEqual(request["tool_choice"], {"type": "code_interpreter"})
                    self.assertEqual(request["tools"], [{"type": "code_interpreter", "container": {"type": "auto", "file_ids": ["file-own"]}}])
                    self.assertTrue(request["text"]["format"]["strict"])
                    self.assertEqual(deletes, {"/v1/files/file-own", "/v1/containers/cntr_1"})
                else:
                    self.assertEqual(request["tools"], [{"type": "code_execution_20260521", "name": "code_execution"}])
                    self.assertEqual(request["messages"][0]["content"][-1], {"type": "container_upload", "file_id": "file-own"})
                    self.assertEqual(request["output_config"]["format"]["type"], "json_schema")
                    self.assertEqual(deletes, {"/v1/files/file-own", "/v1/files/file-generated"})

    def test_mocked_provider_contracts_do_not_require_fork(self):
        with patch.object(api.multiprocessing, "get_all_start_methods", return_value=[]), patch.object(api.multiprocessing, "get_context", side_effect=AssertionError("Unexpected fork preflight")):
            for provider in ("openai", "anthropic"):
                self.assertTrue(self.generate(provider, self.response(provider), self.out.with_name(provider))["accepted"])

    def test_previews_consent_credentials_and_frozen_paths(self):
        with patch.object(api, "_request") as request, patch.dict("os.environ", {}, clear=True):
            for provider in ("openai", "anthropic"):
                model = "gpt-4.1" if provider == "openai" else "claude-sonnet-4-6"
                self.assertTrue(api.generate(self.dest, provider, model, self.out.with_name(provider))["preview"])
                for kwargs in ({"live": True}, {"live": True, "allow_upload": True, "allow_paid": True}):
                    with self.assertRaises(ValueError):
                        api.generate(self.dest, provider, model, self.out, **kwargs)
            with self.assertRaises(ValueError):
                api.generate(self.dest, "openai", "unverified", self.out)
            with self.assertRaises(ValueError):
                api.generate(self.dest, "openai", "gpt-4.1", self.root / "outputs" / "evidence")
            request.assert_not_called()

    def test_each_consent_gate_independently_blocks_with_valid_credentials(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "TEST_SECRET", "ANTHROPIC_API_KEY": "TEST_SECRET"}), patch.object(api, "_request") as request:
            for provider, model in (("openai", "gpt-4.1"), ("anthropic", "claude-sonnet-4-6")):
                for upload, paid in ((False, True), (True, False)):
                    with self.subTest(provider=provider, upload=upload, paid=paid), self.assertRaises(ValueError):
                        api.generate(self.dest, provider, model, self.out, live=True, allow_upload=upload, allow_paid=paid)
                    self.assertFalse(self.out.exists())
            request.assert_not_called()

    def test_unsupported_or_multithreaded_live_transport_has_no_side_effects(self):
        self.preflight.stop()  # Exercise the real gate, never a live request.
        for provider, model in (("openai", "gpt-4.1"), ("anthropic", "claude-sonnet-4-6")):
            for target, value in (("get_all_start_methods", []),):
                with patch.dict("os.environ", {"OPENAI_API_KEY": "TEST_SECRET", "ANTHROPIC_API_KEY": "TEST_SECRET"}), patch.object(api.multiprocessing, target, return_value=value), patch.object(api, "_request") as request:
                    with self.assertRaises(ValueError):
                        api.generate(self.dest, provider, model, self.out, live=True, allow_upload=True, allow_paid=True)
                    request.assert_not_called()
                    self.assertFalse(self.out.exists())
        stop = threading.Event()
        thread = threading.Thread(target=stop.wait)
        thread.start()
        try:
            with patch.dict("os.environ", {"OPENAI_API_KEY": "TEST_SECRET"}), patch.object(api, "_request") as request:
                with self.assertRaises(ValueError):
                    api.generate(self.dest, "openai", "gpt-4.1", self.out, live=True, allow_upload=True, allow_paid=True)
                self.assertFalse(self.out.exists())
                request.assert_not_called()
        finally:
            stop.set()
            thread.join()

    def test_completed_execution_invalid_final_policy_rejects_both_providers(self):
        for provider in ("openai", "anthropic"):
            for index, update in enumerate(({"bundle_sha256": "0" * 64}, {"order_quantity": True}, {"order_quantity": 1})):
                raw = self.response(provider)
                text = json.dumps({**self.candidate(), **update})
                if provider == "openai":
                    raw["output"][-1]["content"][0]["text"] = text
                else:
                    raw["content"][-1]["text"] = text
                out = self.out.with_name(f"{provider}-{index}")
                with self.subTest(provider=provider, update=update), self.assertRaises(api.ProviderError):
                    self.generate(provider, raw, out)
                self.assertFalse((out / "candidate.json").exists())
                self.assertFalse((out / "validation.json").exists())
                self.assertFalse(json.loads((out / "provenance.json").read_text())["accepted"])
                self.assertEqual(sum(c[0] == "POST" for c in self.calls), 2)
                self.assertIn("/v1/files/file-own", [c[1] for c in self.calls if c[0] == "DELETE"])

    def test_reject_refusal_truncation_pause_stdout_and_execution_errors(self):
        failures = []
        for status in ("incomplete", "failed"):
            raw = self.response("openai")
            raw["status"] = status
            failures.append(("openai", raw))
        for reason in ("pause_turn", "max_tokens", "refusal", "tool_use"):
            raw = self.response("anthropic")
            raw["stop_reason"] = reason
            failures.append(("anthropic", raw))
        for provider in ("openai", "anthropic"):
            raw = self.response(provider)
            raw["output" if provider == "openai" else "content"].pop()
            failures.append((provider, raw))
        raw = self.response("openai")
        raw["output"][-1]["content"] = [{"type": "refusal", "refusal": "No"}]
        failures.append(("openai", raw))
        raw = self.response("openai")
        raw["output"][0]["outputs"][0]["logs"] = "Traceback (most recent call last):\nValueError: invalid"
        failures.append(("openai", raw))
        raw = self.response("anthropic")
        raw["content"][1]["content"]["return_code"] = 1
        failures.append(("anthropic", raw))
        for index, (provider, raw) in enumerate(failures):
            out = self.out.with_name(f"failure-{index}")
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.generate(provider, raw, out)
            self.assertFalse((out / "candidate.json").exists())
            self.assertFalse((out / "validation.json").exists())

    def test_successful_execution_stderr_warning_is_not_failure(self):
        raw = self.response("anthropic")
        raw["content"][1]["content"]["stderr"] = "UserWarning: optional plotting font unavailable"
        self.assertTrue(self.generate("anthropic", raw)["accepted"])

    def test_anthropic_tool_ids_and_results_are_unique_and_paired(self):
        failures = []
        raw = self.response("anthropic")
        raw["content"].insert(0, dict(raw["content"][0]))
        failures.append(raw)
        for identifier in (None, "", "../unsafe"):
            raw = self.response("anthropic")
            raw["content"][0]["id"] = identifier
            raw["content"][1]["tool_use_id"] = identifier
            failures.append(raw)
        for name in ("text_editor_code_execution", "web_search"):
            raw = self.response("anthropic")
            raw["content"][0]["name"] = name
            failures.append(raw)
        raw = self.response("anthropic")
        raw["content"][1]["type"] = "text_editor_code_execution_tool_result"
        failures.append(raw)
        raw = self.response("anthropic")
        raw["content"][1]["content"]["type"] = "code_execution_result"
        failures.append(raw)
        raw = self.response("anthropic")
        raw["content"].pop(1)
        failures.append(raw)
        raw = self.response("anthropic")
        raw["content"].insert(0, {**raw["content"][0], "id": "srv_2"})
        raw["content"].insert(2, dict(raw["content"][2]))
        failures.append(raw)  # Two calls, two results both referring to srv_1.
        for index, raw in enumerate(failures):
            with self.subTest(index=index), self.assertRaises(api.ProviderError):
                self.generate("anthropic", raw, self.out.with_name(f"pairing-{index}"))

    def test_anthropic_documented_execution_and_editor_pairs_succeed(self):
        raw = self.response("anthropic")
        expected = raw["content"][-1]["text"]
        raw["content"][0]["name"] = "code_execution"
        raw["content"][1]["type"] = "code_execution_tool_result"
        raw["content"][1]["content"]["type"] = "code_execution_result"
        self.assertEqual(api.final_text("anthropic", raw), expected)
        for kind in ("view", "create", "str_replace"):
            raw = self.response("anthropic")
            raw["content"][2:2] = [
                {"type": "server_tool_use", "id": "srv_editor", "name": "text_editor_code_execution"},
                {"type": "text_editor_code_execution_tool_result", "tool_use_id": "srv_editor",
                 "content": {"type": f"text_editor_code_execution_{kind}_result"}}]
            with self.subTest(kind=kind):
                self.assertEqual(api.final_text("anthropic", raw), expected)

    def test_anthropic_malformed_resource_shapes_preserve_all_later_owned_ids(self):
        malformed_blocks = [{"type": "bash_code_execution_tool_result", "content": {"content": value}}
                            for value in (None, {}, "bad", [None], [{"type": "bash_code_execution_output", "file_id": "../unsafe"}])]
        malformed_blocks.extend((None, {"type": "bash_code_execution_tool_result", "content": None}))
        for index, malformed in enumerate(malformed_blocks):
            raw = self.response("anthropic")
            raw["content"].insert(2, malformed)
            raw["content"].insert(3, {"type": "bash_code_execution_tool_result", "content": {
                "content": [{"type": "bash_code_execution_output", "file_id": "file-later"}]}})
            out = self.out.with_name(f"resource-shape-{index}")
            with self.subTest(index=index):
                with self.assertRaisesRegex(api.ProviderError, "resource"):
                    self.generate("anthropic", raw, out)
                deleted = {c[1] for c in self.calls if c[0] == "DELETE"}
                self.assertEqual(deleted, {"/v1/files/file-own", "/v1/files/file-generated", "/v1/files/file-later"})
                self.assertFalse(json.loads((out / "provenance.json").read_text())["accepted"])
                self.assertFalse((out / "candidate.json").exists())

    def test_exact_models_and_date_snapshots_not_family_prefixes(self):
        for index, model in enumerate(("gpt-4.1-mini", "gpt-4.1-nano-2025-04-14", "gpt-4.1-foo", "gpt-4.1-2025-99-99")):
            raw = self.response("openai")
            raw["model"] = model
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, "model"):
                self.generate("openai", raw, self.out.with_name(f"model-{index}"))

    def test_cleanup_keeps_earlier_and_later_targets_after_malformed_id(self):
        for provider in ("openai", "anthropic"):
            raw = self.response(provider)
            if provider == "openai":
                raw["output"].insert(1, {"type": "code_interpreter_call", "container_id": "../unsafe"})
                raw["output"].insert(2, {"type": "code_interpreter_call", "container_id": "cntr_later"})
                expected = {"/v1/containers/cntr_1", "/v1/containers/cntr_later"}
            else:
                raw["content"][1]["content"]["content"].extend([
                    {"type": "bash_code_execution_output", "file_id": "../unsafe"},
                    {"type": "bash_code_execution_output", "file_id": "file-later"}])
                expected = {"/v1/files/file-generated", "/v1/files/file-later"}
            with self.subTest(provider=provider), self.assertRaisesRegex(ValueError, "resource"):
                self.generate(provider, raw, self.out.with_name(provider))
            self.assertTrue(expected.issubset({c[1] for c in self.calls if c[0] == "DELETE"}))

    def test_timeout_cleanup_failure_and_provenance_error_preserve_primary(self):
        write = commercial._json

        def fail_provenance(path, value):
            if path.name == "provenance.json":
                raise OSError("PRIVATE_PATH_SECRET")
            return write(path, value)

        with patch.object(commercial, "_json", side_effect=fail_provenance), self.assertRaisesRegex(api.ProviderError, "timed out.*cleanup.*provenance") as err:
            self.generate("openai", api.ProviderError("Request timed out"), delete_error=True)
        self.assertNotIn("PRIVATE_PATH_SECRET", str(err.exception))
        self.assertIn("/v1/files/file-own", [c[1] for c in self.calls if c[0] == "DELETE"])
        self.assertFalse((self.out / "candidate.json").exists())

    def test_successful_call_with_unwritable_provenance_leaves_no_candidate(self):
        write = commercial._json

        def fail_provenance(path, value):
            if path.name == "provenance.json":
                raise OSError("PRIVATE_PATH_SECRET")
            return write(path, value)

        with patch.object(commercial, "_json", side_effect=fail_provenance), self.assertRaisesRegex(api.ProviderError, "provenance"):
            self.generate("openai", self.response("openai"))
        self.assertFalse((self.out / "candidate.json").exists())
        self.assertFalse((self.out / "validation.json").exists())

    def test_persistence_failure_preserves_concurrently_created_user_file(self):
        write = commercial._json

        def create_user_file(path, value):
            if path.name == "provenance.json":
                (path.parent / "candidate.json").write_text("user-owned sentinel")
            return write(path, value)

        with patch.object(commercial, "_json", side_effect=create_user_file), self.assertRaises(api.ProviderError):
            self.generate("openai", self.response("openai"))
        self.assertEqual((self.out / "candidate.json").read_text(), "user-owned sentinel")
        self.assertFalse((self.out / "validation.json").exists())
        self.assertFalse(json.loads((self.out / "provenance.json").read_text())["accepted"])

    def test_validation_persistence_failure_cannot_leave_success_provenance(self):
        original = Path.open

        def fail(path, *args, **kwargs):
            if path.name == "validation.json" and args and args[0] == "xb":
                raise OSError("PRIVATE_PATH_SECRET")
            return original(path, *args, **kwargs)

        with patch.object(Path, "open", fail), self.assertRaises(api.ProviderError):
            self.generate("openai", self.response("openai"))
        self.assertFalse(json.loads((self.out / "provenance.json").read_text())["accepted"])
        self.assertFalse((self.out / "candidate.json").exists())
        self.assertFalse((self.out / "validation.json").exists())

    def test_success_provenance_replace_failure_removes_accepted_artifacts(self):
        with patch.object(Path, "replace", side_effect=OSError("PRIVATE_PATH_SECRET")), self.assertRaises(api.ProviderError) as err:
            self.generate("anthropic", self.response("anthropic"))
        self.assertNotIn("PRIVATE_PATH_SECRET", str(err.exception))
        self.assertFalse(json.loads((self.out / "provenance.json").read_text())["accepted"])
        self.assertFalse((self.out / "candidate.json").exists())
        self.assertFalse((self.out / "validation.json").exists())

    def test_cli_retains_safe_timeout_billing_and_retention_diagnostics(self):
        argv = ["commercial", "generate", "--bundle", str(self.dest), "--provider", "openai",
                "--model", "gpt-4.1", "--dest", str(self.out), "--live", "--allow-upload", "--allow-paid"]
        with patch("sys.argv", argv), patch.object(api, "generate", side_effect=api.ProviderError("Request timed out; possible billing and retention")), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
            commercial.main()
        self.assertIn("timed out; possible billing and retention", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_bundle_replacement_during_inference_rejects_coherent_provenance(self):
        raw = self.response("openai")
        value = self.candidate()
        path = self.dest / "bundle.json"
        manifest = json.loads(path.read_text())
        manifest["source_sha256"] = "f" * 64
        replacement = json.dumps(manifest).encode()
        value["bundle_sha256"] = commercial._sha(replacement)
        raw["output"][-1]["content"][0]["text"] = json.dumps(value)

        def exchange(p, method, endpoint, key, body=None, content_type="application/json"):
            if method == "DELETE":
                return {}
            if endpoint == "/v1/files":
                return {"id": "file-own"}
            path.write_bytes(replacement)
            return raw

        with patch.dict("os.environ", {"OPENAI_API_KEY": "TEST_SECRET"}), patch.object(api, "_request", side_effect=exchange), self.assertRaises(ValueError):
            api.generate(self.dest, "openai", "gpt-4.1", self.out, live=True, allow_upload=True, allow_paid=True)
        self.assertFalse((self.out / "candidate.json").exists())


class TransportTests(unittest.TestCase):
    @unittest.skipUnless(FORK_AVAILABLE, "Real transport requires POSIX fork")
    def test_deadline_covers_dns_send_headers_and_body(self):
        with test_commercial.tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "must-not-upload"
            for phase in ("dns", "send", "headers", "body"):
                def block(*args, **kwargs):
                    time.sleep(30)
                    marker.write_text("late upload")

                connection = Mock()
                connection.getresponse.return_value = Mock(status=200)
                connection.getresponse.return_value.read1.side_effect = block
                factory = Mock(return_value=connection)
                if phase == "send":
                    connection.request.side_effect = block
                elif phase == "headers":
                    connection.getresponse.side_effect = block
                boundary = (patch.object(api.socket, "getaddrinfo", side_effect=block) if phase == "dns"
                            else patch.object(api.http.client, "HTTPSConnection", factory))
                with self.subTest(phase=phase), patch.object(api, "TIMEOUT", 0.2), boundary:
                    start = time.monotonic()
                    with self.assertRaisesRegex(api.ProviderError, "timed out"):
                        api._request("openai", "POST", "/v1/files", "TEST_SECRET", b"x" * (4 * 1024 * 1024))
                    self.assertLess(time.monotonic() - start, 2)
                self.assertFalse(marker.exists())
                self.assertFalse(multiprocessing.active_children())

    @unittest.skipUnless(FORK_AVAILABLE, "Real transport requires POSIX fork")
    def test_full_exchange_deadline_terminates_and_reaps_worker(self):
        with test_commercial.tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "must-not-upload"
            before = {child.pid for child in multiprocessing.active_children()}
            with patch.object(api, "TIMEOUT", 0.2), patch.object(api, "_exchange_worker", stalled_worker):
                with self.assertRaisesRegex(api.ProviderError, "timed out.*billing.*retention"):
                    api._request("openai", "POST", "/v1/files", str(marker), b"data")
            self.assertEqual({child.pid for child in multiprocessing.active_children()}, before)
            self.assertFalse(marker.exists())

    @unittest.skipUnless(FORK_AVAILABLE, "Real transport requires POSIX fork")
    def test_fork_worker_success_without_large_argument_serialization(self):
        with patch.object(api, "_exchange_worker", successful_worker), patch("multiprocessing.reduction.ForkingPickler.dump", side_effect=AssertionError("Must not serialize request")):
            self.assertEqual(api._request("openai", "POST", "/v1/files", "SECRET", b"x" * (4 * 1024 * 1024)), {"id": "file-own"})

    @unittest.skipUnless(FORK_AVAILABLE, "Real transport requires POSIX fork")
    def test_real_request_and_exchange_worker_forward_full_body(self):
        expected = {"id": "resp-own", "status": "completed", "usage": {"input_tokens": 20},
                    "output": [{"type": "message", "text": "x" * 70000 + "✓", "metadata": [True, None, 1.5]}]}
        encoded = json.dumps(expected, ensure_ascii=False).encode("utf-8")
        response, connection = Mock(status=200), Mock()
        response.read1.side_effect = [encoded[:65536], encoded[65536:], b""]
        connection.getresponse.return_value = response
        before = {p.pid for p in multiprocessing.active_children()}
        with patch.object(api.http.client, "HTTPSConnection", return_value=connection):
            self.assertEqual(api._request("openai", "POST", "/v1/responses", "SECRET", {"model": "gpt-4.1"}), expected)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_https_headers_origin_limits_json_and_safe_errors(self):
        self.assertEqual(api.RESPONSE_LIMIT, commercial.MAX_FILE_BYTES)
        response, connection = Mock(status=200), Mock()
        connection.getresponse.return_value = response
        with patch.object(api.http.client, "HTTPSConnection", return_value=connection) as factory:
            response.read1.side_effect = [b'{"id":"file-own"}', b'']
            self.assertEqual(api._exchange("anthropic", "POST", "/v1/files", "SECRET", b"data", "multipart/form-data"), {"id": "file-own"})
            self.assertEqual(factory.call_args.args, ("api.anthropic.com",))
            headers = connection.request.call_args.kwargs["headers"]
            self.assertEqual(headers["anthropic-version"], "2023-06-01")
            self.assertEqual(headers["x-api-key"], "SECRET")
            self.assertNotIn("anthropic-beta", headers)
            for status in (302, 429):
                response.status = status
                with self.assertRaisesRegex(api.ProviderError, f"HTTP {status}"):
                    api._exchange("openai", "POST", "/v1/responses", "SECRET", b"{}", "application/json")
            response.status = 200
            response.read1.side_effect = [b'{"id":"a","id":"b"}', b'']
            with self.assertRaisesRegex(api.ProviderError, "Invalid provider JSON"):
                api._exchange("openai", "POST", "/v1/files", "SECRET", b"x", "application/json")
            response.read1.side_effect = None
            response.read1.return_value = b"x" * 33
            with patch.object(api, "RESPONSE_LIMIT", 32), self.assertRaisesRegex(api.ProviderError, "size limit"):
                api._exchange("openai", "POST", "/v1/files", "SECRET", b"x", "application/json")
            connection.request.side_effect = socket.timeout("SECRET")
            with self.assertRaisesRegex(api.ProviderError, "timed out") as err:
                api._exchange("openai", "POST", "/v1/files", "SECRET", b"x", "application/json")
            self.assertNotIn("SECRET", str(err.exception))
        with self.assertRaisesRegex(api.ProviderError, "Disallowed"):
            api._request("openai", "POST", "https://other.example", "SECRET", b"x")


if __name__ == "__main__":
    unittest.main()
