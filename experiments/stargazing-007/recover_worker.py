import argparse
import json
import sqlite3
from pathlib import Path

from store import RecoveryStore


ATTEMPT_ID = "attempt-1"


class RecoveryFailure(RuntimeError):
    pass


def _emit(payload):
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)


def _validate_snapshot(snapshot):
    expected_roles = [
        {"role_id": "host-agent", "role_kind": "host"},
        {"role_id": "worker-agent", "role_kind": "worker"},
    ]
    expected_delegations = [
        {
            "delegation_id": "delegation-1",
            "sender_role_id": "host-agent",
            "target_role_id": "worker-agent",
            "completion_state": None,
        }
    ]
    if snapshot.get("roles") != expected_roles:
        raise RecoveryFailure("invalid_roles")
    if snapshot.get("delegations") != expected_delegations:
        raise RecoveryFailure("invalid_delegation")

    attempts = snapshot.get("attempts")
    if not isinstance(attempts, list) or len(attempts) != 1:
        raise RecoveryFailure("invalid_attempt_count")
    attempt = attempts[0]
    if (
        attempt.get("attempt_id") != ATTEMPT_ID
        or attempt.get("delegation_id") != "delegation-1"
        or attempt.get("role_id") != "worker-agent"
        or attempt.get("dispatch_state") not in {"prepared", "accepted"}
        or attempt.get("terminal_state") not in {None, "succeeded", "failed"}
        or attempt.get("recovery_state") not in {None, "result_unknown"}
    ):
        raise RecoveryFailure("invalid_attempt")

    expected_event_kinds = [
        "role_created",
        "role_created",
        "delegation_created",
        "attempt_created",
    ]
    expected_entity_ids = [
        "host-agent",
        "worker-agent",
        "delegation-1",
        ATTEMPT_ID,
    ]
    if attempt["dispatch_state"] == "accepted":
        expected_event_kinds.append("adapter_accepted")
        expected_entity_ids.append(ATTEMPT_ID)
    if attempt["terminal_state"] is not None:
        expected_event_kinds.append("execution_terminal")
        expected_entity_ids.append(ATTEMPT_ID)
    if attempt["recovery_state"] is not None:
        expected_event_kinds.append("execution_recovered_unknown")
        expected_entity_ids.append(ATTEMPT_ID)

    events = snapshot.get("events")
    if not isinstance(events, list):
        raise RecoveryFailure("invalid_events")
    if [event.get("event_kind") for event in events] != expected_event_kinds:
        raise RecoveryFailure("invalid_events")
    if [event.get("entity_id") for event in events] != expected_entity_ids:
        raise RecoveryFailure("invalid_event_entities")
    if [event.get("sequence") for event in events] != list(range(1, len(events) + 1)):
        raise RecoveryFailure("invalid_event_sequence")
    if snapshot.get("counts") != {
        "messages": 0,
        "agent_results": 0,
        "acceptances": int(attempt["dispatch_state"] == "accepted"),
    }:
        raise RecoveryFailure("invalid_counts")
    return attempt


def _summary(snapshot):
    attempt = _validate_snapshot(snapshot)
    return {
        "attempt_count": len(snapshot["attempts"]),
        "dispatch_state": attempt["dispatch_state"],
        "ok": True,
        "recovery_state": attempt["recovery_state"],
        "terminal_state": attempt["terminal_state"],
        "unknown_event_count": sum(
            event["event_kind"] == "execution_recovered_unknown"
            for event in snapshot["events"]
        ),
    }


def recover(database_path):
    store = RecoveryStore(database_path)
    snapshot = store.snapshot()
    attempt = _validate_snapshot(snapshot)
    if (
        attempt["dispatch_state"] == "accepted"
        and attempt["terminal_state"] is None
        and attempt["recovery_state"] is None
    ):
        store.record_recovery_unknown(ATTEMPT_ID)
        snapshot = store.snapshot()
    return _summary(snapshot)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    arguments = parser.parse_args(argv)
    database_path = Path(arguments.database)

    try:
        if not database_path.is_file():
            raise RecoveryFailure("database_missing")
        summary = recover(database_path)
    except (OSError, sqlite3.Error, RecoveryFailure, KeyError, TypeError, ValueError):
        _emit({"error": "recovery_failed_closed", "ok": False})
        return 1

    _emit(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
