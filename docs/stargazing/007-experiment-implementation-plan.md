# Stargazing 7 Process-Restart Recovery Experiment Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove or disprove that committed Harness facts can survive a process restart and that an accepted execution without a reliable terminal fact is recovered exactly once as `result_unknown` without automatic redispatch.

**Architecture:** A disposable Python probe stores synthetic thread facts in SQLite, calls a deterministic fake Adapter with a separate append-only acceptance ledger, and intentionally exits after the Adapter-accepted fact is committed. Fresh Python processes then recover the same database twice, allowing tests to verify classification, no redispatch, no fabricated result, and idempotency without a real Agent.

**Tech Stack:** Python 3 standard library (`sqlite3`, `subprocess`, `tempfile`, `unittest`), SQLite transactions, JSON Lines fake-Adapter ledger.

---

This plan implements only the confirmed Probe 7.1. It does not create production storage, a reusable repository layer, real Agent process takeover, crash-safe external side effects, concurrency, schema migration, retry policy, or a general workflow engine. Repository changes remain uncommitted until the user separately requests a commit.

### Task 1: Define the durable synthetic facts

**Files:**

- Create: `experiments/stargazing-007/store.py`
- Create: `experiments/stargazing-007/test_store.py`

- [x] Write a failing test that creates a new database and expects exactly two fixed roles, one synthetic delegation, one execution attempt, and append-only fact events after reopening it through a new `RecoveryStore` instance.
- [x] Require the execution attempt to keep separate `dispatch_state`, nullable `terminal_state`, and nullable `recovery_state` fields; do not overload one status field with incompatible meanings.
- [x] Add failing tests proving duplicate role, delegation, attempt, acceptance, terminal, and recovery facts are rejected or idempotent according to their fixed operation; rejected writes must leave prior state unchanged.
- [x] Implement the smallest SQLite schema and explicit transaction methods. Each public mutation opens or uses a transaction that commits before returning; foreign keys are enabled for every connection.
- [x] Reopen the database in a fresh store object and verify relationships, event sequence, and absence of messages, Agent results, delegation completion, and acceptance facts not explicitly written.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v experiments/stargazing-007/test_store.py`; expect all focused tests to pass.

The experimental attempt shape is semantic evidence, not a product schema:

```python
{
    "attempt_id": "attempt-1",
    "delegation_id": "delegation-1",
    "role_id": "worker-agent",
    "dispatch_state": "accepted",
    "terminal_state": None,
    "recovery_state": "result_unknown",
}
```

### Task 2: Record one deterministic Adapter acceptance

**Files:**

- Create: `experiments/stargazing-007/fake_adapter.py`
- Create: `experiments/stargazing-007/test_fake_adapter.py`

- [x] Write a failing test that invokes the fake Adapter with `attempt-1`, reads one machine JSON response with `accepted=true`, and finds exactly one JSONL call entry containing only a fixed sequence, the fixed attempt id and `accepted` outcome.
- [x] Add a failing duplicate test proving a second dispatch appends a second call entry with `duplicate` outcome and returns a duplicate error rather than a second acceptance. The ledger must expose total call count, accepted count, and duplicate count independently.
- [x] Implement a CLI that accepts only `--ledger` and `--attempt-id`, refuses non-fixed attempt ids for this probe, appends and flushes one record for every valid invocation, and returns machine JSON.
- [x] Keep the ledger free of prompts, credentials, workspace paths, environment values, session ids, message bodies, and arbitrary Agent text.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v experiments/stargazing-007/test_fake_adapter.py`; expect all focused tests to pass.

### Task 3: Crash only after the accepted fact is committed

**Files:**

- Create: `experiments/stargazing-007/crash_worker.py`
- Create: `experiments/stargazing-007/test_crash_worker.py`

