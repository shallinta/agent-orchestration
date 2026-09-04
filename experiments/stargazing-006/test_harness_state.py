import hashlib
import json
import tempfile
import unittest
from pathlib import Path

try:
    from harness_state import HarnessState
except ModuleNotFoundError:
    HarnessState = None


HERE = Path(__file__).resolve().parent


def digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class HarnessStateTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(HarnessState, "harness state is absent")
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.state_path = root / "state.json"
        self.log_path = root / "facts.jsonl"
        self.state = HarnessState(self.state_path, self.log_path, HERE / "scenario.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fresh_state_has_only_fixed_roles_and_no_collaboration_facts(self):
        snapshot = self.state.snapshot()
        scenario = json.loads((HERE / "scenario.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot["scenario_digest"], digest(scenario))
        self.assertEqual(snapshot["roles"], ["host-codex", "investigator-claude"])
        self.assertIsNone(snapshot["delegation"])
        self.assertEqual(snapshot["messages"], [])
        self.assertEqual(snapshot["execution_attempts"], [])
        self.assertEqual(snapshot["call_faults"], [])

    def test_delegation_is_host_only_and_payload_cannot_inject_caller(self):
        before = self.state_path.read_bytes()
        rejected = self.state.publish_delegation(
            "investigator-claude",
            {"target_role_id": "investigator-claude", "task": "not allowed"},
        )
        self.assertEqual(rejected["error"]["code"], "forbidden")
        self.assertEqual(self.state_path.read_bytes(), before)

        injected = self.state.publish_delegation(
            "host-codex",
            {
                "target_role_id": "investigator-claude",
                "task": "must not write",
                "caller_role_id": "investigator-claude",
            },
        )
        self.assertEqual(injected["error"]["code"], "invalid_params")
        self.assertEqual(self.state_path.read_bytes(), before)

        accepted = self.state.publish_delegation(
            "host-codex",
            {"target_role_id": "investigator-claude", "task": "host-authored task"},
        )
        self.assertEqual(accepted["status"], "ok")
        self.assertEqual(
            set(accepted["delegation"]),
            {"delegation_id", "publisher_role_id", "target_role_id", "task", "request_id"},
        )

    def test_both_roles_can_send_only_directed_messages(self):
        first = self.state.send_message(
            "host-codex",
            {"target_role_id": "investigator-claude", "body": "host follow-up"},
        )
        second = self.state.send_message(
            "investigator-claude",
            {"target_role_id": "host-codex", "body": "investigator report"},
        )
        self.assertEqual(first["status"], "ok")
        self.assertEqual(second["status"], "ok")
        self.assertEqual(
            set(second["message"]),
            {"message_id", "sender_role_id", "target_role_id", "body", "request_id"},
        )

        before = self.state_path.read_bytes()
        rejected = self.state.send_message(
            "host-codex",
            {"target_role_id": "TOP-SECRET arbitrary-target", "body": "do not log"},
        )
        self.assertEqual(rejected["error"]["code"], "not_found")
        self.assertEqual(self.state_path.read_bytes(), before)

    def test_start_failure_is_controller_fact_not_agent_output(self):
        attempt = self.state.create_execution_attempt(
            "investigator-claude", "delegation", "delegation-1"
        )["execution_attempt"]
        fault = self.state.record_agent_start_failed(attempt["execution_attempt_id"], "not_found")
        snapshot = self.state.snapshot()

        self.assertEqual(snapshot["execution_attempts"][0]["outcome"], "start_failed")
        self.assertEqual(
            set(snapshot["execution_attempts"][0]),
            {"execution_attempt_id", "role_id", "trigger_kind", "trigger_id", "outcome"},
        )
        self.assertEqual(fault["status"], "ok")
        self.assertEqual(snapshot["messages"], [])
        serialized = json.dumps(snapshot)
        for forbidden_key in ("session_id", "delivery", "completion", "agent_result"):
            self.assertNotIn(forbidden_key, serialized)

    def test_successful_execution_attempt_reaches_an_explicit_terminal_outcome(self):
        attempt = self.state.create_execution_attempt(
            "host-codex", "run", "run-start"
        )["execution_attempt"]
        completed = self.state.record_agent_turn_completed(
            attempt["execution_attempt_id"]
        )
        self.assertEqual(completed["execution_attempt"]["outcome"], "completed")
        self.assertEqual(
            self.state.snapshot()["execution_attempts"][0]["outcome"], "completed"
        )

    def test_events_and_logs_are_correlated_and_redacted(self):
        secret_task = "TOP-SECRET delegation body"
        secret_message = "TOP-SECRET message body"
        self.state.publish_delegation(
            "host-codex",
            {"target_role_id": "investigator-claude", "task": secret_task},
        )
        self.state.send_message(
            "investigator-claude",
            {"target_role_id": "host-codex", "body": secret_message},
        )
        snapshot = self.state.snapshot()
        logs = [json.loads(line) for line in self.log_path.read_text().splitlines()]

        self.assertEqual([event["sequence"] for event in snapshot["events"]], [1, 2])
        request_ids = [event["request_id"] for event in snapshot["events"]]
        self.assertEqual(len(request_ids), len(set(request_ids)))
        self.assertEqual({entry["request_id"] for entry in logs}, set(request_ids))
        for event in snapshot["events"]:
            self.assertRegex(event["payload_sha256"], r"^[0-9a-f]{64}$")

        serialized_logs = json.dumps(logs)
        for secret in (
            secret_task,
            secret_message,
            "prompt",
            "credential",
            "session_id",
            "workspace",
            str(self.state_path.parent),
        ):
            self.assertNotIn(secret, serialized_logs)

    def test_query_exposes_scenario_without_hidden_oracle(self):
        result = self.state.query_thread("host-codex", {})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["thread"]["current_role_id"], "host-codex")
        self.assertEqual(result["thread"]["scenario_digest"], self.state.snapshot()["scenario_digest"])
        self.assertNotIn("oracle", json.dumps(result, ensure_ascii=False).lower())

    def test_query_requires_an_empty_object_and_trusted_snapshot_does_not_log(self):
        for invalid in (None, [], "", 0):
            with self.subTest(invalid=invalid):
                result = self.state.query_thread("host-codex", invalid)
                self.assertEqual(result["error"]["code"], "invalid_params")

        before = self.log_path.read_text(encoding="utf-8")
        snapshot = self.state.controller_snapshot()
        self.assertNotIn("current_role_id", snapshot)
        self.assertEqual(self.log_path.read_text(encoding="utf-8"), before)

    def test_scenario_digest_is_computed_and_existing_state_is_revalidated(self):
        alternate = Path(self.temp_dir.name) / "alternate.json"
        alternate.write_text('{"goal":"different","acceptance_criteria":["x"],"evidence":[]}', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "scenario digest"):
            HarnessState(self.state_path, self.log_path, alternate)


if __name__ == "__main__":
    unittest.main()
