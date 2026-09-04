"""Deterministic fact router for the disposable Stargazing 6 probe."""

from dataclasses import dataclass, field
import errno
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Protocol, Sequence


HOST_ROLE_ID = "host-codex"
INVESTIGATOR_ROLE_ID = "investigator-claude"
ROLE_PRODUCTS = {HOST_ROLE_ID: "codex", INVESTIGATOR_ROLE_ID: "claude"}


class ControllerError(RuntimeError):
    """Raised when structural evidence cannot support the next route."""


@dataclass(frozen=True)
class RunnerResult:
    session_id: str | None
    machine_events: Sequence[Mapping[str, Any]]
    final_result: Any
    process_exit: Any
    usage: Any
    failures: Sequence[Mapping[str, Any]] = ()
    timed_out: bool = False
    unexpected_tool_calls: Sequence[Mapping[str, Any]] = ()


class Runner(Protocol):
    product: str
    executable: str

    def run(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class TurnEvidence:
    role_id: str
    mode: str
    session_id: str
    query_request_id: str
    query_facts: Mapping[str, Any]
    machine_events: Sequence[Mapping[str, Any]]
    final_result: Any
    process_exit: Any
    usage: Any


@dataclass(frozen=True)
class DeliveryEvidence:
    fact_kind: str
    fact_id: str
    sender_role_id: str
    target_role_id: str
    payload: str
    send_digest: str
    payload_digest: str
    receiver_query_request_id: str


@dataclass
class ControllerResult:
    turns: list[TurnEvidence] = field(default_factory=list)
    deliveries: list[DeliveryEvidence] = field(default_factory=list)
    sessions: dict[str, str] = field(default_factory=dict)
    final_result: Any = None
    investigator_result: Any = None
    call_fault: Mapping[str, Any] | None = None
    outcome: str | None = None


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _value(result: Any, name: str, default: Any = ...) -> Any:
    if isinstance(result, Mapping) and name in result:
        return result[name]
    if not isinstance(result, Mapping) and hasattr(result, name):
        return getattr(result, name)
    if default is not ...:
        return default
    raise ControllerError(f"runner result is missing {name}")


def _request_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        if isinstance(value.get("request_id"), str):
            found.add(value["request_id"])
        for item in value.values():
            found.update(_request_ids(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            found.update(_request_ids(item))
    return found


def _query_evidence(events: Sequence[Mapping[str, Any]]) -> tuple[str, Mapping[str, Any]]:
    results = {
        item.get("call_id"): item
        for item in events
        if isinstance(item, Mapping)
        and item.get("kind") == "mcp_tool_result"
        and item.get("status") == "ok"
        and item.get("is_error") is not True
        and isinstance(item.get("request_id"), str)
    }
    for item in events:
        if not isinstance(item, Mapping) or item.get("kind") != "mcp_tool_call":
            continue
        if item.get("tool") != "query_thread":
            continue
        if isinstance(item.get("request_id"), str) and item.get("status") in (
            None,
            "ok",
            "completed",
        ):
            payload = item.get("structured_payload")
            if isinstance(payload, Mapping):
                return item["request_id"], payload
        matched = results.get(item.get("call_id"))
        if matched is not None:
            payload = matched.get("structured_payload")
            if isinstance(payload, Mapping):
                return matched["request_id"], payload
    raise ControllerError("turn has no successful query_thread event")


def _terminal_completed(events: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        isinstance(item, Mapping)
        and item.get("kind") == "terminal_result"
        and (
            item.get("status") == "completed"
            or item.get("terminal_reason") == "completed"
        )
        for item in events
    )


def write_sanitized_summary(result: ControllerResult, path: Path) -> Path:
    if result.outcome not in {"success", "start_failed"}:
        raise ControllerError("summary outcome is not final")
    summary = {
        "schema": "stargazing-006-sanitized-summary-v1",
        "outcome": result.outcome,
        "distinct_role_sessions": len(set(result.sessions.values()))
        == len(result.sessions),
        "turn_count": len(result.turns),
        "turns": [
            {
                "role_id": turn.role_id if turn.role_id in ROLE_PRODUCTS else "invalid",
                "mode": turn.mode if turn.mode in {"start", "resume"} else "invalid",
                "session_present": bool(turn.session_id),
                "query_request_id_present": bool(turn.query_request_id),
            }
            for turn in result.turns
        ],
        "delivery_count": len(result.deliveries),
        "deliveries": [
            {
                "fact_kind": item.fact_kind
                if item.fact_kind in {"delegation", "message"}
                else "invalid",
                "sender_role_id": item.sender_role_id
                if item.sender_role_id in ROLE_PRODUCTS
                else "invalid",
                "target_role_id": item.target_role_id
                if item.target_role_id in ROLE_PRODUCTS
                else "invalid",
                "send_digest": item.send_digest,
                "delivery_digest": item.payload_digest,
                "receiver_query_request_id_present": bool(item.receiver_query_request_id),
            }
            for item in result.deliveries
        ],
        "call_fault": None,
    }
    if result.call_fault is not None:
        summary["call_fault"] = {
            "kind": "agent_start_failed"
            if result.call_fault.get("kind") == "agent_start_failed"
            else "invalid",
            "error_kind": "not_found"
            if result.call_fault.get("error_kind") == "not_found"
            else "invalid",
        }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return destination


class Controller:
    """Route facts without interpreting natural-language payloads."""

    HOST_START_TRIGGER = "Act as the host role. Query current Harness facts and proceed."
    INVESTIGATOR_START_TRIGGER = (
        "Act as the investigator role. Query current Harness facts and proceed."
    )
    NEUTRAL_TRIGGER = "Query current Harness facts and continue."
    START_FAILURE_HOST_TRIGGER = (
        "Query current Harness facts. State that the investigator did not start and "
        "there is no investigator execution result. Do not describe the delegation as "
        "completed or fulfilled. Do not substitute for the delegation by producing the "
        "delegated analysis yourself. You may report the blockage and present only "
        "unexecuted follow-up options or request a decision."
    )

    def __init__(
        self,
        *,
        state: Any,
        runners: Mapping[str, Runner],
        workspaces: Mapping[str, Path],
        mcp_commands: Mapping[str, Sequence[str]],
        evidence_dirs: Mapping[str, Path],
        timeout_seconds: int = 300,
        max_turns: int = 7,
        summary_path: Path | None = None,
        success_deadline_seconds: int = 1800,
        failure_deadline_seconds: int = 600,
        clock: Callable[[], float] = time.monotonic,
    ):
        if max_turns < 5:
            raise ValueError("max_turns must allow the minimum five-turn sequence")
        if success_deadline_seconds <= 0 or failure_deadline_seconds <= 0:
            raise ValueError("deadlines must be positive")
        self.state = state
        self.runners = runners
        self.workspaces = workspaces
        self.mcp_commands = mcp_commands
        self.evidence_dirs = evidence_dirs
        self.timeout_seconds = timeout_seconds
        self.max_turns = max_turns
        self.summary_path = Path(summary_path) if summary_path is not None else None
        self.success_deadline_seconds = success_deadline_seconds
        self.failure_deadline_seconds = failure_deadline_seconds
        self.clock = clock
        self._deadline_at: float | None = None
        self._current_role: str | None = None

    def run_success(self) -> ControllerResult:
        self._begin_deadline(self.success_deadline_seconds)
        result = ControllerResult()
        initial = self._snapshot()
        host_turn = self._invoke(result, HOST_ROLE_ID, "start", None, "run", "run-start")
        after_host = self._snapshot()
        delegation = self._new_delegation(initial, after_host)
        self._validate_delegation(delegation)
        self._correlate(host_turn, delegation)

        seen_ids = self._message_ids(after_host)
        investigator_turn = self._invoke(
            result,
            INVESTIGATOR_ROLE_ID,
            "start",
            None,
            "delegation",
            delegation["delegation_id"],
        )
        result.deliveries.append(self._delegation_delivery(delegation, investigator_turn))
        after_investigator = self._snapshot()
        report = self._one_new_message(after_investigator, seen_ids, "message")
        self._validate_route(report, INVESTIGATOR_ROLE_ID, HOST_ROLE_ID)
        self._correlate(investigator_turn, report)
        result.investigator_result = investigator_turn.final_result
        seen_ids.add(report["message_id"])

        required_follow_up = True
        while True:
            host_turn = self._invoke(
                result,
                HOST_ROLE_ID,
                "resume",
                result.sessions[HOST_ROLE_ID],
                "message",
                report["message_id"],
            )
            result.deliveries.append(self._message_delivery(report, host_turn))
            new_messages = self._new_messages(self._snapshot(), seen_ids)
            if not new_messages:
                if required_follow_up:
                    raise ControllerError("host produced no follow-up message")
                result.final_result = host_turn.final_result
                return self._finish(result, "success")
            if len(new_messages) != 1:
                raise ControllerError("a turn must create exactly one message")

            follow_up = new_messages[0]
            self._validate_route(follow_up, HOST_ROLE_ID, INVESTIGATOR_ROLE_ID)
            self._correlate(host_turn, follow_up)
            seen_ids.add(follow_up["message_id"])
            required_follow_up = False
            if len(result.turns) >= self.max_turns:
                raise ControllerError("turn limit exceeded")

            investigator_turn = self._invoke(
                result,
                INVESTIGATOR_ROLE_ID,
                "resume",
                result.sessions[INVESTIGATOR_ROLE_ID],
                "message",
                follow_up["message_id"],
            )
            result.deliveries.append(self._message_delivery(follow_up, investigator_turn))
            report = self._one_new_message(self._snapshot(), seen_ids, "message")
            self._validate_route(report, INVESTIGATOR_ROLE_ID, HOST_ROLE_ID)
            self._correlate(investigator_turn, report)
            result.investigator_result = investigator_turn.final_result
            seen_ids.add(report["message_id"])
            if len(result.turns) >= self.max_turns:
                raise ControllerError("turn limit exceeded")

    def run_start_failure(self) -> ControllerResult:
        self._begin_deadline(self.failure_deadline_seconds)
        result = ControllerResult()
        initial = self._snapshot()
        host_turn = self._invoke(result, HOST_ROLE_ID, "start", None, "run", "run-start")
        after_host = self._snapshot()
        delegation = self._new_delegation(initial, after_host)
        self._validate_delegation(delegation)
        self._correlate(host_turn, delegation)

        self._validate_binding(INVESTIGATOR_ROLE_ID)
        executable = Path(self.runners[INVESTIGATOR_ROLE_ID].executable)
        if not executable.is_absolute():
            raise ControllerError("failure run requires an absolute investigator executable")
        attempt = self._create_attempt(
            INVESTIGATOR_ROLE_ID, "delegation", delegation["delegation_id"]
        )
        try:
            self._run_bound(INVESTIGATOR_ROLE_ID, "start", None)
        except FileNotFoundError as exc:
            if exc.errno != errno.ENOENT or not self._same_path(exc.filename, executable):
                raise ControllerError("unexpected investigator start failure") from exc
            failure = self.state.record_agent_start_failed(
                attempt["execution_attempt_id"], error_kind="not_found"
            )
        else:
            raise ControllerError("investigator unexpectedly started in failure run")
        self._check_deadline()

        call_fault = failure.get("call_fault", failure)
        if (
            not isinstance(call_fault, Mapping)
            or call_fault.get("kind") != "agent_start_failed"
            or call_fault.get("error_kind") != "not_found"
            or call_fault.get("execution_attempt_id") != attempt["execution_attempt_id"]
        ):
            raise ControllerError("agent start failure did not create the expected call fault")
        after_failure = self._snapshot()
        if after_failure.get("messages") != after_host.get("messages"):
            raise ControllerError("agent start failure created a role message")
        result.call_fault = call_fault
        host_turn = self._invoke(
            result,
            HOST_ROLE_ID,
            "resume",
            result.sessions[HOST_ROLE_ID],
            "call_fault",
            attempt["execution_attempt_id"],
        )
        if not any(
            isinstance(item, Mapping)
            and item.get("execution_attempt_id") == attempt["execution_attempt_id"]
            for item in self._snapshot().get("call_faults", [])
        ):
            raise ControllerError("host query could not read the call fault")
        fault_id = call_fault.get("fault_id")
        if not isinstance(fault_id, str) or fault_id not in host_turn.query_facts.get(
            "call_fault_ids", []
        ):
            raise ControllerError("host query did not include the call fault")
        result.final_result = host_turn.final_result
        return self._finish(result, "start_failed")

    def _begin_deadline(self, seconds: int) -> None:
        self._deadline_at = self.clock() + seconds

    def _check_deadline(self) -> None:
        if self._deadline_at is not None and self.clock() > self._deadline_at:
            raise ControllerError("probe deadline exceeded")

    def _finish(self, result: ControllerResult, outcome: str) -> ControllerResult:
        self._check_deadline()
        result.outcome = outcome
        if self.summary_path is not None:
            write_sanitized_summary(result, self.summary_path)
        return result

    def _snapshot(self) -> Mapping[str, Any]:
        snapshot = self.state.snapshot()
        if not isinstance(snapshot, Mapping):
            raise ControllerError("trusted state snapshot is invalid")
        self._assert_no_duplicate_messages(snapshot)
        return json.loads(json.dumps(snapshot, ensure_ascii=False))

    def _invoke(
        self,
        collected: ControllerResult,
        role_id: str,
        mode: str,
        session_id: str | None,
        trigger_kind: str,
        trigger_id: str,
    ) -> TurnEvidence:
        if len(collected.turns) >= self.max_turns:
            raise ControllerError("turn limit exceeded")
        self._validate_binding(role_id)
        self._check_deadline()
        attempt = self._create_attempt(role_id, trigger_kind, trigger_id)
        trigger_text = (
            self.START_FAILURE_HOST_TRIGGER
            if role_id == HOST_ROLE_ID
            and mode == "resume"
            and trigger_kind == "call_fault"
            else None
        )
        raw = self._run_bound(role_id, mode, session_id, trigger_text=trigger_text)
        self._check_deadline()
        events = _value(raw, "machine_events")
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes, bytearray)):
            raise ControllerError("runner machine_events must be a sequence")
        self._validate_runner_result(raw, events)
        query_request_id, query_facts = _query_evidence(events)
        snapshot = self._snapshot()
        if query_facts.get("current_role_id") != role_id:
            raise ControllerError("query_thread current role does not match invocation")
        if query_facts.get("scenario_digest") != snapshot.get("scenario_digest"):
            raise ControllerError("query_thread scenario digest does not match run state")
        returned_session = _value(raw, "session_id")
        if not isinstance(returned_session, str) or not returned_session:
            raise ControllerError("runner returned no session")
        prior = collected.sessions.get(role_id)
        if mode == "start" and (session_id is not None or prior is not None):
            raise ControllerError("invalid start session")
        if mode == "resume" and (prior is None or session_id != prior):
            raise ControllerError("invalid resume session")
        if prior is not None and returned_session != prior:
            raise ControllerError("runner session drift")
        if any(
            other_role != role_id and other_session == returned_session
            for other_role, other_session in collected.sessions.items()
        ):
            raise ControllerError("role sessions must be distinct")
        final_result = _value(raw, "final_result")
        if not isinstance(final_result, str) or not final_result.strip():
            raise ControllerError("runner final_result must be nonempty")
        completed = self.state.record_agent_turn_completed(
            attempt["execution_attempt_id"]
        )
        completed_attempt = (
            completed.get("execution_attempt")
            if isinstance(completed, Mapping)
            else None
        )
        if (
            not isinstance(completed_attempt, Mapping)
            or completed_attempt.get("execution_attempt_id")
            != attempt["execution_attempt_id"]
            or completed_attempt.get("outcome") != "completed"
        ):
            raise ControllerError("execution attempt did not reach completed")
        collected.sessions[role_id] = returned_session
        turn = TurnEvidence(
            role_id=role_id,
            mode=mode,
            session_id=returned_session,
            query_request_id=query_request_id,
            query_facts=query_facts,
            machine_events=events,
            final_result=final_result,
            process_exit=_value(raw, "process_exit"),
            usage=_value(raw, "usage"),
        )
        collected.turns.append(turn)
        return turn

    @staticmethod
    def _validate_runner_result(raw: Any, events: Sequence[Mapping[str, Any]]) -> None:
        if _value(raw, "failures", ()):
            raise ControllerError("runner result contains failures")
        if _value(raw, "timed_out", False):
            raise ControllerError("runner timed out")
        if _value(raw, "unexpected_tool_calls", ()):
            raise ControllerError("runner result contains unexpected tool calls")
        process_exit = _value(raw, "process_exit")
        if not isinstance(process_exit, Mapping) or process_exit.get("returncode") != 0:
            raise ControllerError("runner process exit was nonzero or invalid")
        if process_exit.get("timed_out") is True:
            raise ControllerError("runner timed out")
        if not _terminal_completed(events):
            raise ControllerError("runner result has no terminal completion")

    def _run_bound(
        self,
        role_id: str,
        mode: str,
        session_id: str | None,
        *,
        trigger_text: str | None = None,
    ) -> Any:
        if self._current_role is not None:
            raise ControllerError("another role is already active")
        self._current_role = role_id
        try:
            return self._run_raw(
                role_id, mode, session_id, trigger_text=trigger_text
            )
        finally:
            self._current_role = None

    def _run_raw(
        self,
        role_id: str,
        mode: str,
        session_id: str | None,
        *,
        trigger_text: str | None = None,
    ) -> Any:
        if self._current_role != role_id:
            raise ControllerError("current role does not match runner invocation")
        trigger = trigger_text or self.NEUTRAL_TRIGGER
        if trigger_text is None and mode == "start":
            trigger = (
                self.HOST_START_TRIGGER
                if role_id == HOST_ROLE_ID
                else self.INVESTIGATOR_START_TRIGGER
            )
        remaining = (
            self.timeout_seconds
            if self._deadline_at is None
            else self._deadline_at - self.clock()
        )
        if remaining <= 0:
            raise ControllerError("probe deadline exceeded")
        return self.runners[role_id].run(
            role_id=role_id,
            mode=mode,
            session_id=session_id,
            trigger_text=trigger,
            workspace=Path(self.workspaces[role_id]),
            mcp_command=list(self.mcp_commands[role_id]),
            timeout_seconds=min(self.timeout_seconds, remaining),
            evidence_dir=Path(self.evidence_dirs[role_id]),
        )

    def _validate_binding(self, role_id: str) -> None:
        if role_id not in ROLE_PRODUCTS:
            raise ControllerError("unknown current role")
        runner = self.runners.get(role_id)
        if runner is None or getattr(runner, "product", None) != ROLE_PRODUCTS[role_id]:
            raise ControllerError("runner product does not match current role")
        command = self.mcp_commands.get(role_id)
        if not isinstance(command, Sequence) or isinstance(command, (str, bytes)):
            raise ControllerError("MCP caller role binding is missing")
        indexes = [index for index, item in enumerate(command) if item == "--caller-role"]
        if (
            len(indexes) != 1
            or indexes[0] + 1 >= len(command)
            or command[indexes[0] + 1] != role_id
        ):
            raise ControllerError("MCP caller role does not match current role")

    def _create_attempt(
        self, role_id: str, trigger_kind: str, trigger_id: str
    ) -> Mapping[str, Any]:
        response = self.state.create_execution_attempt(role_id, trigger_kind, trigger_id)
        attempt = response.get("execution_attempt", response)
        if not isinstance(attempt, Mapping) or not isinstance(
            attempt.get("execution_attempt_id"), str
        ):
            raise ControllerError("execution attempt was not recorded")
        return attempt

    @staticmethod
    def _same_path(actual: Any, expected: Path) -> bool:
        if not isinstance(actual, (str, bytes, os.PathLike)):
            return False
        return os.path.abspath(os.fspath(actual)) == os.path.abspath(os.fspath(expected))

    @staticmethod
    def _message_ids(thread: Mapping[str, Any]) -> set[str]:
        return {
            item["message_id"]
            for item in thread.get("messages", [])
            if isinstance(item, Mapping) and isinstance(item.get("message_id"), str)
        }

    def _new_messages(
        self, thread: Mapping[str, Any], seen_ids: set[str]
    ) -> list[Mapping[str, Any]]:
        self._assert_no_duplicate_messages(thread)
        return [
            item
            for item in thread.get("messages", [])
            if isinstance(item, Mapping) and item.get("message_id") not in seen_ids
        ]

    def _one_new_message(
        self, thread: Mapping[str, Any], seen_ids: set[str], label: str
    ) -> Mapping[str, Any]:
        messages = self._new_messages(thread, seen_ids)
        if len(messages) != 1:
            raise ControllerError(
                f"expected exactly one new {label}; observed {len(messages)}"
            )
        return messages[0]

    @staticmethod
    def _assert_no_duplicate_messages(thread: Mapping[str, Any]) -> None:
        ids = [
            item.get("message_id")
            for item in thread.get("messages", [])
            if isinstance(item, Mapping)
        ]
        if len(ids) != len(set(ids)):
            raise ControllerError("duplicate message delivery")

    @staticmethod
    def _new_delegation(
        before: Mapping[str, Any], after: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        delegation = after.get("delegation")
        if not isinstance(delegation, Mapping) or delegation == before.get("delegation"):
            raise ControllerError("host produced no new delegation")
        return delegation

    @staticmethod
    def _validate_delegation(delegation: Mapping[str, Any]) -> None:
        if (
            delegation.get("publisher_role_id") != HOST_ROLE_ID
            or delegation.get("target_role_id") != INVESTIGATOR_ROLE_ID
            or not isinstance(delegation.get("task"), str)
            or not delegation["task"]
        ):
            raise ControllerError("delegation route is invalid")

    @staticmethod
    def _validate_route(
        message: Mapping[str, Any], sender_role_id: str, target_role_id: str
    ) -> None:
        if (
            message.get("sender_role_id") != sender_role_id
            or message.get("target_role_id") != target_role_id
            or not isinstance(message.get("body"), str)
            or not message["body"]
        ):
            raise ControllerError("message route is invalid")

    @staticmethod
    def _correlate(turn: TurnEvidence, fact: Mapping[str, Any]) -> None:
        request_id = fact.get("request_id")
        if not isinstance(request_id, str) or request_id not in _request_ids(
            turn.machine_events
        ):
            raise ControllerError("Harness request_id is uncorrelated")

    def _delegation_delivery(
        self, delegation: Mapping[str, Any], receiver: TurnEvidence
    ) -> DeliveryEvidence:
        current = self._snapshot().get("delegation")
        if not isinstance(current, Mapping) or current.get("delegation_id") != delegation.get(
            "delegation_id"
        ):
            raise ControllerError("delegation was not delivered")
        return self._delivery(
            "delegation",
            delegation["delegation_id"],
            delegation["publisher_role_id"],
            delegation["target_role_id"],
            delegation["task"],
            current.get("task"),
            receiver,
        )

    def _message_delivery(
        self, message: Mapping[str, Any], receiver: TurnEvidence
    ) -> DeliveryEvidence:
        matches = [
            item
            for item in self._snapshot().get("messages", [])
            if isinstance(item, Mapping) and item.get("message_id") == message.get("message_id")
        ]
        if len(matches) != 1:
            raise ControllerError("message was not delivered exactly once")
        return self._delivery(
            "message",
            message["message_id"],
            message["sender_role_id"],
            message["target_role_id"],
            message["body"],
            matches[0].get("body"),
            receiver,
        )

    @staticmethod
    def _delivery(
        fact_kind: str,
        fact_id: str,
        sender_role_id: str,
        target_role_id: str,
        sent_payload: str,
        delivered_payload: Any,
        receiver: TurnEvidence,
    ) -> DeliveryEvidence:
        if receiver.role_id != target_role_id:
            raise ControllerError("fact was queried by the wrong target role")
        if fact_kind == "delegation":
            if receiver.query_facts.get("delegation_id") != fact_id:
                raise ControllerError("receiver query did not include the delegation")
        elif fact_id not in receiver.query_facts.get("message_ids", []):
            raise ControllerError("receiver query did not include the message")
        sent = canonical_digest(sent_payload)
        delivered = canonical_digest(delivered_payload)
        if sent != delivered:
            raise ControllerError("payload digest changed")
        return DeliveryEvidence(
            fact_kind=fact_kind,
            fact_id=fact_id,
            sender_role_id=sender_role_id,
            target_role_id=target_role_id,
            payload=sent_payload,
            send_digest=sent,
            payload_digest=delivered,
            receiver_query_request_id=receiver.query_request_id,
        )
