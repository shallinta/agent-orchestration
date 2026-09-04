# Stargazing 6 disposable experiment

## Local verification

From the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v -s experiments/stargazing-006 -p 'test_*.py'
```

Expected output ends with `OK`. The tests use artificial Codex JSONL, artificial Claude stream-json, fake controller turns, and temporary fake executables. This command does not start either real Agent CLI.

## Real Probe entry (do not run before the preflight review)

The entry point creates one `TemporaryDirectory`, two independent temporary Git workspaces, shared synthetic Harness state, and two role-bound MCP commands. It prints and saves only a sanitized structural summary. Run the success Probe with:

```sh
summary_path="$(mktemp -t sg6-success-summary.XXXXXX)" && review_path="$(mktemp -t sg6-success-review.XXXXXX)" && PYTHONDONTWRITEBYTECODE=1 python3 experiments/stargazing-006/run_probe.py --mode success --summary "$summary_path" --review-bundle "$review_path" && printf 'saved summary: %s\ntemporary review bundle: %s\n' "$summary_path" "$review_path"
```

Run the direct `ENOENT` start-failure Probe with:

```sh
summary_path="$(mktemp -t sg6-failure-summary.XXXXXX)" && review_path="$(mktemp -t sg6-failure-review.XXXXXX)" && PYTHONDONTWRITEBYTECODE=1 python3 experiments/stargazing-006/run_probe.py --mode start-failure --summary "$summary_path" --review-bundle "$review_path" && printf 'saved summary: %s\ntemporary review bundle: %s\n' "$summary_path" "$review_path"
```

These commands start real Agent CLIs. Recheck installed versions, CLI help, and effective initialization/tool surfaces immediately before use; no version is hardcoded. Failure mode injects an absolute nonexistent Claude executable owned by that temporary run. `--review-bundle` is required and must name a caller-created absolute path outside the repository. It is an **unredacted** transcript bundle: Agent-authored text may contain sensitive values, paths, or credentials despite the artificial scenario. The file is forced to mode `0600`, but that is not content sanitization. Use it only for short-lived local A–D review; never share or commit it, and securely delete it immediately after review. Only the separate summary retains the stated sanitization guarantee.

To repeat local verification after changes:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -v -s experiments/stargazing-006 -p 'test_*.py'
git diff --check -- experiments/stargazing-006
find experiments/stargazing-006 -type d -name __pycache__ -print
```

The first two commands must exit `0`; the final command must print nothing.

## Runner output

`CodexRunner.run(...)` and `ClaudeRunner.run(...)` return `AgentRunResult` with separate `session_id`, normalized `machine_events`, `final_result`, `process_exit`, `usage`, `failures`, `timed_out`, `terminal_completed`, `nonzero_exit`, `unexpected_tool_calls`, and `evidence_path` fields. `FileNotFoundError` is intentionally not converted into an Agent result. An observed non-MCP shell, file, web, or mismatched MCP tool event writes sanitized evidence and then raises `UnexpectedToolCallError`, stopping the Probe without retry.

## Exact boundary

- Commands are passed directly to `subprocess.Popen` as argument arrays with `shell=False`. The allowed timeout is positive and no greater than 300 seconds; the default is 300 seconds. Timeout terminates the process group and remains distinct from CLI exit, Agent terminal result, and parser failure.
- Codex start and resume use `exec --disable shell_tool`, `--ignore-user-config`, `--ignore-rules`, `--sandbox read-only`, `--color never`, `--json`, an existing temporary Git workspace, and one required `sg6` STDIO MCP server exposing only `query_thread`, `publish_delegation`, and `send_message`. For the currently verified Codex CLI version, `--disable shell_tool` closes the Codex built-in shell surface while preserving the explicit `sg6` MCP surface; this version-sensitive boundary must be rechecked before a real run. No bypass, `danger-full-access`, Git-check skip, or ephemeral session is used.
- Claude start and resume use `-p`, `--restricted`, `--disable-slash-commands`, `--strict-mcp-config`, an empty built-in `--tools` value, only the three explicit `mcp__sg6__*` allowed tools, `--permission-mode dontAsk`, and stream-json. `--safe-mode` is intentionally absent because it removes the explicit MCP surface in the verified local configuration.
- No CLI version is encoded in code or documentation. Versions and effective init surfaces must be checked immediately before a real run. Codex read-only is only a workspace-write restriction; it is not workspace-external read isolation. Claude restricted and tool flags are not claimed as complete OS or network isolation.
- Success-path resumes use the neutral fact-query trigger. Only the start-failure path's host resume receives a fixed responsibility prompt: query Harness facts, state that the investigator did not start and produced no execution result, avoid claiming the delegation was fulfilled or replacing its work, and limit the response to reporting the blockage plus unexecuted options or a decision request. This is an Agent prompt weak constraint, not a Harness-enforced semantic guarantee; the unredacted review bundle still requires independent review of the host's actual response.
- Runner evidence contains a redacted command shape and normalized structural facts only. It omits prompts, session IDs, paths, environment values, MCP configuration bodies, stderr text, Agent result text, message bodies, and delegation bodies. Raw stdout and stderr exist only in process memory while parsing.
- Only the observed Codex JSONL shape `event.type="item.completed"` with `item.type="error"` records a normalized warning diagnostic rather than a tool call; its free-form message is neither retained nor used for classification. The same item under any other event type fails closed, top-level `error` and `turn.failed` remain hard failures, and unknown item types remain unexpected built-ins.

## Cleanup

Tests create workspaces, fake executables, and evidence under `TemporaryDirectory`; they are removed on test exit. Real Probe workspaces, state, facts, and evidence directories are owned by the entry point's temporary run directory and are removed when that context exits. The caller-owned sanitized summary and unredacted temporary review bundle remain for review; securely delete the review bundle immediately afterward. The success run has a 30-minute total deadline, the failure run a 10-minute total deadline, and each call receives the smaller of five minutes or the remaining total time. On timeout or another exception after process start, the runner terminates and reaps the process group before returning or re-raising. The runner does not delete the CLIs' own persisted session records, because explicit resume requires those records during the Probe.
