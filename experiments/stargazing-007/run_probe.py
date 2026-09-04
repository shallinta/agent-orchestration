import json
import subprocess
import sys
import tempfile
from pathlib import Path

from store import RecoveryStore


SCHEMA_VERSION = "stargazing-007-probe-v1"
PROBE_DIRECTORY = Path(__file__).resolve().parent
CRASH_WORKER = PROBE_DIRECTORY / "crash_worker.py"
RECOVER_WORKER = PROBE_DIRECTORY / "recover_worker.py"
FAKE_ADAPTER = PROBE_DIRECTORY / "fake_adapter.py"
EXPECTED_RECOVERY_KEYS = {
    "attempt_count",
    "dispatch_state",
    "ok",
    "recovery_state",
    "terminal_state",
    "unknown_event_count",
}


class ProbeFailure(RuntimeError):
    pass


def _run_child(command, timeout):
    try:
        return subprocess.run(
            command,
            shell=False,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ProbeFailure("child_timeout") from error


def _recovery_summary(database_path):
    result = _run_child(
        [sys.executable, str(RECOVER_WORKER), "--database", str(database_path)],
        timeout=5,
    )
    if result.returncode != 0:
        raise ProbeFailure("recovery_failed")
    try:
        summary = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProbeFailure("recovery_output_invalid") from error
    if set(summary) != EXPECTED_RECOVERY_KEYS or summary != {
        "attempt_count": 1,
        "dispatch_state": "accepted",
        "ok": True,
        "recovery_state": "result_unknown",
        "terminal_state": None,
        "unknown_event_count": 1,
    }:
        raise ProbeFailure("recovery_summary_rejected")
    return summary


def _ledger_counts(ledger_path):
    try:
        rows = [json.loads(line) for line in ledger_path.read_text().splitlines()]
    except (OSError, json.JSONDecodeError) as error:
        raise ProbeFailure("ledger_invalid") from error
    allowed_keys = {"sequence", "attempt_id", "outcome"}
    if any(set(row) != allowed_keys for row in rows):
        raise ProbeFailure("ledger_shape_invalid")
    return {
        "total": len(rows),
        "accepted": sum(row["outcome"] == "accepted" for row in rows),
        "duplicate": sum(row["outcome"] == "duplicate" for row in rows),
    }


def run_probe(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    database_path = root / "probe.sqlite3"
    ledger_path = root / "adapter.jsonl"

    crash = _run_child(
        [
            sys.executable,
            str(CRASH_WORKER),
            "--database",
            str(database_path),
            "--ledger",
            str(ledger_path),
            "--adapter-command",
            str(FAKE_ADAPTER),
        ],
        timeout=8,
    )
    if crash.returncode != 73:
        raise ProbeFailure("planned_crash_not_observed")

    first_recovery = _recovery_summary(database_path)
    first_snapshot = RecoveryStore(database_path).snapshot()
    second_recovery = _recovery_summary(database_path)
    second_snapshot = RecoveryStore(database_path).snapshot()
    adapter_counts = _ledger_counts(ledger_path)

    attempt = second_snapshot["attempts"][0]
    unknown_event_count = sum(
        event["event_kind"] == "execution_recovered_unknown"
        for event in second_snapshot["events"]
    )
    redispatch_count = max(adapter_counts["total"] - 1, 0)
    idempotent = (
        first_recovery == second_recovery
        and first_snapshot == second_snapshot
        and unknown_event_count == 1
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "planned_crash_observed": True,
        "fact_counts": {
            "roles": len(second_snapshot["roles"]),
            "delegations": len(second_snapshot["delegations"]),
            "attempts": len(second_snapshot["attempts"]),
            "events": len(second_snapshot["events"]),
            "messages": second_snapshot["counts"]["messages"],
            "agent_results": second_snapshot["counts"]["agent_results"],
            "delegation_completions": sum(
                delegation["completion_state"] is not None
                for delegation in second_snapshot["delegations"]
            ),
            "acceptances": second_snapshot["counts"]["acceptances"],
        },
        "states": {
            "dispatch": attempt["dispatch_state"],
            "terminal": attempt["terminal_state"],
            "recovery": attempt["recovery_state"],
        },
        "adapter_counts": adapter_counts,
        "unknown_event_count": unknown_event_count,
        "redispatch_count": redispatch_count,
        "idempotent": idempotent,
    }


def main():
    try:
        with tempfile.TemporaryDirectory() as directory:
            summary = run_probe(Path(directory))
    except (OSError, IndexError, KeyError, TypeError, ValueError, ProbeFailure):
        return 1
    print(json.dumps(summary, separators=(",", ":"), sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
