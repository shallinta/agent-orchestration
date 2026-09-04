import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROBE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE_DIRECTORY))

from store import RecoveryStore


CRASH_WORKER = PROBE_DIRECTORY / "crash_worker.py"
FAKE_ADAPTER = PROBE_DIRECTORY / "fake_adapter.py"
RECOVER_WORKER = PROBE_DIRECTORY / "recover_worker.py"


class RecoveryWorkerTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "probe.sqlite3"
        self.ledger_path = self.root / "adapter.jsonl"

    def test_accepted_without_terminal_recovers_unknown_without_redispatch(self):
        self._prepare_post_crash()

        recovered = self._recover()

        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(
            json.loads(recovered.stdout),
            {
                "attempt_count": 1,
                "dispatch_state": "accepted",
                "ok": True,
                "recovery_state": "result_unknown",
                "terminal_state": None,
                "unknown_event_count": 1,
            },
        )
        snapshot = RecoveryStore(self.database_path).snapshot()
        self.assertEqual(snapshot["attempts"][0]["recovery_state"], "result_unknown")
        self.assertIsNone(snapshot["attempts"][0]["terminal_state"])
        self.assertEqual(len(snapshot["attempts"]), 1)
        self.assertEqual(snapshot["counts"], {"messages": 0, "agent_results": 0, "acceptances": 1})
        self.assertIsNone(snapshot["delegations"][0]["completion_state"])
        self.assertEqual(self._ledger_counts(), {"total": 1, "accepted": 1, "duplicate": 0})

    def test_third_process_recovery_is_idempotent_with_exactly_one_unknown_event(self):
        self._prepare_post_crash()

        first = self._recover()
        third_process = self._recover()

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(third_process.returncode, 0, third_process.stderr)
        self.assertEqual(json.loads(third_process.stdout), json.loads(first.stdout))
        snapshot = RecoveryStore(self.database_path).snapshot()
        self.assertEqual(
            sum(event["event_kind"] == "execution_recovered_unknown" for event in snapshot["events"]),
            1,
        )
        self.assertEqual(self._ledger_counts(), {"total": 1, "accepted": 1, "duplicate": 0})

    def test_prepared_attempt_is_not_mislabeled_unknown(self):
        store = self._prepare_attempt()
        before = store.snapshot()

        result = self._recover()

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["dispatch_state"], "prepared")
        self.assertIsNone(summary["recovery_state"])
        self.assertEqual(summary["unknown_event_count"], 0)
        self.assertEqual(store.snapshot(), before)
        self.assertFalse(self.ledger_path.exists())

    def test_existing_terminal_fact_is_not_overwritten(self):
        store = self._prepare_attempt()
        store.record_acceptance("attempt-1")
        store.record_terminal("attempt-1", "succeeded")
        before = store.snapshot()

        result = self._recover()

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["terminal_state"], "succeeded")
        self.assertIsNone(summary["recovery_state"])
        self.assertEqual(summary["unknown_event_count"], 0)
        self.assertEqual(store.snapshot(), before)

    def test_inconsistent_database_fails_closed_without_mutation(self):
        store = self._prepare_attempt()
        store.record_acceptance("attempt-1")
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "DELETE FROM fact_events WHERE event_kind = 'adapter_accepted' AND entity_id = 'attempt-1'"
            )
            connection.commit()
        finally:
            connection.close()
        before = store.snapshot()

        result = self._recover()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"error": "recovery_failed_closed", "ok": False})
        self.assertEqual(store.snapshot(), before)

    def test_malformed_database_fails_closed_without_mutation(self):
        self.database_path.write_bytes(b"not a sqlite database")
        before = self.database_path.read_bytes()

        result = self._recover()

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"error": "recovery_failed_closed", "ok": False})
        self.assertEqual(self.database_path.read_bytes(), before)

    def _prepare_post_crash(self):
        result = subprocess.run(
            [
                sys.executable,
                str(CRASH_WORKER),
                "--database",
                str(self.database_path),
                "--ledger",
                str(self.ledger_path),
                "--adapter-command",
                str(FAKE_ADAPTER),
            ],
            shell=False,
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )
        self.assertEqual(result.returncode, 73, result.stderr)

    def _prepare_attempt(self):
        store = RecoveryStore(self.database_path)
        store.initialize_schema()
        store.add_role("host-agent", "host")
        store.add_role("worker-agent", "worker")
        store.add_delegation("delegation-1", "host-agent", "worker-agent")
        store.add_attempt("attempt-1", "delegation-1", "worker-agent")
        return store

    def _recover(self):
        return subprocess.run(
            [sys.executable, str(RECOVER_WORKER), "--database", str(self.database_path)],
            shell=False,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    def _ledger_counts(self):
        rows = [json.loads(line) for line in self.ledger_path.read_text().splitlines()]
        return {
            "total": len(rows),
            "accepted": sum(row["outcome"] == "accepted" for row in rows),
            "duplicate": sum(row["outcome"] == "duplicate" for row in rows),
        }


if __name__ == "__main__":
    unittest.main()
