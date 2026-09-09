# Stargazing 8 Stop, Disable, and Guarantee Experiment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine which stop, role-capacity, disable, side-effect, permission, and budget claims the Harness can honestly make, using a deterministic process baseline followed by a bounded real Codex/Claude comparison.

**Architecture:** Disposable Python probes share one small, fixed observation contract but keep three responsibilities separate: process-group control, Harness scheduling/disable decisions, and side-effect reconciliation. Probe 8.1 uses synthetic workers to force both graceful and escalated stop paths; Probe 8.2 uses product-specific command builders plus one blocking synthetic MCP tool to observe real CLI behavior without granting business tools or using a real project.

**Tech Stack:** Python 3 standard library (`subprocess`, `signal`, `sqlite3`, `tempfile`, `unittest`), POSIX process groups on the verified macOS coordinate, JSON Lines observer ledgers, current Codex CLI and Claude Code CLI.

---

This is throwaway feasibility code, not a production scheduler, state machine, sandbox, process supervisor, remote cancellation protocol, compensation engine, or database choice. It must not modify Stargazing 2–7 experiments. No commit or push is part of this plan unless the user separately requests it.

### Task 1: Freeze the shared observation contract

**Files:**

- Create: `experiments/stargazing-008/contracts.py`
- Create: `experiments/stargazing-008/test_contracts.py`

