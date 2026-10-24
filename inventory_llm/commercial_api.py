"""Opt-in hosted execution through killable stdlib HTTPS; no inference retries."""

from __future__ import annotations

import http.client
import json
import multiprocessing
import os
import re
import socket
import ssl
import threading
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from inventory_llm import commercial as local


ORIGINS = {"openai": "api.openai.com", "anthropic": "api.anthropic.com"}
MODELS = {"openai": {"gpt-4.1", "gpt-4o"},
          "anthropic": {"claude-sonnet-4-6", "claude-opus-4-6", "claude-sonnet-4-5-20250929"}}
TIMEOUT = 120
REQUEST_LIMIT = 8 * 1024 * 1024
RESPONSE_LIMIT = local.MAX_FILE_BYTES
RETENTION = ("Deletion is best effort, not immediate erasure. Provider logs/backups may persist. "
             "An ambiguous timeout may leave unknown resources and incur billing; inspect your "
             "provider account. Anthropic container state expires under provider policy; "
             "no container deletion is promised.")


class ProviderError(ValueError):
    """Safe diagnostics only: never raw bodies, credentials or exception strings."""


def _resource(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
        raise ProviderError("Invalid provider resource identifier")
    return value


def _transport_context():
    """Fail closed before workspace creation/upload, including embedded use."""
    if os.name != "posix" or "fork" not in multiprocessing.get_all_start_methods():
        raise ProviderError("Live transport requires POSIX fork; manual preparation and previews remain available")
    if threading.active_count() != 1 or threading.current_thread() is not threading.main_thread():
        raise ProviderError("Live fork transport requires a single-threaded main process")
    return multiprocessing.get_context("fork")


def _exchange(provider: str, method: str, path: str, key: str,
              data: bytes | None, content_type: str) -> dict[str, Any]:
    headers = {"Content-Type": content_type, "Accept": "application/json"}
    if provider == "openai":
        headers["Authorization"] = "Bearer " + key
    else:
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    conn = http.client.HTTPSConnection(ORIGINS[provider], timeout=TIMEOUT, context=ssl.create_default_context())
    try:
        # Direct HTTPS only: no redirects, environment proxies, cookies or SDK retries.
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        if not 200 <= response.status < 300:
            raise ProviderError(f"Provider HTTP {response.status}; no retry. Possible billing/retention.")
        chunks, size = [], 0
        while True:
            chunk = response.read1(min(65536, RESPONSE_LIMIT + 1 - size))
            size += len(chunk)
            if size > RESPONSE_LIMIT:
                raise ProviderError("Provider response exceeds size limit; possible retention/billing")
            if not chunk:
                break
            chunks.append(chunk)
        result = local.strict_json(b"".join(chunks).decode("utf-8")) if size else {}
        if not isinstance(result, dict):
            raise ProviderError("Provider returned a non-object response")
        return result
    except (socket.timeout, TimeoutError):
        raise ProviderError("Request timed out; possible billing and retention. No retry.") from None
    except (OSError, http.client.HTTPException):
        raise ProviderError("HTTPS request failed; possible billing and retention. No retry.") from None
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError("Invalid provider JSON; possible billing and retention") from None
    finally:
        conn.close()


def _exchange_worker(provider, method, path, key, data, content_type, shared, size):
    """Fork inherits request bytes; bounded shared output cannot block on a pipe."""
    try:
        result = {"ok": True, "body": _exchange(provider, method, path, key, data, content_type)}
    except Exception as exc:
        result = {"ok": False, "error": str(exc) if isinstance(exc, ProviderError)
                  else "HTTPS worker failed; possible billing and retention. No retry."}
    encoded = json.dumps(result, allow_nan=False, ensure_ascii=False).encode("utf-8")
    if len(encoded) > len(shared):
        encoded = b'{"ok":false,"error":"Provider response exceeds size limit; possible billing/retention"}'
    shared[:len(encoded)] = encoded
    size.value = len(encoded)


def _request(provider: str, method: str, path: str, key: str,
             body: Any = None, content_type: str = "application/json") -> dict[str, Any]:
    if provider not in ORIGINS or method not in {"POST", "DELETE"} or not re.fullmatch(
        r"/v1/(files|responses|messages|containers)(/[A-Za-z0-9_-]{1,200})?", path
    ):
        raise ProviderError("Disallowed provider endpoint")
    ctx = _transport_context()
    data = body if isinstance(body, bytes) else json.dumps(body, allow_nan=False).encode() if body is not None else None
    if data is not None and len(data) > REQUEST_LIMIT:
        raise ProviderError("Request exceeds size limit")
    shared = ctx.RawArray("B", RESPONSE_LIMIT + 1024)
    size = ctx.RawValue("i", 0)
    worker = ctx.Process(target=_exchange_worker, args=(provider, method, path, key, data, content_type, shared, size))
    started = False
    # Fork has no blocking request serialization. OS scheduling/process creation
    # and termination/reaping add overhead; this is not a hard real-time promise.
    deadline = time.monotonic() + TIMEOUT
    try:
        worker.start()
        started = True
        worker.join(max(0, deadline - time.monotonic()))
        if worker.is_alive() or time.monotonic() > deadline:
            raise ProviderError("Request timed out; possible billing and retention. No retry.")
        if worker.exitcode != 0 or not 0 < size.value <= len(shared):
            raise ProviderError("HTTPS worker failed; possible billing and retention. No retry.")
        result = json.loads(bytes(shared[:size.value]))
        if not result["ok"]:
            raise ProviderError(result["error"])
        return result["body"]
    except OSError:
        raise ProviderError("HTTPS worker failed; possible billing and retention. No retry.") from None
    finally:
        if started:
            if worker.is_alive():
                worker.kill()
            worker.join()  # Reap before returning: no surviving late upload.
        worker.close()


def _multipart(provider: str, csv_bytes: bytes) -> tuple[bytes, str]:
    boundary = "inventor-" + uuid.uuid4().hex
    parts = []
    if provider == "openai":
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="purpose"\r\n\r\nassistants\r\n'.encode())
    parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="training.csv"\r\nContent-Type: text/csv\r\n\r\n'.encode(),
                  csv_bytes, f"\r\n--{boundary}--\r\n".encode()])
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _payload(provider: str, model: str, bundle: dict[str, Any], file_id: str) -> dict[str, Any]:
    text = (bundle["contents"]["instructions.txt"].decode() + "\n" + bundle["contents"]["parameters.json"].decode()
            + "\n" + json.dumps({"bundle_sha256": bundle["bundle_sha256"]}))
    schema = local.response_schema()
    if provider == "openai":
        return {"model": model, "store": False, "max_output_tokens": 8192,
                "input": [{"role": "user", "content": [{"type": "input_text", "text": text}]}],
                "tools": [{"type": "code_interpreter", "container": {"type": "auto", "file_ids": [file_id]}}],
                "tool_choice": {"type": "code_interpreter"}, "include": ["code_interpreter_call.outputs"],
                "text": {"format": {"type": "json_schema", "name": "inventory_candidate", "strict": True, "schema": schema}}}
    return {"model": model, "max_tokens": 8192,
            "messages": [{"role": "user", "content": [{"type": "text", "text": text}, {"type": "container_upload", "file_id": file_id}]}],
            "tools": [{"type": "code_execution_20260521", "name": "code_execution"}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}}}


