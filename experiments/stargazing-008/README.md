# Stargazing 8 disposable probes

These files are feasibility probes, not production adapters, schedulers, sandboxes, or a promise that either Agent CLI is isolated.

## Verification without Agent usage

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  experiments/stargazing-008/test_contracts.py \
  experiments/stargazing-008/test_stop_controller.py \
  experiments/stargazing-008/test_scheduler_probe.py \
  experiments/stargazing-008/test_real_cli_probe.py
```

Task 4 uses only fake CLI executables, but each fake parses the complete product command and launches the
real disposable `blocking_mcp.py` process in the Harness-created process group. It performs the current
`initialize` / `notifications/initialized` / `tools/list` / `tools/call` STDIO exchange and calls the one
hold tool; it does not fabricate MCP ready/effect facts. It must not start `codex` or `claude`.
Its Agent-call budget and model-token budget are both exactly zero. Ordinary fake runs have a 10-second ready
deadline, a 0.04-second graceful deadline, and a 0.7-second cleanup/reap deadline in the test fixture;
these are high-load fixture bounds, not proposed production defaults. Task 5 uses a separately precommitted 60-second
real ready deadline. The explicit missing-ready negative uses a
shorter 0.2-second bound. The 3-second bound avoids treating normal sub-second-to-low-second process startup
jitter as an MCP failure; readiness still comes only from the real MCP ledger.

## Safety boundary and real-run gate

The Task 5 real probe was allowed only after an independent readiness review and a fresh check of CLI versions, help text, and the exact tool surface. It used a fresh temporary Git workspace, one startup-bound `sg8` MCP server exposing only `hold_until_stopped`, fixed artificial input, command arrays with `shell=False`, a total deadline, and identity-guarded process-group cleanup. No business tool, repository workspace, credential, arbitrary URL, notification, deployment, or irreversible external action was in scope. Read-only and restricted flags are bounded observations, not full filesystem or network isolation guarantees.

During the separately authorized Task 5 run, unredacted stdout/stderr and command evidence was written by the caller to a fresh repository-external temporary file created with mode `0600`; the real entry could not start without that target. The audit includes only a sanitized command shape, CLI/MCP/observed PID and PGID facts, requested signal layers and relative monotonic timing, deadline configuration/expiry, return code, elapsed time, per-PID/group confirmation, cleanup outcome, and raw stdout/stderr. The structured control fields contain no command path, workspace path, prompt, environment value, or token; the raw streams may contain sensitive Agent output and are the reason the file is restricted to `0600`. It may be inspected only for the independent evidence review, must never enter Git or sanitized output, and must then be deleted. Sanitized summaries contain only product/version enums, stop layer, terminal presence, result/slot/retry states, bounded side-effect scopes, process-group confirmation, event counts, and decision-escalation state. They never contain prompts, session identifiers, private paths, environment values, raw output, prose, credentials, or tokens.

Stop immediately and fail closed on a missing or extra MCP/tool event, unknown machine shape, unexpected child or PGID, early completion, timeout, inability to reap or confirm the group, unexpected path effect, or any safety-boundary crossing. Never retry automatically. Cleanup removes only fixed probe-owned files; temporary directories remain caller-owned.

Codex JSONL and Claude stream-json are parsed separately against the exact event structures already used
by the Stargazing 6 fixtures. A terminal is recognized only from the product's explicit terminal machine
event; an exit code never creates a terminal fact. The CLI leader is the process-group identity anchor.
Hard, emergency, and final cleanup reuse the Task 2 identity checks; they never send a nonzero signal to a
bare PID. If the leader identity is lost while an observed MCP PID remains, cleanup is incomplete, evidence
is preserved, and no released-slot result exists. Both workspace and evidence directories are audited again
after stop so a late unknown write also fails closed.

`run_real_cli_probe` is a separate gated entry point. Its caller supplies the launch environment without
logging values; fake-only variables are rejected. It requires a passing version/help preflight, exact fixed
MCP argv, and a positive total Agent-run deadline. Safety cleanup may continue after that run deadline.
For Codex, the preflight must also confirm that every currently relevant non-MCP tool-capable feature named
by the probe still exists; the command uses strict config, an ephemeral session, and explicitly disables each
one while leaving only the fixed `sg8` MCP tool configured. For Claude, the command disables session
persistence and permission prompts and sets `--max-budget-usd 0.10`. Stargazing 3 showed that this budget
flag is a soft after-the-fact ceiling which may be exceeded by the first model call; it is not a hard budget
guarantee and the real run remains bounded primarily by one invocation and the wall-clock deadline.
Every started success or failure makes a best-effort audit write. Raw-write failure is surfaced separately;
it cannot replace an original interruption or cleanup outcome.

The disposable MCP server accepts and echoes only protocol versions `2025-03-26` and `2025-06-18`.
These are the Stargazing 6 evidenced version and the current Task 4 candidate fixture, not a claim of
compatibility with every MCP protocol version.

Task 5 had no inherited permission to run. Before the one-shot Codex call, its independent readiness
review recorded an exact total wall-clock deadline and the available CLI-native budget boundary.
If the current CLI cannot enforce a token ceiling, that gap is `uncovered`: the run is bounded only by one
invocation plus the precommitted wall-clock stop and must not be described as having a hard token budget.

## Task 5 observed boundary

The first Codex attempt failed before MCP startup because the surrounding desktop sandbox made the CLI's local state database read-only. Its raw evidence was independently reviewed and deleted. A second, explicitly authorized run outside that sandbox reached the one fixed MCP hold call, but the CLI and MCP server were in different process groups. The probe failed closed before sending the normal stop request: it cleaned the CLI group but correctly refused to claim that the separately grouped MCP process had stopped. An independent operator verified the exact fixed MCP command identity, sent `TERM` only to that MCP process group, and confirmed it disappeared.

This negative result rejects the probe's single-parent-PGID assumption. It does not prove Codex cancellation failed, and it does not permit a released-slot summary for the whole execution. A product adapter must enumerate and retain every controlled execution group or an explicit external cancellation handle before it can confirm the corresponding scope stopped. The Claude Code SG8 real run was not started after this safety boundary was crossed; Stargazing 3 remains prior evidence, not a Task 5 substitute.

Both Codex raw review files were independently reviewed and deleted. Their locations and contents were intentionally not documented here and were never committed or shared. The two dedicated temporary workspaces and evidence directories were also deleted after their bounded contents were checked.
