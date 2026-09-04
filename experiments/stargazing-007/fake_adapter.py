import argparse
import json
import os
from pathlib import Path


FIXED_ATTEMPT_ID = "attempt-1"


def _emit(payload):
    print(json.dumps(payload, separators=(",", ":"), sort_keys=True), flush=True)


def _read_ledger(ledger_path):
    if not ledger_path.exists():
        return []
    return [json.loads(line) for line in ledger_path.read_text().splitlines()]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--attempt-id", required=True)
    arguments = parser.parse_args(argv)

    if arguments.attempt_id != FIXED_ATTEMPT_ID:
        _emit(
            {
                "accepted": False,
                "attempt_id": arguments.attempt_id,
                "error": "invalid_attempt_id",
            }
        )
        return 2

    ledger_path = Path(arguments.ledger)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    entries = _read_ledger(ledger_path)
    duplicate = any(
        entry.get("attempt_id") == FIXED_ATTEMPT_ID
        and entry.get("outcome") == "accepted"
        for entry in entries
    )
    outcome = "duplicate" if duplicate else "accepted"
    entry = {
        "sequence": len(entries) + 1,
        "attempt_id": FIXED_ATTEMPT_ID,
        "outcome": outcome,
    }
    with ledger_path.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(entry, separators=(",", ":"), sort_keys=True) + "\n")
        ledger.flush()
        os.fsync(ledger.fileno())

    if duplicate:
        _emit(
            {
                "accepted": False,
                "attempt_id": FIXED_ATTEMPT_ID,
                "error": "duplicate",
            }
        )
        return 3

    _emit(
        {
            "accepted": True,
            "attempt_id": FIXED_ATTEMPT_ID,
            "outcome": "accepted",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
