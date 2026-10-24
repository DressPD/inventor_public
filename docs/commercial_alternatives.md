# Optional commercial inventory-analysis candidates

This optional path generates **new candidates**, not paper evidence, a reproduction
of proprietary study inference, an equal-service comparison or guaranteed optima.
Operational use requires human approval. Frozen scientific JSONs, numerical results,
figures/tables and original prompt bytes remain unchanged. Author-approved reporting
corrections and explicitly post-study commercial-extension prose are separate from
those scientific assets; new candidates do not extend the study evidence.
No UI or private inference client is needed.
Python 3.10+ and its standard library suffice; no SDK, site packages, `.env` loader
or credentials are needed for manual preparation, validation or previews.

## Prepare an offline handoff

The public export includes `data/synthetic_inventory.csv`. In a private checkout
where that fixture is absent, generate it locally first:

```sh
python3 -S -m inventory_llm.synthetic_demo
```

Then prepare the handoff from the repository root:

```sh
python3 -S -m inventory_llm.commercial prepare \
  --csv data/synthetic_inventory.csv --pair SYN_A__MAT_SMOOTH \
  --dest commercial_workspaces/handoff-01
```

Use a different fresh name for every operation. Destinations must be direct
children of `commercial_workspaces/`; existing paths, nested paths, symlinks,
path escapes and released evidence paths are refused. The directory is ignored
by Git, not encrypted. Protect it and delete local copies according to your own
retention policy; never force-add it to Git. The exporter copies only allowlisted
software/tests/docs, never this workspace, uploads, transcripts or new outputs.
Use a trusted, locally owned workspace parent. These checks are not a race-proof
sandbox against another process under the same local account replacing paths.

The bundle contains:

- `training.csv`: only the selected pair, dates **strictly before 2026-03-10**,
  aggregated material-date records, nonnegative demand, effective repaired working-day
  flags and non-empty lead-time observations. No free text, inventory observations,
  receipts, corrections, scrap or other pairs are uploaded.
- `parameters.json`: identity and allowlisted numeric training statistics, costs,
  service target, MOQ, ERP buffers and storage limit. Missing optional source
  parameters retain the deterministic core's documented defaults.
- `instructions.txt`: adapted deterministic analysis instructions. Private tools,
  presigned URLs, original HTML/PNG deliverables and RESULT_JSON markers are
  explicitly replaced by hosted execution and one final strict JSON object.
- `schema.json`: the exact new candidate contract, separate from historical
  artifacts. Supports `rq` and consistent `ss` policies; no tolerant coercion.
- `bundle.json`: source/training/parameter/instruction/schema hashes, cutoff,
  row count and local preprocessing provenance. Keep the original bundle locally.

The training split precedes calendar repair, so future flags cannot influence
training repair. All source pairs may contribute same-date training calendar
votes, as in the deterministic core, but only selected normalized rows leave the
computer. Each preparation/replay reads one bounded source snapshot into memory;
validation, hashing and the deterministic loader use those same bytes, even if
the source path changes afterward. The full source is never copied into a bundle.
The full source hash supports optional local held-out replay. Hashes
detect accidental changes; they are not signatures or proof of data authenticity.

## Manual ChatGPT or Claude workflow

1. Obtain company/data-owner authorization before any external upload. Confirm
   account privacy, retention, region, contractual controls and available analysis
   tools. A chat subscription is separate from API access and billing.
2. Open ChatGPT with Data Analysis or Claude with code execution enabled. Upload
   **only** `training.csv`. Paste `instructions.txt`, `parameters.json` and
   `schema.json`. Supply the exact `bundle_sha256` printed by `prepare`; do not
   substitute the CSV hash. Never upload the full source or local held-out rows.
3. Ask the service to run its hosted analysis and return one final JSON object.
   If the service cannot run code, refuses, truncates, pauses or reports execution
   failure, treat the attempt as failed. Do not execute generated code locally.
4. Save the final assistant JSON verbatim as
   `commercial_workspaces/handoff-01/candidate.json`. No Markdown fences,
   RESULT_JSON markers, HTML attachments or tool stdout. Do not repair an invalid
   response; retain its failure and make a separately approved new attempt only
   if needed. Manual provenance cannot independently verify hosted execution.

```sh
python3 -S -m inventory_llm.commercial validate \
  --bundle commercial_workspaces/handoff-01 \
  --candidate commercial_workspaces/handoff-01/candidate.json \
  --csv data/synthetic_inventory.csv --dest commercial_workspaces/check-01
```

Omit `--csv` for static checks only. Replay requires the exact original source
bytes and at least 40 held-out working days. Preparation requires at least 20
training working days; no held-out data is needed for preparation itself.
Validation rejects duplicate keys, nonfinite/overflow numbers, boolean integers,
unknown/missing fields, wrong identity/hash, inconsistent family/parameters,
nonpositive reorder/order values, MOQ violations and supplied static capacity
violations. Historical parser semantics remain unchanged behind this strict gate.

The local report labels candidates as non-paper evidence. It distinguishes:

- **Static acceptance**: `safety_stock + order_quantity <= capacity`, where a
  positive capacity is supplied; MOQ and order-up-to consistency also pass.
- **Unclipped trajectory replay**: storage exceedances may occur despite static
  acceptance. Static storage rules are not a trajectory feasibility proof.
- **Capacity-clipped replay**: clips each release but can produce orders below
  MOQ. It does **not** prove simultaneous MOQ/capacity feasibility.

Replay uses the shared simulator and observed opening inventory when available.
Without an observation, it uses the deterministic formula policy's ROP + Q;
the report records the opening-stock source and units. Replay starts with an empty
pipeline, rounded working-day lead time and no shortage penalty. It never
optimizes, projects, repairs or chooses a policy using the held-out rows.

