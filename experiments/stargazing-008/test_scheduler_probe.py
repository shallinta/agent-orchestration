import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path


PROBE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE_DIRECTORY))

from scheduler_probe import SchedulerError, SchedulerProbe
from stop_controller import CompletionReceipt, StopReceipt


FAKE_WORKER = PROBE_DIRECTORY / "fake_worker.py"


class SchedulerProbeTest(unittest.TestCase):
    def setUp(self):
        self.scheduler = SchedulerProbe()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        for role_id in ("writer", "analyst"):
            for attempt_id in self.scheduler.active_attempts(role_id):
                self.scheduler.force_stop_attempt(
                    attempt_id, graceful_timeout=0.03, cleanup_timeout=1.0
                )

    def submit(self, attempt_id, role_id):
        workspace = self.root / attempt_id
        workspace.mkdir()
        return self.scheduler.submit(
            attempt_id,
            role_id,
            worker_path=FAKE_WORKER,
            workspace=workspace,
            ready_timeout=10.0,
        )

    def test_different_roles_run_concurrently_but_same_role_capacity_is_one(self):
        writer_first = self.submit("writer-1", "writer")
        writer_second = self.submit("writer-2", "writer")
        analyst_first = self.submit("analyst-1", "analyst")

        self.assertEqual(writer_first["state"], "active")
        self.assertEqual(writer_second["state"], "pending")
        self.assertEqual(analyst_first["state"], "active")
        self.assertEqual(self.scheduler.active_attempts("writer"), ["writer-1"])
        self.assertEqual(self.scheduler.active_attempts("analyst"), ["analyst-1"])
        self.assertEqual(self.scheduler.dispatch_ledger, ["writer-1", "analyst-1"])
        self.assertEqual(self.scheduler.dispatch_count("writer-2"), 0)

    def test_confirmed_stop_releases_only_that_role_and_old_unknown_never_redispatches(self):
        self.submit("writer-old", "writer")
        analyst = self.submit("analyst-active", "analyst")

        self.scheduler.force_stop_attempt("writer-old", graceful_timeout=0.03, cleanup_timeout=1.0)
        replacement = self.submit("writer-new", "writer")

        old = self.scheduler.snapshot()["attempts"]["writer-old"]
        self.assertEqual(old["state"], "stopped")
        self.assertEqual(old["result_state"], "result_unknown")
        self.assertEqual(old["retry_eligibility"], "blocked")
        self.assertEqual(self.scheduler.dispatch_count("writer-old"), 1)
        self.assertEqual(replacement["state"], "active")
        self.assertEqual(analyst["state"], "active")
        self.assertEqual(self.scheduler.active_attempts("analyst"), ["analyst-active"])
        self.assertEqual(
            self.scheduler.dispatch_ledger,
            ["writer-old", "analyst-active", "writer-new"],
        )

    def test_disabled_role_blocks_new_dispatch_and_graceful_disable_allows_active_finish(self):
        self.submit("writer-active", "writer")
        role_before = self.scheduler.role("writer")

        outcome = self.scheduler.disable_role("writer", mode="graceful")
        blocked = self.submit("writer-after-disable", "writer")
        receipt = self.scheduler.complete_execution("writer-active")
        active = self.scheduler.snapshot()["attempts"]["writer-active"]

        self.assertEqual(outcome, {"mode": "graceful", "stop_invoked": False})
        self.assertEqual(active["state"], "completed")
        self.assertEqual(active["result_state"], "succeeded")
        self.assertEqual(blocked["state"], "pending")
        self.assertEqual(self.scheduler.dispatch_count("writer-after-disable"), 0)
        self.assertEqual(self.scheduler.active_attempts("writer"), [])

        self.scheduler.enable_role("writer")
        self.assertEqual(self.scheduler.role("writer")["instance_identity"], role_before["instance_identity"])
        resumed = self.submit("writer-after-enable", "writer")
        self.assertEqual(resumed["state"], "active")

    def test_force_disable_reuses_stop_controller_and_does_not_fabricate_terminal(self):
        dispatched = self.submit("writer-force", "writer")
        observed_pids = ()
        outcome = self.scheduler.disable_role(
            "writer",
            mode="force",
            graceful_timeout=0.05,
            cleanup_timeout=1.0,
        )
        observed_pids = outcome["observed_pids"]

        self.assertTrue(outcome["stop_invoked"])
        self.assertEqual(outcome["execution_identity"], dispatched["execution_identity"])
        self.assertEqual(outcome["stop_summary"]["stop_request"]["mode"], "force_after_deadline")
        self.assertIsNone(outcome["stop_summary"]["terminal_state"])
        self.assertEqual(outcome["stop_summary"]["result_state"], "result_unknown")
        active = self.scheduler.snapshot()["attempts"]["writer-force"]
        self.assertEqual(active["state"], "stopped")
        self.assertIsNone(active["terminal_state"])
        self.assertEqual(active["result_state"], "result_unknown")
        self.assertEqual(active["retry_eligibility"], "blocked")
        self.assertFalse(self.scheduler.role("writer")["enabled"])
        for pid in observed_pids:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_host_and_supervisor_labels_block_disable_until_transferred(self):
        cases = (("host-role", "host"), ("supervisor-role", "supervisor"))
        for protected_role, label in cases:
            with self.subTest(label=label):
                scheduler = SchedulerProbe()
                with self.assertRaises(SchedulerError):
                    scheduler.disable_role(protected_role, mode="graceful")
                self.assertTrue(scheduler.role(protected_role)["enabled"])

                scheduler.transfer_label(label, protected_role, "writer")
                scheduler.disable_role(protected_role, mode="graceful")

                self.assertFalse(scheduler.role(protected_role)["enabled"])
                self.assertIn(label, scheduler.role("writer")["labels"])
                with self.assertRaises(SchedulerError):
                    scheduler.disable_role("writer", mode="graceful")

    def test_invalid_or_duplicate_facts_fail_closed_without_dispatch(self):
        before = self.scheduler.snapshot()
        for operation in (
            lambda: self.scheduler.submit("bad", "missing-role"),
            lambda: self.scheduler.disable_role("writer", mode="unknown"),
            lambda: self.scheduler.enable_role("missing-role"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(SchedulerError):
                    operation()
        self.assertEqual(self.scheduler.snapshot(), before)

        self.submit("attempt-1", "writer")
        accepted = self.scheduler.snapshot()
        with self.assertRaises(SchedulerError):
            self.scheduler.submit("attempt-1", "analyst")
        self.assertEqual(self.scheduler.snapshot(), accepted)

    def test_string_terminal_and_mismatched_typed_receipts_are_rejected(self):
        active = self.submit("receipt-test", "writer")
        before = self.scheduler.snapshot()
        with self.assertRaises(SchedulerError):
            self.scheduler.complete("receipt-test", "succeeded")
        with self.assertRaises(SchedulerError):
            self.scheduler.apply_stop_receipt(
                "receipt-test",
                StopReceipt(
                    execution_identity=active["execution_identity"],
                    summary={},
                    observed_pids=(),
                ),
            )
        with self.assertRaises(SchedulerError):
            self.scheduler.complete(
                "receipt-test",
                CompletionReceipt(active["execution_identity"], "succeeded"),
            )
        self.assertEqual(self.scheduler.snapshot(), before)

    def test_returned_views_cannot_mutate_internal_roles_attempts_or_ledger(self):
        role = self.scheduler.role("writer")
        role["enabled"] = False
        role["labels"].add("host")
        ledger = self.scheduler.dispatch_ledger
        ledger.append("forged")
        submitted = self.submit("copy-test", "writer")
        submitted["state"] = "completed"
        snapshot = self.scheduler.snapshot()
        snapshot["roles"]["writer"]["enabled"] = False
        snapshot["attempts"]["copy-test"]["state"] = "completed"
        snapshot["dispatch_ledger"].clear()

        fresh = self.scheduler.role("writer")
        self.assertTrue(fresh["enabled"])
        self.assertEqual(fresh["labels"], set())
        self.assertEqual(self.scheduler.snapshot()["attempts"]["copy-test"]["state"], "active")
        self.assertEqual(self.scheduler.dispatch_ledger, ["copy-test"])

    def test_label_transfer_rejects_disabled_target_without_partial_mutation(self):
        self.scheduler.disable_role("writer", mode="graceful")
        before = self.scheduler.snapshot()

        with self.assertRaises(SchedulerError):
            self.scheduler.transfer_label("host", "host-role", "writer")

        self.assertEqual(self.scheduler.snapshot(), before)

    def test_label_transfer_preserves_one_enabled_holder(self):
        self.scheduler.transfer_label("host", "host-role", "writer")

        holders = [
            role_id
            for role_id, role in self.scheduler.snapshot()["roles"].items()
            if role["enabled"] and "host" in role["labels"]
        ]
        self.assertEqual(holders, ["writer"])


if __name__ == "__main__":
    unittest.main()