def final_text(provider: str, response: dict[str, Any]) -> str:
    """Only final assistant text after successful hosted execution, never stdout."""
    if provider == "openai":
        if response.get("status") != "completed" or response.get("error") or response.get("incomplete_details"):
            raise ProviderError("OpenAI response incomplete, refused or failed")
        output = response.get("output")
        if not isinstance(output, list) or not output or any(not isinstance(x, dict) for x in output):
            raise ProviderError("Missing OpenAI output")
        calls = [x for x in output if x.get("type") == "code_interpreter_call"]
        if not calls or any(x.get("status") != "completed" for x in calls):
            raise ProviderError("Missing or unsuccessful hosted execution")
        for call in calls:
            if not isinstance(call.get("outputs"), list):
                raise ProviderError("Missing requested hosted execution outputs")
            for result in call["outputs"]:
                if not isinstance(result, dict) or result.get("type") not in {"logs", "image"}:
                    raise ProviderError("Unsuccessful hosted execution output")
                logs = result.get("logs", "")
                if not isinstance(logs, str) or re.search(r"Traceback \(most recent call last\)|\b\w*Error:", logs):
                    raise ProviderError("Hosted execution reported an error")
        messages = [x for x in output if x.get("type") == "message"]
        if not messages or output[-1] is not messages[-1] or messages[-1].get("role") != "assistant" or messages[-1].get("status") != "completed":
            raise ProviderError("Missing final assistant message")
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list) or any(not isinstance(x, dict) for x in content):
                raise ProviderError("Malformed assistant message")
            if any(x.get("type") == "refusal" for x in content):
                raise ProviderError("Provider refusal")
        content = messages[-1]["content"]
        if len(content) != 1 or content[0].get("type") != "output_text":
            raise ProviderError("Refusal or ambiguous final output")
        text = content[0].get("text")
    else:
        if response.get("stop_reason") != "end_turn" or response.get("role") != "assistant":
            raise ProviderError("Anthropic response refused, paused, truncated or incomplete")
        content = response.get("content")
        if not isinstance(content, list) or not content or any(not isinstance(x, dict) for x in content):
            raise ProviderError("Missing Anthropic content")
        pairs = {
            "bash_code_execution": ("bash_code_execution_tool_result", {"bash_code_execution_result"}),
            "code_execution": ("code_execution_tool_result", {"code_execution_result"}),
            "text_editor_code_execution": ("text_editor_code_execution_tool_result", {
                "text_editor_code_execution_view_result", "text_editor_code_execution_create_result",
                "text_editor_code_execution_str_replace_result"}),
        }
        calls = {}
        for block in content:
            if block.get("type") == "server_tool_use":
                identifier = _resource(block.get("id"))
                name = block.get("name")
                if identifier in calls or not isinstance(name, str) or name not in pairs:
                    raise ProviderError("Duplicate or unrecognized hosted tool call")
                calls[identifier] = name
        results = [x for x in content if str(x.get("type", "")).endswith("_tool_result")]
        if not calls or len(results) != len(calls):
            raise ProviderError("Missing or incomplete hosted tool results")
        executed = False
        seen = set()
        for block in results:
            identifier = _resource(block.get("tool_use_id"))
            if identifier in seen or identifier not in calls:
                raise ProviderError("Duplicate or unmatched hosted tool result")
            seen.add(identifier)
            outer, kinds = pairs[calls[identifier]]
            if block.get("type") != outer:
                raise ProviderError("Hosted tool/result type mismatch")
            result = block.get("content")
            if not isinstance(result, dict) or "error" in str(result.get("type", "")) or result.get("error_code"):
                raise ProviderError("Hosted tool execution failed")
            kind = result.get("type")
            if not isinstance(kind, str) or kind not in kinds:
                raise ProviderError("Hosted tool/result type mismatch")
            if kind in {"bash_code_execution_result", "code_execution_result"}:
                if type(result.get("return_code")) is not int or result["return_code"] != 0:
                    raise ProviderError("Hosted code execution failed")
                executed = True
        if not executed:
            raise ProviderError("Hosted execution did not run code")
        if content[-1].get("type") != "text":
            raise ProviderError("Missing final assistant text; tool stdout is not a policy")
        text = content[-1].get("text")
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("Missing final JSON text")
    return text