- [x] Write failing tests for three fixed summaries: `graceful_stopped` with a reliable synthetic terminal, `graceful_stopped_unknown` where the process stops before the deadline but emits no reliable terminal, and `force_stopped` with no terminal and `result_unknown`.
- [x] Require distinct fields for `stop_request`, `stop_confirmation`, `terminal_state`, `result_state`, `slot_state`, `retry_eligibility`, `side_effects`, and `decision_escalation`; reject a single overloaded `cancelled` field.
- [x] Require side effects to contain exactly three fixed scopes: `harness_recorded`, `workspace_observed`, and `external_uncovered`. Each scope carries `visibility` and a bounded state; no scope may imply quality, completeness, rollback, or universal absence.
- [x] Require unknown side effects to produce one fixed, sanitized `decision_escalation` fact targeted to `responsible_actor`, with no real message send and no automatic decision, retry, rollback, or compensation.
- [x] Add failing contradictions: released slot without confirmed stop, retry allowed with unknown result or unknown side effect, unknown side effect without decision escalation, force stop without a prior graceful request/deadline, and a terminal result fabricated from process exit.
- [x] Implement only fixed validators and sanitized summary builders. Do not add a generic workflow/status framework.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v experiments/stargazing-008/test_contracts.py`; require all focused tests to pass.

The minimum successful shapes are semantically equivalent to:

```python
{
    "stop_request": "graceful",
    "stop_confirmation": "controlled_group_stopped",
    "terminal_state": "cancelled",
    "result_state": "cancelled",
    "slot_state": "released",
    "retry_eligibility": "blocked",
    "decision_escalation": "responsible_actor_required",
}
```

and:

```python
{
    "stop_request": "force_after_deadline",
    "stop_confirmation": "controlled_group_stopped",
    "terminal_state": None,
    "result_state": "result_unknown",
    "slot_state": "released",
    "retry_eligibility": "blocked",
    "decision_escalation": "responsible_actor_required",
}
```

Here `cancelled` in the first shape is allowed only because the synthetic worker emitted a reliable terminal fact; it is never inferred from the process exit.

The real CLI may stop during the graceful deadline without emitting a terminal. That fixed shape keeps the first stop-request object (`deadline_expired=false`, `force_requested=false`) but sets `terminal_state=None`, `terminal_evidence=None`, and `result_state="result_unknown"`; it must not be rejected or silently converted into the force shape.

### Task 2: Prove the deterministic stop and side-effect baseline

**Files:**

- Create: `experiments/stargazing-008/fake_worker.py`
- Create: `experiments/stargazing-008/stop_controller.py`
- Create: `experiments/stargazing-008/test_stop_controller.py`

- [x] Write a failing graceful-path test. The fake worker creates a fixed marker in a temporary workspace, records one fixed Harness-mediated effect, starts one child in the same process group, reports ready PIDs, and on the graceful signal stops its child, writes a reliable synthetic terminal, and exits.
- [x] Assert the controller sends one graceful request, observes the whole controlled process group stop before the deadline, never sends force, releases the slot, preserves the terminal result, reports the marker and Harness fact, leaves external effects `uncovered/unknown`, blocks automatic retry, and records one decision escalation without sending a real notification or making the decision.
- [x] Write a failing escalation test. The fixed worker and child ignore the graceful signal; after a short deterministic deadline the controller must send a force signal to the exact process group, reap the leader, and verify every recorded PID is gone before releasing the slot.
- [x] Assert the escalation result has no terminal, uses `result_unknown`, observes the same bounded side effects, keeps external effects unknown, records one decision escalation, records force only after the deadline, and leaves the Adapter dispatch ledger at one call with zero redispatch.
- [x] Add failure cases for missing ready evidence, malformed PID/PGID facts, a surviving recorded child, missing effect ledger, and inability to confirm the group stopped. All fail closed without reporting a released slot.
- [x] Implement argument-array subprocess calls with `shell=False`, `start_new_session=True`, exact PID/PGID targeting, monotonic deadlines, bounded waits, and final cleanup that never uses process-name matching.
- [x] Run the focused tests and scan for live test processes plus repository-local generated artifacts.

The worker may write only fixed artificial values below a `TemporaryDirectory`. It must never receive a repository workspace, prompt, credential, arbitrary command, URL, or external-service endpoint.

### Task 3: Prove Harness-level capacity and role disable decisions

**Files:**

- Create: `experiments/stargazing-008/scheduler_probe.py`
- Create: `experiments/stargazing-008/test_scheduler_probe.py`

- [x] Write failing tests for two fixed ordinary roles with capacity one each: different roles may hold one active execution simultaneously, while a second execution for the same role remains pending and is not dispatched.
- [x] Write a failing test showing confirmed stop releases only the stopped role's slot: a new, distinct attempt for that same role can be dispatched while another role's existing active fact remains unchanged; the old unknown attempt remains retry-blocked and is never redispatched.
- [x] Write failing role-disable tests: disabling an ordinary role blocks new dispatch; graceful disable allows the already active fake execution to finish; force disable invokes the same stop controller and does not invent an execution terminal; re-enable preserves the same logical role and permits new work.
- [x] Add fixed protected-role negative cases: a role carrying `host` or `supervisor` cannot be disabled until the label is transferred. Keep this a deterministic Harness rule, not an Agent prompt.
- [x] Implement the smallest single-process scheduler fact model needed by these tests. Do not implement priority, fairness, generic queues, distributed locks, database persistence, or production concurrency configuration.
- [x] Run focused scheduler tests and the complete Probe 8.1 suite.

This task may establish only that Harness-owned dispatch decisions can enforce the artificial capacity and disable rules. It does not prove that an Agent cannot start unobserved native work outside Harness dispatch.

### Task 4: Preflight the real CLI stop comparison

**Files:**

- Create: `experiments/stargazing-008/blocking_mcp.py`
- Create: `experiments/stargazing-008/real_cli_probe.py`
- Create: `experiments/stargazing-008/test_real_cli_probe.py`
- Create: `experiments/stargazing-008/README.md`

- [x] Record current `codex --version`, `claude --version`, relevant local help, and the exact allowed tool surface immediately before any Agent run. Store only version/shape facts, never credentials, config contents, environment values, private paths, prompts, or raw model output.
- [x] Write failing protocol tests for a role-bound STDIO MCP server exposing only `hold_until_stopped`. On the one valid call it writes a fixed ready/effect ledger record containing its own PID and PGID, creates one fixed marker in the dedicated temporary evidence directory, then remains in progress until its process is stopped; identity and paths come from server startup, not Agent arguments.
- [x] Write failing command-builder tests. Codex must use a temporary Git workspace, JSONL, read-only, ignored user/rule configuration, disabled shell, one required `sg8` MCP server, and only the hold tool. Claude must use restricted mode, strict MCP config, disabled slash commands, an empty built-in tool set, only `mcp__sg8__hold_until_stopped`, `dontAsk`, and stream-json.
- [x] Write fake-executable tests for the live controller: wait for the MCP ready ledger, require the CLI leader and MCP PID to share the exact Harness-created PGID, request product-specific graceful stop, observe until a fixed deadline, escalate only if still alive, reap the process group, confirm the CLI leader, recorded MCP PID, and every other explicitly observed child are gone, parse only known machine events, and classify missing terminal as `result_unknown`.
- [x] Require each sanitized result to use the Task 1 observation contract and contain only product/version enums, stop layer, terminal presence, result state, slot state, retry eligibility, bounded side-effect states, process-group confirmation, and event counts.
- [x] Add fail-closed tests for Agent completion before the hold tool, MCP not loaded, tool not called, MCP PID outside the expected PGID, any recorded child surviving, unexpected tool/event, malformed output, start failure, timeout, group not confirmed stopped, and unknown parser shapes. None may report a released slot.
- [x] Document the exact safety boundary, run commands, time/token ceilings, sanitized summary, temporary unredacted review evidence handling, cleanup, and stop conditions. Do not start a real Agent during this task.
- [x] Run all fake/protocol tests and obtain independent run-readiness review before Task 5.

### Task 5: Run one bounded stop Probe for each real CLI

**Files:**

- Modify: `docs/stargazing/008-concurrency-cancellation-and-guarantees.md`
- Modify only if evidence requires it: `experiments/stargazing-008/real_cli_probe.py`
- Modify only with a new failing test first: `experiments/stargazing-008/test_real_cli_probe.py`

- [x] Recheck versions and command/tool surfaces. Stop if they differ materially from the tested preflight or if the restricted surface cannot be constructed.
- [x] Create fresh temporary Git workspaces and caller-owned `0600` unredacted review files outside the repository; use only the fixed artificial prompt and blocking MCP tool.
- [x] Run Codex once. Stop if it invokes an unexpected tool, reads or writes an unexpected path, contacts a non-model external service, emits an unknown machine event, exceeds the time ceiling, or cannot be reaped. Never retry automatically.
- [x] Independently review Codex raw evidence, then retain only a sanitized structural summary and delete the raw review file.
- [ ] Run Claude Code once under the same evidence contract and stop conditions; do not require it to use the same signal or exit-code semantics as Codex.
- [ ] Independently review Claude raw evidence, retain only the sanitized structural summary, and delete the raw review file.
- [x] If a real run reveals a probe defect, preserve the failed observation in the Stargazing record, add a failing regression test before the smallest fix, repeat only when the failure did not cross a safety boundary, and never rewrite the acceptance rule to fit Agent output.
- [x] Record observed stop layer, CLI/MCP process-group evidence, terminal presence, result classification, slot release, retry block, decision escalation, bounded side-effect evidence, usage observations, and all limitations without retaining prompts, session ids, private paths, environment values, stderr, or Agent prose.

Task 5 以安全反证停止：Codex 真实运行证明 CLI 与 MCP 位于不同独立进程组，统一父 PGID 前提不成立，因此未继续 Claude Code 的 SG8 实跑。两次 Codex 原始证据均已独立审阅并删除；Claude Code 的运行与原始证据审阅 checkbox 保持未完成，是安全门禁触发后的明确实验边界，不以勾选清单掩盖。

Real runs are evidence collection, not an implementation success requirement. A safe failure or inability to construct the promised restricted surface remains a valid negative result.

### Task 6: Build the guarantee matrix and conclude Stargazing 8

**Files:**

- Modify: `docs/stargazing/008-concurrency-cancellation-and-guarantees.md`
- Modify: `docs/stargazing/README.md`
- Modify: `docs/stargazing/logbook.md`
- Modify: `docs/stargazing/plan.md`
- Modify: `CHANGELOG.md`

- [x] Build a matrix for dispatch/capacity, graceful stop, force stop, stop confirmation, execution result, Harness-mediated effects, workspace changes, Agent-direct external effects, decision escalation, role disable, workspace permissions, tool surface, network, token/cost observation, and hard budget.
- [x] For every row state the evidence source, scope, guarantee class (`Harness strong`, `OS/external conditional`, `weak constraint`, or `uncovered`), and what cannot be inferred.
- [x] Reuse Stargazing 2/3/6/7 evidence for cross-role minimum concurrency, per-product cancellation, permissions, tool surfaces, result unknown, and budget limits; do not relabel old observations as newly run SG8 experiments.
- [x] Decide whether Probe 8.1 and 8.2 satisfy the core gate. Add no new Probe unless one exact missing fact blocks an honest matrix conclusion; write its hypothesis and disproof before implementation.
- [x] Record one conclusion: `可行`, `有条件可行`, `不可行`, or `未决`, with current versions, conditions, negative evidence, and unresolved remote/production boundaries.
- [x] Update all Stargazing status documents and the notebook-style changelog; do not start Stargazing 9.
- [x] Run all Stargazing 8 tests, relevant Stargazing 5–7 regressions, both reproducible sanitized probe entries that do not spend Agent tokens, `git diff --check`, generated-file scans, and an independent final evidence review.

最终验证已完成：Stargazing 8 共 79 项测试通过，Stargazing 5–7 分套回归分别为 20、60、21 项通过；两个不调用 Agent 的结构化停止摘要入口、差异检查、生成物与临时目录扫描均通过。独立证据审查与文档收尾审查分别完成，审查提出的准确性问题已修正并复核通过。“以负面证据收束”来自预设门禁与独立审查，不是作者自行批准。

The likely shape is a conditional conclusion, but the experiments may disprove it. Completion means the matrix is honest and evidence-backed, not that every row is strongly controlled.
