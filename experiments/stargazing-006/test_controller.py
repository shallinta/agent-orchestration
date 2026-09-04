import hashlib
import inspect
import json
import errno
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from controller import Controller, ControllerError, RunnerResult
except ModuleNotFoundError:
    Controller = None
    ControllerError = RuntimeError
    RunnerResult = None


HOST = "host-codex"
INVESTIGATOR = "investigator-claude"


def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class FakeState:
    def __init__(self):
        self.request_number = 0
        self.message_number = 0
        self.attempt_number = 0
        self.query_callers = []
        self.thread = {
            "scenario_digest": "a" * 64,
            "scenario": {"goal": "artificial goal"},
            "roles": [{"role_id": HOST}, {"role_id": INVESTIGATOR}],
            "delegation": None,
            "messages": [],
            "call_faults": [],
            "execution_attempts": [],
            "events": [],
        }

    def _request_id(self):
        self.request_number += 1
        return f"req-{self.request_number}"

    def query_thread(self, caller_role_id, payload=None):
        self.query_callers.append(caller_role_id)
        thread = json.loads(json.dumps(self.thread, ensure_ascii=False))
        thread["current_role_id"] = caller_role_id
        return {"status": "ok", "request_id": self._request_id(), "thread": thread}

    def snapshot(self):
        return json.loads(json.dumps(self.thread, ensure_ascii=False))

    def publish_delegation(self, caller_role_id, payload):
        request_id = self._request_id()
        self.thread["delegation"] = {
            "delegation_id": "delegation-1",
            "publisher_role_id": caller_role_id,
            "target_role_id": payload["target_role_id"],
            "task": payload["task"],
            "request_id": request_id,
        }
        return {"status": "ok", "request_id": request_id, "delegation": self.thread["delegation"]}

    def send_message(self, caller_role_id, payload):
        self.message_number += 1
        request_id = self._request_id()
        message = {
            "message_id": f"message-{self.message_number}",
            "sender_role_id": caller_role_id,
            "target_role_id": payload["target_role_id"],
            "body": payload["body"],
            "request_id": request_id,
        }
        self.thread["messages"].append(message)
        return {"status": "ok", "request_id": request_id, "message": message}

    def create_execution_attempt(self, role_id, trigger_kind, trigger_id):
        self.attempt_number += 1
        attempt = {
            "execution_attempt_id": f"attempt-{self.attempt_number}",
            "role_id": role_id,
            "trigger_kind": trigger_kind,
            "trigger_id": trigger_id,
            "outcome": "started",
        }
        self.thread["execution_attempts"].append(attempt)
        return {"execution_attempt": attempt}

    def record_agent_start_failed(self, attempt_id, error_kind="not_found"):
        for attempt in self.thread["execution_attempts"]:
            if attempt["execution_attempt_id"] == attempt_id:
                attempt["outcome"] = "start_failed"
        fault = {
            "fault_id": f"fault-{len(self.thread['call_faults']) + 1}",
            "execution_attempt_id": attempt_id,
            "error_kind": error_kind,
            "kind": "agent_start_failed",
        }
        self.thread["call_faults"].append(fault)
        return {"call_fault": fault}

    def record_agent_turn_completed(self, attempt_id):
        for attempt in self.thread["execution_attempts"]:
            if attempt["execution_attempt_id"] == attempt_id:
                attempt["outcome"] = "completed"
                return {"execution_attempt": attempt}
        raise AssertionError("unknown attempt")