def _owned_resources(provider: str, response: dict[str, Any]) -> Iterator[tuple[str, Any]]:
    """Yield invalid sentinels for malformed shapes; never lose later owned IDs."""
    kind = "containers" if provider == "openai" else "files"
    blocks = response.get("output" if provider == "openai" else "content", [])
    if not isinstance(blocks, list):
        yield kind, None
        return
    for block in blocks:
        if not isinstance(block, dict):
            yield kind, None
            continue
        if provider == "openai":
            if block.get("type") == "code_interpreter_call":
                yield kind, block.get("container_id")
        elif block.get("type") in ("bash_code_execution_tool_result", "code_execution_tool_result"):
            result = block.get("content")
            if not isinstance(result, dict) or not isinstance(result.get("content", []), list):
                yield kind, None
                continue
            for output in result.get("content", []):
                if not isinstance(output, dict) or output.get("type") not in ("bash_code_execution_output", "code_execution_output"):
                    yield kind, None
                    continue
                yield kind, output.get("file_id")


def _model_matches(requested: str, returned: Any) -> bool:
    if returned == requested:
        return True
    if not isinstance(returned, str) or re.search(r"(?:-\d{8}|-\d{4}-\d{2}-\d{2})$", requested):
        return False
    suffix = returned.removeprefix(requested + "-")
    if suffix == returned or not re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{8}", suffix):
        return False
    try:
        date.fromisoformat(suffix if "-" in suffix else f"{suffix[:4]}-{suffix[4:6]}-{suffix[6:]}")
        return True
    except ValueError:
        return False


def _persist_success(dest: Path, text: str, report: dict[str, Any], provenance: dict[str, Any]) -> None:
    """Failure provenance already exists. Publish success only after all writes."""
    created = []
    temporary = dest / ("provenance-" + uuid.uuid4().hex + ".json")
    try:
        for path, data in ((dest / "candidate.json", text.encode("utf-8")),
                           (dest / "validation.json", local._encoded(report)),
                           (temporary, local._encoded({**provenance, "accepted": True,
                                                      "candidate_sha256": report["candidate_sha256"]}))):
            with path.open("xb") as fh:
                created.append(path)  # Never delete a file whose exclusive open failed.
                fh.write(data)
        temporary.replace(dest / "provenance.json")
    except OSError:
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # Preserve primary failure; inspect private workspace for partial files.
        raise ProviderError("Could not persist candidate/validation/provenance; inspect private workspace for partial files. " + RETENTION) from None