- [x] Write a failing subprocess test that starts `crash_worker.py`, requires the agreed experiment exit code, then opens the database from the parent process.
- [x] Assert the parent observes the fixed roles, delegation, attempt, one Adapter acceptance, `dispatch_state=accepted`, no terminal, no recovery marker, and one Adapter-ledger acceptance.
- [x] Implement the worker sequence: initialize committed facts, call the fake Adapter directly as an argument array with `shell=False`, validate its machine response and exit, commit the accepted fact, then call `os._exit(73)`.
- [x] Add timeouts and fail closed on malformed Adapter output, nonzero exit, duplicate acceptance, wrong attempt id, or inability to confirm the database commit. None of these failures may be converted into the planned crash evidence.
- [x] Run the focused test and confirm exit `73` occurs only after the parent can reopen and observe the accepted fact.

### Task 4: Recover as unknown without redispatch

**Files:**

- Create: `experiments/stargazing-007/recover_worker.py`
- Create: `experiments/stargazing-007/test_recovery.py`

- [x] Write a failing test that prepares the post-crash database, starts a fresh `recover_worker.py`, and expects `result_unknown` rather than any terminal state.
- [x] Assert recovery does not execute `fake_adapter.py`: the Adapter ledger remains exactly one total call, one `accepted`, and zero `duplicate`; no new attempt, message, Agent result, completion, acceptance, or target fact appears.
- [x] Add a failing test that runs recovery in a third process and expects the same machine summary, the same fact counts, and exactly one `execution_recovered_unknown` event.
- [x] Add negative fixtures: no Adapter acceptance remains pre-dispatch and is not mislabeled result unknown; a reliable terminal fact remains terminal and is not overwritten; malformed/inconsistent state fails closed without mutation.
- [x] Implement deterministic recovery from persisted Harness database fields only. Do not inspect process state, Agent prose, timestamps, stdout, stderr, or the Adapter ledger to infer the Harness recovery classification; the ledger is observer evidence only.
- [x] Run the focused recovery tests and confirm all pass.

### Task 5: Assemble the reproducible Probe 7.1

**Files:**

- Create: `experiments/stargazing-007/run_probe.py`
- Create: `experiments/stargazing-007/test_run_probe.py`
- Create: `experiments/stargazing-007/README.md`

- [x] Write a failing end-to-end test that creates one `TemporaryDirectory`, runs crash, first recovery, and second recovery as three separate processes, and expects a sanitized structural summary.
- [x] Require the summary to contain only schema version, planned crash observed, restored fact counts, fixed enum states, Adapter total-call/accepted/duplicate counts, unknown-event count, redispatch count, and idempotency result.
- [x] Implement the runner without shell invocation. Every child gets an explicit timeout; paths, raw SQLite contents, environment values, prompts, credentials, stdout/stderr text, and arbitrary payloads are excluded from the summary.
- [x] Document exact local verification and manual probe commands, expected structural output, cleanup, and the distinction between process restart evidence and power-loss durability.
- [x] Run all Stargazing 7 tests and `git diff --check`; verify no `__pycache__`, `.pyc`, database, WAL, SHM, ledger, summary, or temporary directory remains in the repository.

### Task 6: Evaluate evidence and decide whether another probe is necessary

**Files:**

- Modify: `docs/stargazing/007-persistence-restart-and-unknown-outcome.md`
- Modify: `docs/stargazing/README.md`
- Modify: `docs/stargazing/logbook.md`
- Modify: `docs/stargazing/plan.md`
- Modify: `CHANGELOG.md`

- [x] Independently review committed database facts, child-process evidence, the Adapter ledger count, recovery summaries, negative cases, and absence of redispatch or fabricated results.
- [x] Decide whether Probe 7.1 alone satisfies the Stargazing 7 core gate. If not, write the exact remaining hypothesis and disproof before implementing only the necessary Probe 7.2 or 7.3.
- [x] Record observations, limitations, failed attempts, conditions, and one conclusion: `可行`, `有条件可行`, `不可行`, or `未决`.
- [x] Update all Stargazing status documents and the notebook-style changelog; do not start Stargazing 8.
- [x] Run Stargazing 7 tests, relevant Stargazing 5/6 regression tests, `git diff --check`, generated-file checks, and an independent final reviewer pass before claiming completion.