class ScriptedRunner:
    def __init__(self, state, scripts, product, executable):
        self.state = state
        self.scripts = list(scripts)
        self.product = product
        self.executable = executable
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if not self.scripts:
            raise AssertionError("unexpected runner call")
        script = self.scripts.pop(0)
        if isinstance(script, BaseException):
            raise script
        overrides = {}
        if isinstance(script, tuple):
            script, overrides = script
        query = self.state.query_thread(kwargs["role_id"], {})
        request_ids, session_id, final_result = script(self.state, kwargs)
        machine_events = [
            {"kind": "mcp_tool_call", "call_id": "query-call", "tool": "query_thread"},
            {
                "kind": "mcp_tool_result",
                "call_id": "query-call",
                "request_id": query["request_id"],
                "status": "ok",
                "structured_payload": {
                    "current_role_id": query["thread"]["current_role_id"],
                    "scenario_digest": query["thread"]["scenario_digest"],
                    "delegation_id": (
                        query["thread"]["delegation"]["delegation_id"]
                        if query["thread"]["delegation"] else None
                    ),
                    "message_ids": [
                        item["message_id"] for item in query["thread"]["messages"]
                    ],
                    "call_fault_ids": [
                        item.get("fault_id", item["execution_attempt_id"])
                        for item in query["thread"]["call_faults"]
                    ],
                },
            },
            *[
                {"kind": "mcp_tool_result", "request_id": item, "status": "ok"}
                for item in request_ids
            ],
            {"kind": "terminal_result", "status": "completed"},
        ]
        values = {
            "session_id": session_id,
            "machine_events": machine_events,
            "final_result": final_result,
            "process_exit": {"returncode": 0, "timed_out": False},
            "usage": [{"turns": 1}],
            "failures": [],
            "timed_out": False,
            "unexpected_tool_calls": [],
        }
        omit_query = overrides.pop("omit_query", False)
        if omit_query:
            values["machine_events"] = [
                event
                for event in machine_events
                if event.get("call_id") != "query-call"
            ]
        omit_terminal = overrides.pop("omit_terminal", False)
        if omit_terminal:
            values["machine_events"] = [
                event
                for event in values["machine_events"]
                if event.get("kind") != "terminal_result"
            ]
        query_payload = overrides.pop("query_payload", None)
        if query_payload is not None:
            for event in values["machine_events"]:
                if event.get("call_id") == "query-call" and event.get("kind") == "mcp_tool_result":
                    event["structured_payload"] = query_payload
        values.update(overrides)
        return SimpleNamespace(**values)


def publish_delegation(body="delegation chosen by host"):
    def script(state, kwargs):
        result = state.publish_delegation(
            HOST, {"target_role_id": INVESTIGATOR, "task": body}
        )
        return [result["request_id"]], "codex-session", "delegated"

    return script


def send(sender, target, body, session_id):
    def script(state, kwargs):
        result = state.send_message(sender, {"target_role_id": target, "body": body})
        return [result["request_id"]], session_id, body

    return script


def quiet(session_id, final_result="final agent result"):
    def script(state, kwargs):
        return [], session_id, final_result

    return script


