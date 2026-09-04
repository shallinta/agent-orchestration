import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from store import RecoveryStore


class RecoveryStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.database_path = Path(self.temporary_directory.name) / "probe.sqlite3"
        self.store = RecoveryStore(self.database_path)

    def test_committed_synthetic_facts_survive_reopen(self):
        self.store.initialize_schema()
        self.store.add_role("host-agent", "host")
        self.store.add_role("worker-agent", "worker")
        self.store.add_delegation(
            "delegation-1", sender_role_id="host-agent", target_role_id="worker-agent"
        )
        self.store.add_attempt(
            "attempt-1", delegation_id="delegation-1", role_id="worker-agent"
        )

        snapshot = RecoveryStore(self.database_path).snapshot()

        self.assertEqual(
            snapshot["roles"],
            [
                {"role_id": "host-agent", "role_kind": "host"},
                {"role_id": "worker-agent", "role_kind": "worker"},
            ],
        )
        self.assertEqual(
            snapshot["delegations"],
            [
                {
                    "delegation_id": "delegation-1",
                    "sender_role_id": "host-agent",
                    "target_role_id": "worker-agent",
                    "completion_state": None,
                }
            ],
        )
        self.assertEqual(
            snapshot["attempts"],
            [
                {
                    "attempt_id": "attempt-1",
                    "delegation_id": "delegation-1",
                    "role_id": "worker-agent",
                    "dispatch_state": "prepared",
                    "terminal_state": None,
                    "recovery_state": None,
                }
            ],
        )
        self.assertEqual(
            [event["event_kind"] for event in snapshot["events"]],
            ["role_created", "role_created", "delegation_created", "attempt_created"],
        )
        self.assertEqual(snapshot["counts"]["messages"], 0)
        self.assertEqual(snapshot["counts"]["agent_results"], 0)
        self.assertEqual(snapshot["counts"]["acceptances"], 0)

    def test_duplicate_identity_facts_are_rejected_without_mutation(self):
        self._prepare_attempt()
        before = self.store.snapshot()

        duplicate_operations = (
            lambda: self.store.add_role("host-agent", "host"),
            lambda: self.store.add_delegation(
                "delegation-1", "host-agent", "worker-agent"
            ),
            lambda: self.store.add_attempt(
                "attempt-1", "delegation-1", "worker-agent"
            ),
        )
        for operation in duplicate_operations:
            with self.subTest(operation=operation):
                with self.assertRaises(sqlite3.IntegrityError):
                    operation()
                self.assertEqual(self.store.snapshot(), before)

    def test_acceptance_terminal_and_recovery_writes_are_idempotent(self):
        self._prepare_attempt()

        self.assertTrue(self.store.record_acceptance("attempt-1"))
        accepted = self.store.snapshot()
        self.assertFalse(self.store.record_acceptance("attempt-1"))
        self.assertEqual(self.store.snapshot(), accepted)

        self.assertTrue(self.store.record_terminal("attempt-1", "succeeded"))
        terminal = self.store.snapshot()
        self.assertFalse(self.store.record_terminal("attempt-1", "succeeded"))
        self.assertEqual(self.store.snapshot(), terminal)
        with self.assertRaises(ValueError):
            self.store.record_terminal("attempt-1", "failed")
        self.assertEqual(self.store.snapshot(), terminal)

        other_path = Path(self.temporary_directory.name) / "unknown.sqlite3"
        other = RecoveryStore(other_path)
        self._prepare_attempt(other)
        other.record_acceptance("attempt-1")
        self.assertTrue(other.record_recovery_unknown("attempt-1"))
        recovered = other.snapshot()
        self.assertFalse(other.record_recovery_unknown("attempt-1"))
        self.assertEqual(other.snapshot(), recovered)

    def test_foreign_keys_are_enforced_on_every_mutation_connection(self):
        self.store.initialize_schema()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_delegation(
                "delegation-1", "missing-host", "missing-worker"
            )
        self.assertEqual(self.store.snapshot()["events"], [])

    def test_terminal_requires_accepted_attempt_and_fixed_non_null_value(self):
        self._prepare_attempt()
        before = self.store.snapshot()

        for invalid_terminal in (None, "unknown"):
            with self.subTest(terminal_state=invalid_terminal):
                with self.assertRaises(ValueError):
                    self.store.record_terminal("attempt-1", invalid_terminal)
                self.assertEqual(self.store.snapshot(), before)

        with self.assertRaises(ValueError):
            self.store.record_terminal("attempt-1", "succeeded")
        self.assertEqual(self.store.snapshot(), before)

        self.store.record_acceptance("attempt-1")
        accepted = self.store.snapshot()
        with self.assertRaises(ValueError):
            self.store.record_terminal("attempt-1", None)
        self.assertEqual(self.store.snapshot(), accepted)

    def test_sqlite_constraints_reject_dispatch_terminal_recovery_mismatches(self):
        self._prepare_attempt()
        before = self.store.snapshot()

        invalid_updates = (
            "UPDATE execution_attempts SET terminal_state = 'succeeded' WHERE attempt_id = 'attempt-1'",
            "UPDATE execution_attempts SET recovery_state = 'result_unknown' WHERE attempt_id = 'attempt-1'",
            "UPDATE execution_attempts SET terminal_state = 'unknown' WHERE attempt_id = 'attempt-1'",
        )
        for statement in invalid_updates:
            with self.subTest(statement=statement):
                connection = sqlite3.connect(self.database_path)
                try:
                    with self.assertRaises(sqlite3.IntegrityError):
                        connection.execute(statement)
                        connection.commit()
                    connection.rollback()
                finally:
                    connection.close()
                self.assertEqual(self.store.snapshot(), before)

        self.store.record_acceptance("attempt-1")
        accepted = self.store.snapshot()
        connection = sqlite3.connect(self.database_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    UPDATE execution_attempts
                    SET terminal_state = 'failed', recovery_state = 'result_unknown'
                    WHERE attempt_id = 'attempt-1'
                    """
                )
                connection.commit()
            connection.rollback()
        finally:
            connection.close()
        self.assertEqual(self.store.snapshot(), accepted)

    def _prepare_attempt(self, store=None):
        store = store or self.store
        store.initialize_schema()
        store.add_role("host-agent", "host")
        store.add_role("worker-agent", "worker")
        store.add_delegation("delegation-1", "host-agent", "worker-agent")
        store.add_attempt("attempt-1", "delegation-1", "worker-agent")


if __name__ == "__main__":
    unittest.main()
