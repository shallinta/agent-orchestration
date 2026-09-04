# Stargazing 6 Minimal Continuous Collaboration Experiment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce reproducible success and executor-start-failure evidence for one Codex-hosted, Claude-executed collaboration loop without human message forwarding.

**Architecture:** A disposable Python controller owns an append-only synthetic thread state and invokes two product-specific CLI runners. Each Agent receives a role-specific STDIO MCP server backed by the same run state; the controller routes only recorded delegations, messages, and call faults, while semantic delegation, follow-up, and conclusion remain Agent outputs.

**Tech Stack:** Python 3 standard library, newline-delimited JSON-RPC STDIO MCP, Codex CLI `0.144.6`, Claude Code CLI `2.1.260` at the accepted real runs, JSON/JSONL fixtures and evidence.

---

This plan implements only the approved Stargazing experiment. It does not create production source code, a database, restart recovery, automatic retry, concurrency, a general state machine, or a reusable Agent framework. Repository work remains uncommitted until the user separately requests a commit.

### Task 1: Freeze the Agent-visible scenario

**Files:**

- Create: `experiments/stargazing-006/scenario.json`
- Create: `experiments/stargazing-006/test_scenario.py`
- Modify: `docs/stargazing/006-minimal-continuous-collaboration-loop.md`

- [x] Write a failing test that loads `scenario.json`, requires evidence IDs `E01` through `E18` exactly once, requires non-empty goal and acceptance criteria, rejects an `oracle` field, and checks that canonical JSON produces one stable SHA-256.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest experiments/stargazing-006/test_scenario.py -v`; expect failure because the fixture is absent.
- [x] Add the exact artificial evidence and acceptance requirements already approved in the Stargazing 6 record. Keep the observer oracle out of the fixture.
- [x] Re-run the test and record the fixture SHA-256 in the Stargazing 6 document before any Agent starts.

The canonical digest function is fixed as:

```python
def canonical_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

### Task 2: Build the shared synthetic Harness facts

**Files:**

- Create: `experiments/stargazing-006/harness_state.py`
- Create: `experiments/stargazing-006/test_harness_state.py`

- [x] Write failing tests for a fresh run containing exactly `host-codex` and `investigator-claude`, no messages or delegations, and a fixed scenario digest.
- [x] Add failing tests proving only `host-codex` can publish the single investigation delegation to `investigator-claude`; both roles can send directed messages; caller identity is supplied to the state API by trusted server construction and is rejected inside payloads.
- [x] Add failing tests for controller-owned execution attempts and `agent_start_failed` events. Such a fault must not create a role message, Claude session, delivery, completion, or Agent result.
- [x] Add failing tests for append-only event sequence numbers, unique Harness request IDs, payload SHA-256, and logs that omit message bodies, delegation bodies, prompts, credentials, session IDs, arbitrary target strings, and workspace paths.
- [x] Implement the smallest file-backed state using an explicit state path created for one run. Write through a sibling temporary file followed by `os.replace`; do not claim crash durability or concurrent-write safety.
- [x] Run the focused tests and confirm every rejected operation leaves the prior state unchanged.

Minimum stored entities are exact JSON objects with these fields:

```json
{
  "delegation": {
    "delegation_id": "delegation-1",
    "publisher_role_id": "host-codex",
    "target_role_id": "investigator-claude",
    "task": "agent-authored text",
    "request_id": "req-..."
  },
  "message": {
    "message_id": "message-1",
    "sender_role_id": "investigator-claude",
    "target_role_id": "host-codex",
    "body": "agent-authored text",
    "request_id": "req-..."
  },
  "execution_attempt": {
    "execution_attempt_id": "attempt-...",
    "role_id": "investigator-claude",
    "trigger_kind": "delegation",
    "trigger_id": "delegation-1",
    "outcome": "start_failed"
  }
}
```

### Task 3: Expose role-specific MCP tools

**Files:**

- Create: `experiments/stargazing-006/harness_mcp.py`
- Create: `experiments/stargazing-006/test_harness_mcp.py`

- [x] Write protocol tests for `initialize`, `notifications/initialized`, `ping`, `tools/list`, and `tools/call`, including current clients' protocol-level `_meta` behavior learned in Stargazing 5.
- [x] Require server startup arguments `--state`, `--log`, and `--caller-role`; validate `--caller-role` against the two fixed roles before serving.
- [x] Expose only `query_thread`, `publish_delegation`, and `send_message`. Tool arguments must use `additionalProperties:false` and contain no caller, session, execution-attempt, or authority field.
- [x] Make `query_thread` return the frozen scenario plus current directed messages, delegation, and controller-owned call faults. Do not return the hidden oracle.
- [x] Return structured success and business errors with a Harness request ID; write only normalized server facts to JSONL.
- [x] Run tests through the real STDIO process and verify result request IDs exactly match server facts.

### Task 4: Implement deterministic routing with fake runners

**Files:**

- Create: `experiments/stargazing-006/controller.py`
- Create: `experiments/stargazing-006/test_controller.py`

