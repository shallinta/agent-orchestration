"""Throwaway file-backed synthetic Harness facts for Stargazing 6."""

import hashlib
import json
import os
import uuid
from pathlib import Path


ROLES = ("host-codex", "investigator-claude")


def canonical_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


SCENARIO_DIGEST = canonical_digest(
    json.loads(Path(__file__).with_name("scenario.json").read_text(encoding="utf-8"))
)


class HarnessState:
    def __init__(self, state_path, log_path, scenario_path):
        self.state_path = Path(state_path)
        self.log_path = Path(log_path)
        self.scenario_path = Path(scenario_path)
        self.scenario = json.loads(self.scenario_path.read_text(encoding="utf-8"))
        self.scenario_digest = canonical_digest(self.scenario)
        if not self.state_path.exists():
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self._write(
                {
                    "scenario_digest": self.scenario_digest,
                    "roles": list(ROLES),
                    "delegation": None,
                    "messages": [],
                    "execution_attempts": [],
                    "call_faults": [],
                    "events": [],
                }
            )
        elif self.snapshot().get("scenario_digest") != self.scenario_digest:
            raise ValueError("scenario digest does not match existing run state")

    def snapshot(self):
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def controller_snapshot(self):
        """Read trusted controller facts without impersonating a role or logging a query."""
        return self.snapshot()

    def query_thread(self, caller_role_id, payload=None):
        request_id = self._request_id()
        if caller_role_id not in ROLES or not isinstance(payload, dict) or payload:
            return self._reject(request_id, caller_role_id, "invalid_params")
        state = self.snapshot()
        self._log(request_id, caller_role_id, "query_thread", "ok", {})
        return {
            "status": "ok",
            "request_id": request_id,
            "thread": {
                "current_role_id": caller_role_id,
                "scenario": self.scenario,
                "scenario_digest": state["scenario_digest"],
                "roles": state["roles"],
                "delegation": state["delegation"],
                "messages": state["messages"],
                "execution_attempts": state["execution_attempts"],
                "call_faults": state["call_faults"],
                "events": state["events"],
            },
        }

    def publish_delegation(self, caller_role_id, payload):
        request_id = self._request_id()
        if not self._exact_strings(payload, {"target_role_id", "task"}):
            return self._reject(request_id, caller_role_id, "invalid_params")
        if caller_role_id != "host-codex":
            return self._reject(request_id, caller_role_id, "forbidden")
        if payload["target_role_id"] != "investigator-claude":
            return self._reject(request_id, caller_role_id, "not_found")
        state = self.snapshot()
        if state["delegation"] is not None:
            return self._reject(request_id, caller_role_id, "conflict")
        delegation = {
            "delegation_id": "delegation-1",
            "publisher_role_id": caller_role_id,
            "target_role_id": "investigator-claude",
            "task": payload["task"],
            "request_id": request_id,
        }
        state["delegation"] = delegation
        event = self._append_event(state, "delegation_published", request_id, payload)
        self._write(state)
        self._log(request_id, caller_role_id, "publish_delegation", "ok", event)
        return {"status": "ok", "request_id": request_id, "delegation": delegation}

    def send_message(self, caller_role_id, payload):
        request_id = self._request_id()
        if not self._exact_strings(payload, {"target_role_id", "body"}):
            return self._reject(request_id, caller_role_id, "invalid_params")
        if caller_role_id not in ROLES:
            return self._reject(request_id, caller_role_id, "forbidden")
        expected_target = (
            "investigator-claude" if caller_role_id == "host-codex" else "host-codex"
        )
        if payload["target_role_id"] != expected_target:
            return self._reject(request_id, caller_role_id, "not_found")
        state = self.snapshot()
        message = {
            "message_id": "message-{}".format(len(state["messages"]) + 1),
            "sender_role_id": caller_role_id,
            "target_role_id": expected_target,
            "body": payload["body"],
            "request_id": request_id,
        }
        state["messages"].append(message)
        event = self._append_event(state, "message_sent", request_id, payload)
        self._write(state)
        self._log(request_id, caller_role_id, "send_message", "ok", event)
        return {"status": "ok", "request_id": request_id, "message": message}

    def create_execution_attempt(self, role_id, trigger_kind, trigger_id):
        request_id = self._request_id()
        state = self.snapshot()
        attempt = {
            "execution_attempt_id": "attempt-{}".format(
                len(state["execution_attempts"]) + 1
            ),
            "role_id": role_id,
            "trigger_kind": trigger_kind,
            "trigger_id": trigger_id,
            "outcome": "started",
        }
        state["execution_attempts"].append(attempt)
        event = self._append_event(state, "agent_start_attempted", request_id, attempt)
        self._write(state)
        self._log(request_id, "controller", "agent_start_attempted", "ok", event)
        return {"status": "ok", "request_id": request_id, "execution_attempt": attempt}

    def record_agent_start_failed(self, execution_attempt_id, error_kind="not_found"):
        request_id = self._request_id()
        state = self.snapshot()
        attempt = next(
            (
                item
                for item in state["execution_attempts"]
                if item["execution_attempt_id"] == execution_attempt_id
            ),
            None,
        )
        if attempt is None or attempt["outcome"] != "started":
            return self._reject(request_id, "controller", "invalid_params")
        attempt["outcome"] = "start_failed"
        fault = {
            "fault_id": "fault-{}".format(len(state["call_faults"]) + 1),
            "execution_attempt_id": execution_attempt_id,
            "kind": "agent_start_failed",
            "error_kind": error_kind,
            "request_id": request_id,
        }
        state["call_faults"].append(fault)
        event = self._append_event(state, "agent_start_failed", request_id, fault)
        self._write(state)
        self._log(request_id, "controller", "agent_start_failed", "ok", event)
        return {"status": "ok", "request_id": request_id, "call_fault": fault}

    def record_agent_turn_completed(self, execution_attempt_id):
        request_id = self._request_id()
        state = self.snapshot()
        attempt = next(
            (
                item
                for item in state["execution_attempts"]
                if item["execution_attempt_id"] == execution_attempt_id
            ),
            None,
        )
        if attempt is None or attempt["outcome"] != "started":
            return self._reject(request_id, "controller", "invalid_params")
        attempt["outcome"] = "completed"
        event = self._append_event(state, "agent_turn_completed", request_id, attempt)
        self._write(state)
        self._log(request_id, "controller", "agent_turn_completed", "ok", event)
        return {
            "status": "ok",
            "request_id": request_id,
            "execution_attempt": attempt,
        }

    @staticmethod
    def _exact_strings(payload, expected):
        return (
            isinstance(payload, dict)
            and set(payload) == expected
            and all(isinstance(value, str) and value.strip() for value in payload.values())
        )

    @staticmethod
    def _request_id():
        return "req-" + uuid.uuid4().hex

    @staticmethod
    def _append_event(state, event_type, request_id, payload):
        event = {
            "sequence": len(state["events"]) + 1,
            "type": event_type,
            "request_id": request_id,
            "payload_sha256": canonical_digest(payload),
        }
        state["events"].append(event)
        return event

    def _reject(self, request_id, caller_role_id, code):
        self._log(request_id, caller_role_id, "invalid", code, {})
        return {
            "status": "error",
            "request_id": request_id,
            "error": {"code": code, "message": "request rejected"},
        }

    def _log(self, request_id, caller_role_id, operation, outcome, event):
        safe_caller = caller_role_id if caller_role_id in ROLES else "controller"
        safe_operation = operation if operation in {
            "query_thread",
            "publish_delegation",
            "send_message",
            "agent_start_attempted",
            "agent_start_failed",
            "agent_turn_completed",
        } else "invalid"
        facts = {}
        if event:
            facts = {
                "sequence": event["sequence"],
                "payload_sha256": event["payload_sha256"],
            }
        entry = {
            "request_id": request_id,
            "caller_role_id": safe_caller,
            "operation": safe_operation,
            "outcome": outcome,
            "facts": facts,
        }
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry, separators=(",", ":")) + "\n")

    def _write(self, state):
        temporary = self.state_path.with_name(
            self.state_path.name + ".tmp-" + uuid.uuid4().hex
        )
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)
