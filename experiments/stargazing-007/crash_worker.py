import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from store import RecoveryStore


PLANNED_CRASH_EXIT_CODE = 73
ATTEMPT_ID = "attempt-1"


class WorkerFailure(RuntimeError):
    pass


def initialize_fixed_facts(store):
    store.initialize_schema()
    store.add_role("host-agent", "host")
    store.add_role("worker-agent", "worker")
    store.add_delegation("delegation-1", "host-agent", "worker-agent")
    store.add_attempt(ATTEMPT_ID, "delegation-1", "worker-agent")


def verify_committed_acceptance(database_path):
    snapshot = RecoveryStore(database_path).snapshot()
    if len(snapshot["attempts"]) != 1:
        raise RuntimeError("accepted fact commit could not be confirmed")
    attempt = snapshot["attempts"][0]
    if (
        attempt["attempt_id"] != ATTEMPT_ID
        or attempt["dispatch_state"] != "accepted"
        or attempt["terminal_state"] is not None
        or attempt["recovery_state"] is not None
        or snapshot["counts"]["acceptances"] != 1
    ):
        raise RuntimeError("accepted fact commit could not be confirmed")
    return snapshot


def invoke_adapter(adapter_command, ledger_path):
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(adapter_command),
                "--ledger",
                str(ledger_path),
                "--attempt-id",
                ATTEMPT_ID,
            ],
            shell=False,
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise WorkerFailure("adapter_timeout") from error
    if result.returncode != 0:
        raise WorkerFailure("adapter_nonzero_exit")
    try:
        response = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as error:
        raise WorkerFailure("adapter_output_invalid") from error
    expected = {
        "accepted": True,
        "attempt_id": ATTEMPT_ID,
        "outcome": "accepted",
    }
    if response != expected:
        raise WorkerFailure("adapter_response_rejected")
    return response


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--adapter-command", required=True)
    arguments = parser.parse_args(argv)

    database_path = Path(arguments.database)
    try:
        store = RecoveryStore(database_path)
        initialize_fixed_facts(store)
        invoke_adapter(Path(arguments.adapter_command), Path(arguments.ledger))
        if not store.record_acceptance(ATTEMPT_ID):
            raise WorkerFailure("database_acceptance_duplicate")
        verify_committed_acceptance(database_path)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        error_kind = error.args[0] if isinstance(error, WorkerFailure) else "worker_failed_closed"
        print(json.dumps({"planned_crash": False, "error": error_kind}))
        return 1

    os._exit(PLANNED_CRASH_EXIT_CODE)


if __name__ == "__main__":
    raise SystemExit(main())