- [x] Define a runner boundary that accepts role, start/resume mode, optional session ID, neutral trigger text, workspace, MCP command, timeout, and run evidence directory; it returns parsed session ID, machine events, final Agent result, process exit fact, and usage observations.
- [x] Write a fake-runner success test with five turns: host start, investigator start, host resume, investigator resume, host resume. Each fake turn must emit the structural tool call that creates the next Harness fact; the controller may only inspect state types and target roles.
- [x] Assert the controller passes the host-authored delegation unchanged to the investigator, wakes the host only after an investigator message, and wakes the investigator only after a host message. Compare canonical payload digests at send and delivery.
- [x] Assert the controller never contains a fixed delegation body, follow-up body, root-cause phrase, containment recommendation, or final conclusion.
- [x] Add failure tests for host not delegating, investigator not reporting, host not sending any follow-up message, wrong sender/target, duplicate delivery, session drift, extra-turn limit, and uncorrelated request IDs. Whether a non-empty follow-up is genuinely targeted remains an independent post-run semantic review, not controller logic.
- [x] Add the start-failure fake test: after a real host-authored delegation, runner raises `FileNotFoundError`; controller records one `agent_start_failed`, resumes the same host session, and creates no Claude result or message.
- [x] Implement the minimum event-driven sequence. Natural-language semantic grading must remain a post-run reviewer responsibility; the controller may enforce only structural evidence and hard limits.

### Task 5: Implement product-specific real CLI runners

**Files:**

- Create: `experiments/stargazing-006/agent_runners.py`
- Create: `experiments/stargazing-006/test_agent_runners.py`
- Create: `experiments/stargazing-006/README.md`

- [x] Write parser tests using artificial Codex JSONL and Claude stream-json fixtures. Verify session IDs, MCP tool events, terminal results, failures, timeouts, exit status, usage, and unexpected non-MCP tool calls remain distinguishable.
- [x] Implement Codex start/resume commands using the Stargazing 2/5 verified read-only, ignore, JSONL, required role-specific MCP and temporary Git workspace baseline. Do not use bypass permissions.
- [x] Implement Claude start/resume commands using the Stargazing 3/5 verified `--restricted`, `--strict-mcp-config`, disabled slash commands, empty built-in tools, explicit allowed MCP tools and `dontAsk`. Do not use safe-mode because the current version removes explicit MCP.
- [x] Launch subprocesses directly with argument arrays and explicit five-minute timeout; never use a shell. Redact commands before writing evidence so prompts, session IDs, paths, environment values, and MCP configuration bodies do not enter committed logs.
- [x] Detect any unexpected shell/file/web tool event and stop the real Probe. Do not auto-retry.
- [x] Document exact local commands, expected run outputs, scope limits, and cleanup behavior in the experiment README.

### Task 6: Run Probe 6A without human forwarding

**Files:**

- Runtime-only: a unique directory created by `tempfile.TemporaryDirectory`
- Modify after run: `docs/stargazing/006-minimal-continuous-collaboration-loop.md`

- [x] Reconfirm macOS architecture and both CLI versions; record drift before running if any coordinate changed.
- [x] Run a fresh accepted controller success mode after preserving all stopped diagnostic runs. After launch, do not manually copy, alter, select, or resend any role content.
- [x] Require distinct host and investigator session IDs, five to seven bounded turns, matching request IDs, original-payload digests, one host delegation, at least one investigator report, at least one subsequent host-to-investigator message, a later investigator response, and final host output.
- [x] Stop on every observed safety rule violation, session drift, duplicate delivery, uncorrelated result, timeout, or need for human content intervention; do not relabel stopped runs as success.
- [x] Preserve a sanitized machine summary containing structural facts and digests only; retain raw artificial transcripts only long enough for semantic review and do not commit CLI diagnostic noise.

### Task 7: Run Probe 6B with direct executor start failure

**Files:**

- Runtime-only: a second unique temporary directory
- Modify after run: `docs/stargazing/006-minimal-continuous-collaboration-loop.md`

- [x] Start fresh host sessions and fresh synthetic state for each failure run; require a real host-authored delegation.
- [x] Attempt to launch the investigator with an explicit nonexistent executable path through direct `subprocess.Popen`, producing `FileNotFoundError` before any Claude Agent turn.
- [x] Record exactly one controller-owned start-failure fact and resume the original host session. The initial neutral instruction exposed a semantic failure; the accepted rerun added an explicit host-responsibility prompt weak constraint.
- [x] Verify there is no Claude session/event/result, no synthetic investigator message, no completed/accepted delegation, and no retry or fallback Agent.
- [x] Capture both host final responses and independently preserve the first failure and second pass instead of discarding the negative result.

### Task 8: Reveal the oracle, grade evidence, and close Stargazing 6

**Files:**

- Modify: `docs/stargazing/006-minimal-continuous-collaboration-loop.md`
- Modify: `docs/stargazing/README.md`
- Modify: `docs/stargazing/logbook.md`
- Modify: `docs/stargazing/plan.md`
- Modify: `CHANGELOG.md`

- [x] After both real-run categories ended, append the canonical observer oracle JSON to the Stargazing record and verify its SHA-256 equals the pre-run commitment.
- [x] Grade three dimensions separately: technical routing facts, host autonomous progression, and incident-analysis alignment. Do not use Agent self-assessment for any dimension.
- [x] Record every observed failure, configuration condition, tool surface, session/turn fact, request/payload digest relationship, and unverified guarantee.
- [x] Choose exactly one conclusion: `有条件可行`, using the prewritten thresholds and retaining the prompt-dependent failure-path counterexample.
- [x] Update all Stargazing status documents and the notebook-style changelog. Do not start Stargazing 7.
- [x] Run all Stargazing 5 and 6 tests, `git diff --check`, generated-file checks, and an independent reviewer pass before claiming completion.
