import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


PROBE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE_DIRECTORY))

from fake_worker import write_json
from stop_controller import (
    ProbeError,
    complete_managed_worker,
    start_managed_worker,
    stop_managed_worker,
    run_stop_probe,
)


EXPECTED_EFFECTS = {
    "harness_recorded": {"visibility": "direct", "state": "recorded"},
    "workspace_observed": {"visibility": "bounded", "state": "marker_present"},
    "external_uncovered": {"visibility": "uncovered", "state": "unknown"},
}


class StopControllerTest(unittest.TestCase):
    def test_atomic_json_publish_never_exposes_partial_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "ready.json"
            real_replace = os.replace

            def inspect_then_replace(source, target):
                self.assertFalse(destination.exists())
                self.assertEqual(
                    __import__("json").loads(Path(source).read_text(encoding="utf-8")),
                    {"fixed": "ready"},
                )
                real_replace(source, target)

            with mock.patch("fake_worker.os.replace", side_effect=inspect_then_replace):
                write_json(destination, {"fixed": "ready"})

            self.assertEqual(destination.read_text(encoding="utf-8"), '{"fixed": "ready"}\n')
            self.assertEqual(list(Path(directory).iterdir()), [destination])

    def test_atomic_json_publish_failure_removes_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "ready.json"
            with mock.patch("fake_worker.os.replace", side_effect=OSError("fixed")):
                with self.assertRaisesRegex(OSError, "fixed"):
                    write_json(destination, {"fixed": "ready"})
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_managed_popen_failure_is_normalized_and_cleans_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)

            def fail_launch(*_args, **_kwargs):
                raise OSError("private launch detail")

            with self.assertRaises(ProbeError) as caught:
                start_managed_worker(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    popen_factory=fail_launch,
                )

            self.assertEqual(str(caught.exception), "managed worker start failed")
            self.assertEqual(caught.exception.observed_pids, ())
            self.assertTrue(caught.exception.cleanup_outcome["complete"])
            self.assertEqual(list(workspace.iterdir()), [])

    def test_managed_baseexception_preserves_original_and_full_cleanup_outcome(self):
        original = KeyboardInterrupt("fixed managed interrupt")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            handle = start_managed_worker(
                worker_path=PROBE_DIRECTORY / "fake_worker.py",
                workspace=workspace,
            )
            with mock.patch(
                "stop_controller._confirm_managed_stopped", side_effect=original
            ):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    stop_managed_worker(handle, cleanup_timeout=1.0)

            self.assertIs(caught.exception, original)
            self.assertTrue(caught.exception.sg8_cleanup_outcome["complete"])
            self.assertIn("emergency_cleanup", caught.exception.sg8_cleanup_outcome)
            self.assertIn("final_safety_cleanup", caught.exception.sg8_cleanup_outcome)
            self.assertEqual(list(workspace.iterdir()), [])

    def test_managed_start_baseexception_preserves_original_and_cleans_worker(self):
        original = KeyboardInterrupt("fixed managed start interrupt")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with mock.patch("stop_controller._read_ready", side_effect=original):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    start_managed_worker(
                        worker_path=PROBE_DIRECTORY / "fake_worker.py",
                        workspace=workspace,
                    )

            self.assertIs(caught.exception, original)
            self.assertTrue(caught.exception.sg8_cleanup_outcome["complete"])
            self.assertEqual(list(workspace.iterdir()), [])

    def test_managed_completion_baseexception_preserves_original_and_artifact_failure(self):
        original = KeyboardInterrupt("fixed managed completion interrupt")
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            handle = start_managed_worker(
                worker_path=PROBE_DIRECTORY / "fake_worker.py",
                workspace=workspace,
            )
            unexpected = workspace / "unexpected.txt"
            unexpected.write_text("preserve", encoding="utf-8")
            with mock.patch(
                "stop_controller._confirm_managed_stopped", side_effect=original
            ):
                with self.assertRaises(KeyboardInterrupt) as caught:
                    complete_managed_worker(handle, cleanup_timeout=1.0)

            self.assertIs(caught.exception, original)
            outcome = caught.exception.sg8_cleanup_outcome
            self.assertEqual(outcome["artifact_cleanup"], "incomplete")
            self.assertFalse(outcome["complete"])
            self.assertTrue(any("cleanup incomplete" in note for note in caught.exception.__notes__))
            self.assertEqual(unexpected.read_text(encoding="utf-8"), "preserve")

    def run_probe(self, behavior, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            result = run_stop_probe(
                worker_path=PROBE_DIRECTORY / "fake_worker.py",
                workspace=Path(directory),
                behavior=behavior,
                ready_timeout=10.0,
                graceful_timeout=0.15,
                cleanup_timeout=1.0,
                **kwargs,
            )
            self.assertEqual(list(Path(directory).glob("**/*")), [])
            return result

    def test_graceful_stop_preserves_reliable_terminal_and_releases_slot(self):
        result = self.run_probe("graceful")

        self.assertEqual(result["dispatch_count"], 1)
        self.assertEqual(result["redispatch_count"], 0)
        self.assertEqual(
            result["dispatch_ledger"],
            [{"attempt": "fixed-attempt", "event": "dispatch"}],
        )
        self.assertEqual(result["signals"], ["graceful"])
        self.assertTrue(result["all_recorded_pids_gone"])
        self.assertEqual(
            result["summary"],
            {
                "stop_request": {
                    "mode": "graceful",
                    "graceful_requested": True,
                    "deadline_expired": False,
                    "force_requested": False,
                },
                "stop_confirmation": "controlled_group_stopped",
                "terminal_state": "cancelled",
                "terminal_evidence": "synthetic_worker_terminal",
                "result_state": "cancelled",
                "slot_state": "released",
                "retry_eligibility": "blocked",
                "side_effects": EXPECTED_EFFECTS,
                "decision_escalation": {
                    "state": "required",
                    "target": "responsible_actor",
                    "notification_sent": False,
                    "decision_taken": False,
                    "automatic_action": "none",
                },
            },
        )

    def test_ignored_graceful_request_escalates_once_after_deadline(self):
        result = self.run_probe("ignore")

        self.assertEqual(result["dispatch_count"], 1)
        self.assertEqual(result["redispatch_count"], 0)
        self.assertEqual(
            result["dispatch_ledger"],
            [{"attempt": "fixed-attempt", "event": "dispatch"}],
        )
        self.assertEqual(result["signals"], ["graceful", "force"])
        self.assertGreaterEqual(
            result["force_requested_at"] - result["graceful_requested_at"],
            0.15,
        )
        self.assertTrue(result["all_recorded_pids_gone"])
        self.assertEqual(result["summary"]["terminal_state"], None)
        self.assertEqual(result["summary"]["result_state"], "result_unknown")
        self.assertEqual(result["summary"]["slot_state"], "released")
        self.assertEqual(result["summary"]["retry_eligibility"], "blocked")
        self.assertEqual(result["summary"]["side_effects"], EXPECTED_EFFECTS)

    def test_children_share_the_exact_controller_created_process_group(self):
        result = self.run_probe("graceful")

        self.assertEqual(result["leader_pid"], result["pgid"])
        self.assertEqual(result["observed_child_pgid"], result["pgid"])

    def test_missing_ready_evidence_fails_closed(self):
        self.assert_fails_closed("missing_ready")

    def test_nonempty_workspace_is_rejected_before_dispatch_or_worker_launch(self):
        launched = False

        def forbidden_launch(*_args, **_kwargs):
            nonlocal launched
            launched = True
            raise AssertionError("worker must not launch")

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            sentinel = workspace / "sentinel.txt"
            sentinel.write_text("preserve exactly", encoding="utf-8")

            with self.assertRaises(ProbeError) as caught:
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    behavior="graceful",
                    ready_timeout=10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=0.5,
                    popen_factory=forbidden_launch,
                )

            self.assertFalse(launched)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "preserve exactly")
            self.assertEqual(list(workspace.iterdir()), [sentinel])
            self.assertNotIn("released", str(caught.exception))

    def test_missing_or_non_directory_workspace_is_rejected_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = (root / "missing", root / "not-a-directory")
            candidates[1].write_text("fixed", encoding="utf-8")
            for workspace in candidates:
                with self.subTest(workspace=workspace.name):
                    with self.assertRaises(ProbeError):
                        run_stop_probe(
                            worker_path=PROBE_DIRECTORY / "fake_worker.py",
                            workspace=workspace,
                            behavior="graceful",
                            ready_timeout=10.0,
                            graceful_timeout=0.05,
                            cleanup_timeout=0.5,
                            popen_factory=lambda *_args, **_kwargs: self.fail("launched"),
                        )

    def test_unknown_artifact_is_preserved_and_prevents_released_summary(self):
        unexpected_content = "fixed unexpected content"
        workspace = None

        def create_unexpected(checkpoint, _facts):
            if checkpoint == "after_ready":
                workspace.joinpath("unexpected.txt").write_text(
                    unexpected_content, encoding="utf-8"
                )

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(ProbeError) as caught:
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    behavior="graceful",
                    ready_timeout=10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=0.5,
                    checkpoint=create_unexpected,
                )

            unexpected = workspace / "unexpected.txt"
            self.assertEqual(unexpected.read_text(encoding="utf-8"), unexpected_content)
            self.assertEqual(caught.exception.cleanup_outcome["artifact_cleanup"], "incomplete")
            self.assertFalse(caught.exception.cleanup_outcome["complete"])
            self.assertNotIn("released", str(caught.exception))

    def test_whitelisted_name_with_directory_type_is_preserved_and_fails_closed(self):
        workspace = None

        def replace_ready_with_directory(checkpoint, _facts):
            if checkpoint == "after_ready":
                ready = workspace / "ready.json"
                ready.unlink()
                ready.mkdir()

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(ProbeError) as caught:
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    behavior="graceful",
                    ready_timeout=10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=0.5,
                    checkpoint=replace_ready_with_directory,
                )

            self.assertTrue((workspace / "ready.json").is_dir())
            self.assertEqual(caught.exception.cleanup_outcome["artifact_cleanup"], "incomplete")
            self.assertNotIn("released", str(caught.exception))

    def test_malformed_pid_or_pgid_evidence_fails_closed(self):
        for behavior in ("malformed_ready", "wrong_pgid"):
            with self.subTest(behavior=behavior):
                self.assert_fails_closed(behavior)

    def test_surviving_recorded_child_fails_closed_and_is_hard_cleaned(self):
        error = self.assert_fails_closed("ignore", pid_gone=lambda _pid: False)
        self.assertEqual(str(error), "a recorded PID survived stop")
        self.assertGreaterEqual(len(error.observed_pids), 2)
        for pid in error.observed_pids:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_missing_effect_ledger_fails_closed(self):
        error = self.assert_fails_closed("missing_effect")
        self.assertEqual(str(error), "effect evidence is missing or malformed")

    def test_inability_to_confirm_group_stop_fails_closed(self):
        self.assert_fails_closed("ignore", group_gone=lambda _pgid: False)

    def test_keyboard_interrupt_after_ready_cleans_group_and_reraises(self):
        observed = {}

        def interrupt(checkpoint, facts):
            if checkpoint == "after_ready":
                observed.update(facts)
                raise KeyboardInterrupt("fixed interrupt")

        self.assert_interrupted_and_cleaned("graceful", interrupt, observed)

    def test_keyboard_interrupt_after_force_cleans_group_and_reraises(self):
        observed = {}

        def interrupt(checkpoint, facts):
            if checkpoint == "after_force":
                observed.update(facts)
                raise KeyboardInterrupt("fixed interrupt")

        self.assert_interrupted_and_cleaned("ignore", interrupt, observed)

    def test_interrupt_preserves_identity_when_group_kill_is_permission_denied(self):
        def denied(_pgid, _signal):
            raise PermissionError("fixed denial")

        error = self.run_cleanup_fault_interrupt(
            behavior="graceful",
            interrupt_at="after_ready",
            cleanup_ops={"kill_group": denied},
        )

        self.assertEqual(error.sg8_cleanup_outcome["group_kill"], "permission_denied")
        self.assertFalse(error.sg8_cleanup_outcome["complete"])
        self.assertTrue(error.sg8_cleanup_outcome["emergency_cleanup"]["complete"])

    def test_interrupt_reports_leader_wait_timeout_without_masking_interrupt(self):
        def timeout(_process, seconds):
            raise subprocess.TimeoutExpired("fixed-worker", seconds)

        error = self.run_cleanup_fault_interrupt(
            behavior="graceful",
            interrupt_at="after_ready",
            cleanup_ops={"wait_leader": timeout},
        )

        self.assertEqual(error.sg8_cleanup_outcome["leader_reap"], "timeout")
        self.assertFalse(error.sg8_cleanup_outcome["complete"])
        self.assertTrue(any("cleanup incomplete" in note for note in error.__notes__))

    def test_unexpected_cleanup_exception_does_not_replace_interrupt(self):
        def broken(_pgid, _signal):
            raise RuntimeError("fixed cleanup bug")

        error = self.run_cleanup_fault_interrupt(
            behavior="graceful",
            interrupt_at="after_ready",
            cleanup_ops={"kill_group": broken},
        )

        self.assertEqual(error.sg8_cleanup_outcome["group_kill"], "operation_failed")

    def test_cleanup_never_sends_a_signal_to_an_individual_pid(self):
        called = False

        def denied(_pid, _signal):
            nonlocal called
            called = True
            raise PermissionError("fixed denial")

        error = self.run_cleanup_fault_interrupt(
            behavior="ignore",
            interrupt_at="after_force",
            cleanup_ops={
                "kill_pid": denied,
                "pid_gone": lambda _pid: False,
                "group_gone": lambda _pgid: False,
            },
        )

        outcome = error.sg8_cleanup_outcome
        self.assertFalse(called)
        self.assertEqual(outcome["pid_signal"], "not_sent")
        self.assertGreater(outcome["remaining_pid_count"], 0)
        self.assertEqual(outcome["group_state"], "present_or_unconfirmed")
        self.assertFalse(outcome["complete"])
        self.assertTrue(outcome["emergency_cleanup"]["complete"])

    def test_emergency_cleanup_baseexception_is_sanitized_and_original_survives(self):
        def primary_denied(_pgid, _signal):
            raise PermissionError("fixed primary denial")

        def emergency_interrupt(_pgid, _signal):
            raise KeyboardInterrupt("fixed emergency interrupt")

        error = self.run_cleanup_fault_interrupt(
            behavior="graceful",
            interrupt_at="after_ready",
            cleanup_ops={"kill_group": primary_denied},
            emergency_ops={"kill_group": emergency_interrupt},
        )

        emergency = error.sg8_cleanup_outcome["emergency_cleanup"]
        self.assertEqual(emergency["group_kill"], "operation_failed")
        self.assertFalse(emergency["complete"])
        self.assertTrue(error.sg8_cleanup_outcome["final_safety_cleanup"]["complete"])

    def test_emergency_setup_baseexception_does_not_replace_probe_error(self):
        class BrokenEmergencyOperations:
            def get(self, _name, _default):
                raise KeyboardInterrupt("fixed emergency setup interrupt")

        error = self.assert_fails_closed(
            "missing_effect",
            cleanup_ops={
                "pid_gone": lambda _pid: False,
                "group_gone": lambda _pgid: False,
            },
            emergency_ops=BrokenEmergencyOperations(),
        )

        self.assertEqual(str(error), "effect evidence is missing or malformed")
        self.assertEqual(
            error.cleanup_outcome["emergency_cleanup"]["group_kill"],
            "operation_failed",
        )
        self.assertTrue(error.cleanup_outcome["final_safety_cleanup"]["complete"])

    def test_reaped_leader_prevents_later_group_signals(self):
        group_signal_calls = []
        original = KeyboardInterrupt("fixed after reap interrupt")

        def interrupt(checkpoint, _facts):
            if checkpoint == "after_reap":
                raise original

        def forbidden_group_signal(pgid, sent_signal):
            group_signal_calls.append((pgid, sent_signal))
            raise AssertionError("identity-lost group must not be signalled")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(KeyboardInterrupt) as caught:
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=Path(directory),
                    behavior="ignore",
                    ready_timeout=10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=0.1,
                    checkpoint=interrupt,
                    cleanup_ops={
                        "pid_gone": lambda _pid: False,
                        "group_gone": lambda _pgid: False,
                    },
                    emergency_ops={
                        "kill_group": forbidden_group_signal,
                        "pid_gone": lambda _pid: False,
                        "group_gone": lambda _pgid: False,
                    },
                    final_ops={"kill_group": forbidden_group_signal},
                )

            self.assertIs(caught.exception, original)
            self.assertEqual(group_signal_calls, [])
            outcome = caught.exception.sg8_cleanup_outcome
            self.assertEqual(outcome["emergency_cleanup"]["group_kill"], "identity_lost")
            self.assertEqual(outcome["final_safety_cleanup"]["group_kill"], "identity_lost")
            self.assertNotIn("released", str(caught.exception))

    def run_cleanup_fault_interrupt(
        self, *, behavior, interrupt_at, cleanup_ops, emergency_ops=None
    ):
        observed = {}
        original = KeyboardInterrupt("fixed original interrupt")

        def interrupt(checkpoint, facts):
            if checkpoint == interrupt_at:
                observed.update(facts)
                raise original

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(KeyboardInterrupt) as caught:
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    behavior=behavior,
                    ready_timeout=10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=0.15,
                    checkpoint=interrupt,
                    cleanup_ops=cleanup_ops,
                    emergency_ops=emergency_ops,
                )
            self.assertIs(caught.exception, original)
            self.assertNotIn("released", str(caught.exception))
            self.assertEqual(set(observed), {"leader_pid", "child_pid", "pgid"})
            for pid in (observed["leader_pid"], observed["child_pid"]):
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
            self.assertEqual(list(workspace.glob("**/*")), [])
            return caught.exception

    def assert_interrupted_and_cleaned(self, behavior, checkpoint, observed):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaisesRegex(KeyboardInterrupt, "fixed interrupt"):
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    behavior=behavior,
                    ready_timeout=10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=1.0,
                    checkpoint=checkpoint,
                )

            self.assertEqual(set(observed), {"leader_pid", "child_pid", "pgid"})
            for pid in (observed["leader_pid"], observed["child_pid"]):
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)
            self.assertEqual(list(workspace.glob("**/*")), [])

    def assert_fails_closed(self, behavior, **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaises(ProbeError) as caught:
                run_stop_probe(
                    worker_path=PROBE_DIRECTORY / "fake_worker.py",
                    workspace=workspace,
                    behavior=behavior,
                    ready_timeout=0.5 if behavior == "missing_ready" else 10.0,
                    graceful_timeout=0.05,
                    cleanup_timeout=0.5,
                    **kwargs,
                )

            self.assertNotIn("released", str(caught.exception))
            self.assertGreaterEqual(len(caught.exception.observed_pids), 1)
            self.assertIsNotNone(caught.exception.cleanup_outcome)
            self.assertIn("complete", caught.exception.cleanup_outcome)
            return caught.exception


if __name__ == "__main__":
    unittest.main()