def uncorrelated_delegation(state, kwargs):
    state.publish_delegation(HOST, {"target_role_id": INVESTIGATOR, "task": "opaque task"})
    return ["req-not-the-server-result"], "codex-session", "delegated"


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Controller, "controller.py is not implemented")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def make_controller(self, state, host_scripts, investigator_scripts, **overrides):
        root = Path(self.temp_dir.name)
        host_executable = root / "codex"
        investigator_executable = root / "claude"
        host = ScriptedRunner(state, host_scripts, "codex", str(host_executable))
        investigator = ScriptedRunner(
            state, investigator_scripts, "claude", str(investigator_executable)
        )
        options = {
            "state": state,
            "runners": {HOST: host, INVESTIGATOR: investigator},
            "workspaces": {HOST: root / "host", INVESTIGATOR: root / "investigator"},
            "mcp_commands": {
                HOST: ["python", "host-mcp", "--caller-role", HOST],
                INVESTIGATOR: [
                    "python", "investigator-mcp", "--caller-role", INVESTIGATOR
                ],
            },
            "evidence_dirs": {HOST: root / "host-evidence", INVESTIGATOR: root / "investigator-evidence"},
            "timeout_seconds": 300,
        }
        if "summary_path" in inspect.signature(Controller).parameters:
            options["summary_path"] = root / "summary.json"
        options.update(overrides)
        return Controller(**options), host, investigator

    def test_success_routes_five_turns_and_preserves_payload_digests(self):
        state = FakeState()
        delegation_body = "host-authored investigation request"
        first_report = "investigator-authored first report"
        follow_up = "host-authored narrow follow-up"
        second_report = "investigator-authored supplemental report"
        controller, host, investigator = self.make_controller(
            state,
            [
                publish_delegation(delegation_body),
                send(HOST, INVESTIGATOR, follow_up, "codex-session"),
                quiet("codex-session", "host-authored terminal result"),
            ],
            [
                send(INVESTIGATOR, HOST, first_report, "claude-session"),
                send(INVESTIGATOR, HOST, second_report, "claude-session"),
            ],
        )

        result = controller.run_success()

        self.assertEqual(
            [(turn.role_id, turn.mode) for turn in result.turns],
            [(HOST, "start"), (INVESTIGATOR, "start"), (HOST, "resume"),
             (INVESTIGATOR, "resume"), (HOST, "resume")],
        )
        self.assertEqual(result.sessions, {HOST: "codex-session", INVESTIGATOR: "claude-session"})
        self.assertEqual(result.final_result, "host-authored terminal result")
        self.assertEqual(
            [item["outcome"] for item in state.thread["execution_attempts"]],
            ["completed"] * 5,
        )
        self.assertEqual(
            [delivery.payload_digest for delivery in result.deliveries],
            [digest(delegation_body), digest(first_report), digest(follow_up), digest(second_report)],
        )
        self.assertEqual(result.deliveries[0].payload, delegation_body)
        self.assertTrue(all(call["timeout_seconds"] == 300 for call in host.calls + investigator.calls))
        self.assertEqual(
            host.calls[0]["trigger_text"],
            getattr(Controller, "HOST_START_TRIGGER", None),
        )
        self.assertEqual(
            investigator.calls[0]["trigger_text"],
            getattr(Controller, "INVESTIGATOR_START_TRIGGER", None),
        )
        self.assertTrue(
            all(
                call["trigger_text"] == Controller.NEUTRAL_TRIGGER
                for call in host.calls[1:] + investigator.calls[1:]
            )
        )
        self.assertEqual(state.query_callers, [HOST, INVESTIGATOR, HOST, INVESTIGATOR, HOST])
        self.assertTrue(
            all(
                getattr(delivery, "receiver_query_request_id", None)
                for delivery in result.deliveries
            )
        )

        summary_path = Path(self.temp_dir.name) / "summary.json"
        self.assertTrue(summary_path.exists(), "sanitized summary was not written")
        summary = json.loads(summary_path.read_text())
        serialized = json.dumps(summary)
        for secret in (
            delegation_body,
            first_report,
            follow_up,
            second_report,
            "codex-session",
            "claude-session",
            str(Path(self.temp_dir.name)),
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(summary["outcome"], "success")
        self.assertTrue(summary["distinct_role_sessions"])

    def test_controller_source_contains_no_scripted_incident_semantics(self):
        source = inspect.getsource(Controller).lower()
        for forbidden in (
            "idempotency", "duplicate authorization", "root cause", "containment",
            "rollback", "final conclusion",
        ):
            self.assertNotIn(forbidden, source)

    def test_rejects_host_that_does_not_delegate(self):
        controller, _, _ = self.make_controller(FakeState(), [quiet("codex-session")], [])
        with self.assertRaisesRegex(ControllerError, "delegation"):
            controller.run_success()

    def test_rejects_investigator_that_does_not_report(self):
        controller, _, _ = self.make_controller(
            FakeState(), [publish_delegation()], [quiet("claude-session")]
        )
        with self.assertRaisesRegex(ControllerError, "message"):
            controller.run_success()

    def test_rejects_host_that_sends_no_first_follow_up(self):
        controller, _, _ = self.make_controller(
            FakeState(),
            [publish_delegation(), quiet("codex-session")],
            [send(INVESTIGATOR, HOST, "first report", "claude-session")],
        )
        with self.assertRaisesRegex(ControllerError, "follow-up"):
            controller.run_success()

    def test_rejects_wrong_message_sender_or_target(self):
        cases = ((HOST, HOST), (INVESTIGATOR, INVESTIGATOR))
        for sender, target in cases:
            with self.subTest(sender=sender, target=target):
                state = FakeState()
                controller, _, _ = self.make_controller(
                    state,
                    [publish_delegation()],
                    [send(sender, target, "misrouted", "claude-session")],
                )
                with self.assertRaisesRegex(ControllerError, "route"):
                    controller.run_success()

    def test_rejects_duplicate_delivery(self):
        def duplicate_report(state, kwargs):
            result = state.send_message(INVESTIGATOR, {"target_role_id": HOST, "body": "report"})
            state.thread["messages"].append(dict(result["message"]))
            return [result["request_id"]], "claude-session", "report"

        controller, _, _ = self.make_controller(
            FakeState(), [publish_delegation()], [duplicate_report]
        )
        with self.assertRaisesRegex(ControllerError, "duplicate"):
            controller.run_success()

    def test_rejects_session_drift(self):
        controller, _, _ = self.make_controller(
            FakeState(),
            [
                publish_delegation(),
                send(HOST, INVESTIGATOR, "follow-up", "different-codex-session"),
            ],
            [send(INVESTIGATOR, HOST, "report", "claude-session")],
        )
        with self.assertRaisesRegex(ControllerError, "session"):
            controller.run_success()

    def test_rejects_same_session_id_for_both_roles(self):
        controller, _, _ = self.make_controller(
            FakeState(),
            [publish_delegation()],
            [send(INVESTIGATOR, HOST, "report", "codex-session")],
        )
        with self.assertRaisesRegex(ControllerError, "distinct"):
            controller.run_success()

    def test_enforces_seven_turn_limit(self):
        state = FakeState()
        controller, _, _ = self.make_controller(
            state,
            [
                publish_delegation(),
                send(HOST, INVESTIGATOR, "follow-up-1", "codex-session"),
                send(HOST, INVESTIGATOR, "follow-up-2", "codex-session"),
                send(HOST, INVESTIGATOR, "follow-up-3", "codex-session"),
            ],
            [
                send(INVESTIGATOR, HOST, "report-1", "claude-session"),
                send(INVESTIGATOR, HOST, "report-2", "claude-session"),
                send(INVESTIGATOR, HOST, "report-3", "claude-session"),
            ],
            max_turns=7,
        )
        with self.assertRaisesRegex(ControllerError, "turn limit"):
            controller.run_success()

    def test_rejects_uncorrelated_harness_request_id(self):
        controller, _, _ = self.make_controller(
            FakeState(), [uncorrelated_delegation], []
        )
        with self.assertRaisesRegex(ControllerError, "request_id"):
            controller.run_success()

    def test_rejects_unusable_runner_results(self):
        cases = (
            ("failures", {"failures": [{"kind": "turn.failed"}]}),
            ("timed out", {"timed_out": True}),
            ("unexpected", {"unexpected_tool_calls": [{"tool": "Read"}]}),
            ("process exit", {"process_exit": {"returncode": 7, "timed_out": False}}),
            (
                "terminal",
                {"omit_terminal": True},
            ),
        )
        for label, overrides in cases:
            with self.subTest(label=label):
                controller, _, _ = self.make_controller(
                    FakeState(),
                    [
                        (publish_delegation(), overrides),
                        send(HOST, INVESTIGATOR, "follow-up", "codex-session"),
                        quiet("codex-session"),
                    ],
                    [
                        send(INVESTIGATOR, HOST, "report-1", "claude-session"),
                        send(INVESTIGATOR, HOST, "report-2", "claude-session"),
                    ],
                )
                with self.assertRaisesRegex(ControllerError, label):
                    controller.run_success()

    def test_rejects_turn_without_nonempty_final_result(self):
        controller, _, _ = self.make_controller(
            FakeState(), [quiet("codex-session", "")], []
        )
        with self.assertRaisesRegex(ControllerError, "final_result"):
            controller.run_success()

    def test_rejects_turn_without_successful_query_thread_event(self):
        controller, _, _ = self.make_controller(
            FakeState(),
            [
                (publish_delegation(), {"omit_query": True}),
                send(HOST, INVESTIGATOR, "follow-up", "codex-session"),
                quiet("codex-session"),
            ],
            [
                send(INVESTIGATOR, HOST, "report-1", "claude-session"),
                send(INVESTIGATOR, HOST, "report-2", "claude-session"),
            ],
        )
        with self.assertRaisesRegex(ControllerError, "query_thread"):
            controller.run_success()

    def test_rejects_query_that_does_not_show_the_delivered_fact(self):
        controller, _, _ = self.make_controller(
            FakeState(),
            [publish_delegation()],
            [
                (
                    send(INVESTIGATOR, HOST, "report", "claude-session"),
                    {
                        "query_payload": {
                            "current_role_id": INVESTIGATOR,
                            "scenario_digest": "a" * 64,
                            "delegation_id": None,
                            "message_ids": [],
                            "call_fault_ids": [],
                        }
                    },
                )
            ],
        )
        with self.assertRaisesRegex(ControllerError, "query.*delegation"):
            controller.run_success()

    def test_rejects_runner_product_or_mcp_caller_role_mismatch(self):
        state = FakeState()
        controller, host, _ = self.make_controller(
            state,
            [
                publish_delegation(),
                send(HOST, INVESTIGATOR, "follow-up", "codex-session"),
                quiet("codex-session"),
            ],
            [
                send(INVESTIGATOR, HOST, "report-1", "claude-session"),
                send(INVESTIGATOR, HOST, "report-2", "claude-session"),
            ],
        )
        host.product = "claude"
        with self.assertRaisesRegex(ControllerError, "runner product"):
            controller.run_success()

        state = FakeState()
        controller, _, _ = self.make_controller(
            state,
            [
                publish_delegation(),
                send(HOST, INVESTIGATOR, "follow-up", "codex-session"),
                quiet("codex-session"),
            ],
            [
                send(INVESTIGATOR, HOST, "report-1", "claude-session"),
                send(INVESTIGATOR, HOST, "report-2", "claude-session"),
            ],
            mcp_commands={
                HOST: ["python", "mcp", "--caller-role", INVESTIGATOR],
                INVESTIGATOR: ["python", "mcp", "--caller-role", INVESTIGATOR],
            },
        )
        with self.assertRaisesRegex(ControllerError, "caller role"):
            controller.run_success()

    def test_success_total_deadline_is_enforced_after_a_turn(self):
        parameters = inspect.signature(Controller).parameters
        self.assertIn("success_deadline_seconds", parameters)
        self.assertIn("clock", parameters)

        class Clock:
            value = 0.0

            def __call__(self):
                return self.value

        clock = Clock()

        def slow_delegation(state, kwargs):
            result = state.publish_delegation(
                HOST,
                {"target_role_id": INVESTIGATOR, "task": "opaque delegation"},
            )
            clock.value = 31.0
            return [result["request_id"]], "codex-session", "delegated"

        controller, _, _ = self.make_controller(
            FakeState(),
            [slow_delegation],
            [],
            success_deadline_seconds=30,
            clock=clock,
        )
        with self.assertRaisesRegex(ControllerError, "deadline"):
            controller.run_success()

    def test_start_failure_records_fault_and_resumes_same_host_without_claude_result(self):
        state = FakeState()
        missing = str(Path(self.temp_dir.name) / "claude")
        controller, host, investigator = self.make_controller(
            state,
            [publish_delegation("failure-run delegation"), quiet("codex-session", "blocked result")],
            [FileNotFoundError(errno.ENOENT, "missing executable", missing)],
        )

        result = controller.run_start_failure()

        self.assertEqual([(turn.role_id, turn.mode) for turn in result.turns], [(HOST, "start"), (HOST, "resume")])
        self.assertEqual(result.sessions, {HOST: "codex-session"})
        self.assertEqual(result.final_result, "blocked result")
        self.assertIsNone(result.investigator_result)
        self.assertEqual(len(state.thread["call_faults"]), 1)
        self.assertEqual(state.thread["call_faults"][0]["kind"], "agent_start_failed")
        self.assertEqual(state.thread["messages"], [])
        self.assertEqual(len(investigator.calls), 1)
        self.assertEqual(host.calls[1]["session_id"], "codex-session")
        failure_trigger = host.calls[1]["trigger_text"]
        self.assertNotEqual(failure_trigger, Controller.NEUTRAL_TRIGGER)
        self.assertEqual(failure_trigger, Controller.START_FAILURE_HOST_TRIGGER)
        for boundary in (
            "Query current Harness facts",
            "investigator did not start",
            "no investigator execution result",
            "Do not describe the delegation as completed or fulfilled",
            "Do not substitute for the delegation by producing the delegated analysis yourself",
            "report the blockage",
            "unexecuted follow-up options",
            "request a decision",
        ):
            self.assertIn(boundary, failure_trigger)
        self.assertTrue(getattr(result.turns[-1], "query_request_id", None))
        self.assertEqual(state.query_callers, [HOST, HOST])
        summary_path = Path(self.temp_dir.name) / "summary.json"
        self.assertTrue(summary_path.exists(), "sanitized summary was not written")
        summary = json.loads(summary_path.read_text())
        self.assertEqual(summary["outcome"], "start_failed")

    def test_start_failure_rejects_any_investigator_message(self):
        missing = str(Path(self.temp_dir.name) / "claude")

        def message_then_missing(state, kwargs):
            state.send_message(
                INVESTIGATOR, {"target_role_id": HOST, "body": "must not survive"}
            )
            raise FileNotFoundError(errno.ENOENT, "missing executable", missing)

        controller, _, _ = self.make_controller(
            FakeState(),
            [publish_delegation("failure-run delegation"), quiet("codex-session")],
            [message_then_missing],
        )

        with self.assertRaisesRegex(ControllerError, "message"):
            controller.run_start_failure()

    def test_start_failure_rejects_non_enoent_or_wrong_executable(self):
        cases = (
            FileNotFoundError(errno.EACCES, "denied", str(Path(self.temp_dir.name) / "claude")),
            FileNotFoundError(errno.ENOENT, "missing", str(Path(self.temp_dir.name) / "other")),
        )
        for failure in cases:
            with self.subTest(errno=failure.errno, filename=failure.filename):
                state = FakeState()
                controller, _, _ = self.make_controller(
                    state,
                    [
                        publish_delegation("failure-run delegation"),
                        quiet("codex-session"),
                    ],
                    [failure],
                )
                with self.assertRaisesRegex(ControllerError, "start failure"):
                    controller.run_start_failure()
                self.assertEqual(state.thread["call_faults"], [])


if __name__ == "__main__":
    unittest.main()
