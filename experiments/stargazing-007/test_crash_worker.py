import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROBE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE_DIRECTORY))

from crash_worker import verify_committed_acceptance
from store import RecoveryStore


CRASH_WORKER = PROBE_DIRECTORY / "crash_worker.py"
FAKE_ADAPTER = PROBE_DIRECTORY / "fake_adapter.py"


class CrashWorkerTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def test_planned_crash_occurs_only_after_acceptance_is_committed(self):
        database_path = self.root / "probe.sqlite3"
        ledger_path = self.root / "adapter.jsonl"

        result = self._run_worker(database_path, ledger_path, FAKE_ADAPTER)

        self.assertEqual(result.returncode, 73, result.stderr)
        snapshot = RecoveryStore(database_path).snapshot()
        self.assertEqual(len(snapshot["roles"]), 2)
        self.assertEqual(len(snapshot["delegations"]), 1)
        self.assertEqual(len(snapshot["attempts"]), 1)
        self.assertEqual(
            snapshot["attempts"][0],
            {
                "attempt_id": "attempt-1",
                "delegation_id": "delegation-1",
                "role_id": "worker-agent",
                "dispatch_state": "accepted",
                "terminal_state": None,
                "recovery_state": None,
            },
        )
        self.assertEqual(snapshot["counts"]["acceptances"], 1)
        self.assertEqual(snapshot["counts"]["messages"], 0)
        self.assertEqual(snapshot["counts"]["agent_results"], 0)
        self.assertIsNone(snapshot["delegations"][0]["completion_state"])
        self.assertEqual(
            self._ledger(ledger_path),
            [{"sequence": 1, "attempt_id": "attempt-1", "outcome": "accepted"}],
        )

    def test_duplicate_adapter_acceptance_fails_closed_without_database_acceptance(self):
        ledger_path = self.root / "adapter.jsonl"
        first = subprocess.run(
            [
                sys.executable,
                str(FAKE_ADAPTER),
                "--ledger",
                str(ledger_path),
                "--attempt-id",
                "attempt-1",
            ],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(first.returncode, 0)
        database_path = self.root / "duplicate.sqlite3"

        result = self._run_worker(database_path, ledger_path, FAKE_ADAPTER)

        self.assertNotEqual(result.returncode, 73)
        snapshot = RecoveryStore(database_path).snapshot()
        self.assertEqual(snapshot["attempts"][0]["dispatch_state"], "prepared")
        self.assertEqual(snapshot["counts"]["acceptances"], 0)
        self.assertEqual(
            [entry["outcome"] for entry in self._ledger(ledger_path)],
            ["accepted", "duplicate"],
        )

    def test_adapter_protocol_failures_never_become_planned_crash_evidence(self):
        fixtures = {
            "malformed": "print('not-json')",
            "nonzero": "import sys; print('{\"accepted\":true,\"attempt_id\":\"attempt-1\",\"outcome\":\"accepted\"}'); sys.exit(9)",
            "wrong_attempt": "print('{\"accepted\":true,\"attempt_id\":\"attempt-other\",\"outcome\":\"accepted\"}')",
            "timeout": "import time; time.sleep(3)",
        }
        for name, source in fixtures.items():
            with self.subTest(name=name):
                case_root = self.root / name
                case_root.mkdir()
                adapter_path = case_root / "adapter.py"
                adapter_path.write_text(source + "\n")
                database_path = case_root / "probe.sqlite3"
                ledger_path = case_root / "adapter.jsonl"

                result = self._run_worker(database_path, ledger_path, adapter_path)

                self.assertNotEqual(result.returncode, 73)
                snapshot = RecoveryStore(database_path).snapshot()
                self.assertEqual(snapshot["attempts"][0]["dispatch_state"], "prepared")
                self.assertEqual(snapshot["counts"]["acceptances"], 0)

    def test_commit_verification_rejects_unaccepted_database_state(self):
        database_path = self.root / "unaccepted.sqlite3"
        store = RecoveryStore(database_path)
        self._prepare_attempt(store)

        with self.assertRaises(RuntimeError):
            verify_committed_acceptance(database_path)

    def _run_worker(self, database_path, ledger_path, adapter_path):
        return subprocess.run(
            [
                sys.executable,
                str(CRASH_WORKER),
                "--database",
                str(database_path),
                "--ledger",
                str(ledger_path),
                "--adapter-command",
                str(adapter_path),
            ],
            text=True,
            capture_output=True,
            timeout=8,
            check=False,
        )

    @staticmethod
    def _prepare_attempt(store):
        store.initialize_schema()
        store.add_role("host-agent", "host")
        store.add_role("worker-agent", "worker")
        store.add_delegation("delegation-1", "host-agent", "worker-agent")
        store.add_attempt("attempt-1", "delegation-1", "worker-agent")

    @staticmethod
    def _ledger(ledger_path):
        return [json.loads(line) for line in ledger_path.read_text().splitlines()]


if __name__ == "__main__":
    unittest.main()