## API preview and optional live invocation

The reviewed model set is deliberately narrow:

| Provider | Explicit model choices | Required capabilities |
|---|---|---|
| OpenAI | `gpt-4.1`, `gpt-4o` | Responses API, Code Interpreter, structured JSON output |
| Anthropic | `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-sonnet-4-5-20250929` | Messages, Files, structured output, `code_execution_20260521` |

Availability depends on your account. Verify current provider compatibility and
terms before live use. Unknown identifiers are refused, not guessed by prefix;
adding a model requires an explicit reviewed code/configuration change and
contract tests. No model is selected or switched automatically.

```sh
# Offline: no environment credentials needed; UPLOAD_ID is a placeholder.
python3 -S -m inventory_llm.commercial generate \
  --bundle commercial_workspaces/handoff-01 --provider openai --model gpt-4.1 \
  --dest commercial_workspaces/openai-preview-01
python3 -S -m inventory_llm.commercial generate \
  --bundle commercial_workspaces/handoff-01 --provider anthropic \
  --model claude-sonnet-4-6 --dest commercial_workspaces/claude-preview-01
```

For an **independently approved, billable** run, set `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` in your process environment through your secret manager. Do
not put keys in arguments, bundles, transcripts, source files or version control.
Use a new destination and add all three flags:

```sh
# Billable external upload/inference: run only after explicit authorization.
python3 -S -m inventory_llm.commercial generate \
  --bundle commercial_workspaces/handoff-01 --provider openai --model gpt-4.1 \
  --dest commercial_workspaces/openai-live-01 \
  --live --allow-upload --allow-paid
```

The Anthropic live form uses the same flags with `--provider anthropic` and an
explicit compatible model. Code performs exactly one Files upload and one
inference request, using direct stdlib HTTPS to `api.openai.com` or
`api.anthropic.com`. OpenAI uses an automatic Code Interpreter container with
the uploaded file ID, required `tool_choice`, requested execution logs
(`include=code_interpreter_call.outputs`), `store=false` and strict `text.format`. Anthropic uses
`container_upload`, GA Files (no legacy beta header), versioned code execution
and `output_config.format`. There are no custom base URLs, redirects, proxies,
inference retries, continuations or local code execution. Live transport requires
POSIX `fork` in a **single-threaded main process**; unsupported platforms and
multithreaded callers fail closed before workspace creation or upload. Manual
preparation, validation and offline previews remain portable. Use the standalone
CLI rather than embedding live execution in a threaded application or a runtime
with native background threads.

Each HTTP exchange has a 120-second budget starting immediately before fork,
covering DNS, connect, send, headers and body. Request bytes and credentials are
inherited in memory, not synchronously serialized through spawn bootstrap.
Timeout kills and reaps the worker before returning, with no surviving late
upload. Ordinary OS scheduling, process creation, termination/reaping and local
encoding add overhead; this is not a hard real-time bound. Killing the local
worker does not cancel provider-side work or prove deletion. Requests are bounded
at 8 MiB; responses and bundle files at 4 MiB; local source CSVs at 128 MiB.

The adapter rejects refusal, incomplete/truncated/paused turns, missing final
assistant JSON, missing execution and unsuccessful execution results. Tool stdout
is never parsed as the final policy. A completed tool status is a provider-level
signal, not an independent scientific verification of generated code correctness.
Local strict validation must still pass. Invalid responses never become accepted
candidates; provenance records the failed attempt without raw provider bodies.
OpenAI execution-log screening conservatively rejects traceback/error-looking
text (for example, `Traceback (most recent call last)` or `ValueError:`), even if
successful analysis only quotes those strings. Such false positives remain failed
attempts, without automatic repair or retry. Anthropic errors/nonzero return codes
are rejected; a stderr warning alone does not establish failure.

## Billing, retention and provenance

API tokens and hosted execution/container usage may be billed separately from
each other and from chat subscriptions. No prices, free tier or zero-data-retention
eligibility are assumed. Preview requests are offline; live execution is not a
development or test requirement and was not used to verify this implementation.

`provenance.json` records requested/returned model, response ID, bundle/upload/
request/response hashes, numeric token usage, explicit consent, static acceptance
and cleanup outcomes. Raw transcripts are not saved. Successful candidate and
validation JSON stay in the ignored workspace. Keep these records private.
Candidate hashes cover the exact persisted final UTF-8 bytes. Returned model
names must equal the explicitly selected model or use a valid date-shaped
snapshot of that exact name; sibling families such as `gpt-4.1-mini` are rejected.
If a provenance write fails, diagnostics retain the primary provider error;
newly created candidate/validation files are removed best effort; inspect the
private workspace if removal fails. Failure provenance starts with `accepted=false`;
success replaces it atomically only after candidate and validation persistence.
Existing user files are never removed when their exclusive creation fails.

Cleanup attempts delete only resources created by that invocation: the uploaded
file, returned OpenAI automatic containers and returned Anthropic generated file
IDs. Cleanup failure does not hide the primary error. No deletion of pre-existing
files, account-wide resources or reused containers is attempted. Anthropic
container state remains subject to provider-managed expiry; no deletion endpoint is
invented. A timeout can occur after provider-side acceptance, leaving unknown
upload/container IDs and possible charges. Inspect your provider account; never
silently retry. Deletion is best effort and does not promise immediate erasure of
logs, backups or contractual retention copies.

## Official sources

Request shapes reviewed 24 October 2026; check again before live adoption:

- https://developers.openai.com/api/docs/guides/tools-code-interpreter
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/reference/resources/files/methods/create
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- https://platform.claude.com/docs/en/build-with-claude/files
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs

Software archival upgrades and paper archival/submission upgrades are separate
manual actions. See the canonical release notes and release/submission checklist.
