import json
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    from agent_runners import ClaudeRunner, CodexRunner
    from controller import ControllerResult
    from run_probe import run_probe
except ModuleNotFoundError:
    ClaudeRunner = None
    CodexRunner = None
    ControllerResult = None
    run_probe = None


HOST = "host-codex"
INVESTIGATOR = "investigator-claude"


class CapturingController:
    created = []

    def __init__(self, **options):
        self.options = options
        self.created.append(self)
        workspaces = options["workspaces"]
        self.workspace_strings = [str(path) for path in workspaces.values()]
        self.state_string = str(options["state"].state_path)
        self.log_string = str(options["state"].log_path)
        self.assert_assembly_is_live(options)

    @staticmethod
    def assert_assembly_is_live(options):
        workspaces = options["workspaces"]
        assert set(workspaces) == {HOST, INVESTIGATOR}
        assert workspaces[HOST] != workspaces[INVESTIGATOR]
        assert all((Path(path) / ".git").exists() for path in workspaces.values())
        commands = options["mcp_commands"]
        for role in (HOST, INVESTIGATOR):
            command = commands[role]
            index = command.index("--caller-role")
            assert command[index + 1] == role
        assert options["runners"][HOST].product == "codex"
        assert options["runners"][INVESTIGATOR].product == "claude"
        assert options["timeout_seconds"] == 300
        assert options["success_deadline_seconds"] == 1800
        assert options["failure_deadline_seconds"] == 600

    def _result(self):
        result = ControllerResult()
        result.outcome = "success"
        result.final_result = "TOP-SECRET final prose"
        result.turns = [
            SimpleNamespace(role_id=HOST, mode="start", final_result="host turn one"),
            SimpleNamespace(
                role_id=INVESTIGATOR,
                mode="start",
                final_result="investigator analysis",
            ),
        ]
        result.deliveries = [
            SimpleNamespace(
                fact_kind="delegation",
                fact_id="delegation-1",
                sender_role_id=HOST,
                target_role_id=INVESTIGATOR,
                payload="TOP-SECRET delegation body",
                send_digest="a" * 64,
                payload_digest="a" * 64,
            )
        ]
        result.sessions[HOST] = "TOP-SECRET session"
        result.sessions[INVESTIGATOR] = "TOP-SECRET investigator session"
        return result

    def run_success(self):
        self.called = "success"
        return self._result()

    def run_start_failure(self):
        self.called = "start-failure"
        return self._result()


class RunProbeTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(run_probe, "run_probe.py is absent")
        CapturingController.created.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def test_success_assembles_one_disposable_run_and_writes_sanitized_summary(self):
        summary_path = Path(self.temp_dir.name) / "success-summary.json"
        review_path = Path(self.temp_dir.name) / "success-review.json"
        review_path.touch()
        review_path.chmod(0o644)
        summary = run_probe(
            mode="success",
            summary_path=summary_path,
            review_bundle_path=review_path,
            controller_class=CapturingController,
        )

        controller = CapturingController.created[-1]
        self.assertEqual(controller.called, "success")
        self.assertIsInstance(controller.options["runners"][HOST], CodexRunner)
        self.assertIsInstance(controller.options["runners"][INVESTIGATOR], ClaudeRunner)
        self.assertEqual(summary, json.loads(summary_path.read_text(encoding="utf-8")))
        self.assertTrue(summary["distinct_role_sessions"])
        serialized = summary_path.read_text(encoding="utf-8")
        for forbidden in (
            "TOP-SECRET",
            *controller.workspace_strings,
            controller.state_string,
            controller.log_string,
        ):
            self.assertNotIn(forbidden, serialized)

        # TemporaryDirectory ownership is observable: run artifacts are gone on return.
        self.assertFalse(Path(controller.state_string).exists())
        review = json.loads(review_path.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(review_path.stat().st_mode), 0o600)
        self.assertEqual(review["final_host_text"], "TOP-SECRET final prose")
        self.assertEqual(review["turns"][1]["final_text"], "investigator analysis")
        self.assertEqual(review["facts"][0]["body"], "TOP-SECRET delegation body")
        self.assertEqual(review["facts"][0]["fact_id"], "delegation-1")
        self.assertNotIn("TOP-SECRET session", json.dumps(review))
        for forbidden in (*controller.workspace_strings, controller.state_string, controller.log_string):
            self.assertNotIn(forbidden, json.dumps(review))

    def test_failure_mode_injects_an_absolute_nonexistent_claude_executable(self):
        summary_path = Path(self.temp_dir.name) / "failure-summary.json"
        review_path = Path(self.temp_dir.name) / "failure-review.json"
        run_probe(
            mode="start-failure",
            summary_path=summary_path,
            review_bundle_path=review_path,
            controller_class=CapturingController,
        )

        controller = CapturingController.created[-1]
        executable = Path(controller.options["runners"][INVESTIGATOR].executable)
        self.assertEqual(controller.called, "start-failure")
        self.assertTrue(executable.is_absolute())
        self.assertFalse(executable.exists())

    def test_invalid_mode_is_rejected_before_any_run_is_created(self):
        with self.assertRaisesRegex(ValueError, "mode"):
            run_probe(
                mode="other",
                summary_path=Path(self.temp_dir.name) / "unused.json",
                review_bundle_path=Path(self.temp_dir.name) / "unused-review.json",
                controller_class=CapturingController,
            )
        self.assertEqual(CapturingController.created, [])

    def test_review_bundle_path_is_explicit_absolute_and_outside_repository(self):
        with self.assertRaisesRegex(ValueError, "review bundle"):
            run_probe(
                mode="success",
                summary_path=Path(self.temp_dir.name) / "unused.json",
                review_bundle_path=Path("relative-review.json"),
                controller_class=CapturingController,
            )

    def test_run_failure_writes_a_sanitized_summary_before_reraising(self):
        class FailingController(CapturingController):
            def run_success(self):
                raise RuntimeError("TOP-SECRET failure detail")

        summary_path = Path(self.temp_dir.name) / "stopped-summary.json"
        with self.assertRaises(RuntimeError):
            run_probe(
                mode="success",
                summary_path=summary_path,
                review_bundle_path=Path(self.temp_dir.name) / "stopped-review.json",
                controller_class=FailingController,
            )
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["outcome"], "stopped")
        self.assertNotIn("TOP-SECRET", json.dumps(summary))

    def test_documentation_calls_review_bundle_unredacted_and_possibly_sensitive(self):
        readme = (Path(__file__).resolve().parent / "README.md").read_text(encoding="utf-8")
        record = (
            Path(__file__).resolve().parents[2]
            / "docs/stargazing/006-minimal-continuous-collaboration-loop.md"
        ).read_text(encoding="utf-8")
        self.assertIn("unredacted", readme.lower())
        self.assertIn("may contain sensitive", readme.lower())
        self.assertIn("未脱敏", record)
        self.assertIn("可能包含敏感", record)


if __name__ == "__main__":
    unittest.main()