def generate(bundle_path: Path, provider: str, model: str, dest: Path, *, live: bool = False,
             allow_upload: bool = False, allow_paid: bool = False) -> dict[str, Any]:
    local.workspace_path(dest)
    if provider not in MODELS or model not in MODELS[provider]:
        raise ValueError("Choose an explicitly supported provider/model; no automatic fallback")
    bundle = local.load_bundle(bundle_path)
    key = ""
    if live:
        if not allow_upload or not allow_paid:
            raise ValueError("Live calls require explicit --allow-upload and --allow-paid consent")
        key = os.environ.get("OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY", "")
        if not key or any(ord(ch) < 33 or ord(ch) > 126 for ch in key):
            raise ValueError("Missing or invalid provider credential environment variable")
        _transport_context()
    dest = local._new_workspace(dest)
    local._json(dest / "request_preview.json", {"provider": provider, "origin": ORIGINS[provider],
                "request": _payload(provider, model, bundle, "UPLOAD_ID"),
                "upload_sha256": bundle["files"]["training.csv"],
                "upload_bytes": len(bundle["contents"]["training.csv"]), "notice": local.NOTICE})
    if not live:
        return {"preview": True, "workspace": str(dest), "notice": "Offline preview; no upload or paid call"}
    owned = []
    cleanup = {"deleted": [], "failed": [], "retention_notice": RETENTION}
    provenance = {"provider": provider, "model_requested": model, "started_at": datetime.now(timezone.utc).isoformat(),
                  "adapter_sha256": local._sha(Path(__file__).read_bytes()), "bundle_sha256": bundle["bundle_sha256"],
                  "upload_sha256": bundle["files"]["training.csv"], "consent": {"upload": True, "paid": True},
                  "accepted": False, "paper_evidence": False, "notice": local.NOTICE}
    error = None
    try:
        body, content_type = _multipart(provider, bundle["contents"]["training.csv"])
        uploaded = _request(provider, "POST", "/v1/files", key, body, content_type)
        file_id = _resource(uploaded.get("id"))
        owned.append(("files", file_id))
        payload = _payload(provider, model, bundle, file_id)
        provenance["request_sha256"] = local._sha(json.dumps(payload, sort_keys=True).encode())
        response = _request(provider, "POST", "/v1/responses" if provider == "openai" else "/v1/messages", key, payload)
        malformed = False
        for kind, identifier in _owned_resources(provider, response):
            try:
                owned.append((kind, _resource(identifier)))
            except ProviderError:
                malformed = True  # Continue discovering and registering later valid IDs.
        if malformed:
            raise ProviderError("Invalid provider resource identifier")
        provenance["response_sha256"] = local._sha(json.dumps(response, sort_keys=True, allow_nan=False).encode())
        provenance["response_id"] = _resource(response.get("id"))
        if not _model_matches(model, response.get("model")):
            raise ProviderError("Provider model does not match explicit selection")
        provenance["model_returned"] = response["model"]
        usage = response.get("usage", {})
        provenance["usage"] = {n: v for n, v in usage.items() if n in {"input_tokens", "output_tokens", "total_tokens"}
                               and type(v) is int and v >= 0} if isinstance(usage, dict) else {}
        text = final_text(provider, response)
        report = local.validate(bundle_path, text)
        if report.get("bundle_sha256") != bundle["bundle_sha256"]:
            raise ProviderError("Bundle changed during inference; candidate rejected")
        if report.get("accepted") is not True:
            raise ProviderError("Candidate failed local validation")
        report["provider_execution_checked"] = True
    except (ValueError, TypeError, KeyError, AttributeError, OSError, OverflowError) as exc:
        error = str(exc) if isinstance(exc, ProviderError) else "Candidate or provider response failed local validation"
        provenance["error"] = error
    finally:
        for kind, resource_id in dict.fromkeys(owned):
            try:
                _request(provider, "DELETE", f"/v1/{kind}/{resource_id}", key)
                cleanup["deleted"].append(f"{kind}/{resource_id}")
            except (ValueError, OSError):
                cleanup["failed"].append(f"{kind}/{resource_id}")
        provenance["cleanup"] = cleanup
        try:
            local._json(dest / "provenance.json", provenance)
        except OSError:
            error = (error + "; " if error else "") + "Could not persist provenance"
    if error:
        raise ProviderError(error + f"; cleanup failures: {len(cleanup['failed'])}; provenance retained only if write succeeded. " + RETENTION) from None
    _persist_success(dest, text, report, provenance)
    return {**report, "cleanup": cleanup, "workspace": str(dest)}
