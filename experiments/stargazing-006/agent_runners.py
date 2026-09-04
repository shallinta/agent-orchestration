#!/usr/bin/env python3
"""Disposable Codex and Claude CLI adapters for Stargazing 6.

The adapters deliberately expose a small common return shape.  They do not
interpret Agent prose, retry a call, or turn CLI success into Harness success.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import uuid
from pathlib import Path
from typing import Any, NamedTuple


SERVER_NAME = "sg6"
HARNESS_TOOLS = ("query_thread", "publish_delegation", "send_message")
MAX_TIMEOUT_SECONDS = 300


class AgentRunResult(NamedTuple):
    session_id: str | None
    machine_events: list[dict[str, Any]]
    final_result: str | None
    process_exit: dict[str, Any]
    usage: list[dict[str, Any]]
    failures: list[dict[str, Any]]
    timed_out: bool
    terminal_completed: bool
    nonzero_exit: bool
    unexpected_tool_calls: list[dict[str, Any]]
    evidence_path: str | None = None


class UnexpectedToolCallError(RuntimeError):
    """Stop signal carrying the parsed run that crossed the tool boundary."""

    def __init__(self, result: AgentRunResult):
        super().__init__("unexpected non-MCP tool call; stop the probe")
        self.result = result


def _new_result(*, exit_code: int | None, timed_out: bool) -> dict[str, Any]:
    return {
        "session_id": None,
        "machine_events": [],
        "final_result": None,
        "process_exit": {"returncode": exit_code, "timed_out": timed_out},
        "usage": [],
        "failures": [],
        "timed_out": timed_out,
        "terminal_completed": False,
        "nonzero_exit": exit_code not in (None, 0),
        "unexpected_tool_calls": [],
        "evidence_path": None,
    }


def _finish(parsed: dict[str, Any]) -> AgentRunResult:
    return AgentRunResult(**parsed)


def _set_session(parsed: dict[str, Any], candidate: Any) -> None:
    if not isinstance(candidate, str) or not candidate:
        return
    current = parsed["session_id"]
    if current is None:
        parsed["session_id"] = candidate
    elif current != candidate and not any(
        failure.get("kind") == "session_drift" for failure in parsed["failures"]
    ):
        parsed["failures"].append({"kind": "session_drift"})


def _events(text: str, failures: list[dict[str, Any]]):
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            failures.append({"kind": "invalid_jsonl", "line": line_number})
            continue
        if not isinstance(event, dict):
            failures.append({"kind": "invalid_event", "line": line_number})
            continue
        yield event


def _structured_codex_result(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result")
    if not isinstance(result, dict):
        return {}
    structured = result.get("structured_content", result.get("structuredContent"))
    return structured if isinstance(structured, dict) else {}


def _string_ids(items: Any, field: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return [
        item[field]
        for item in items
        if isinstance(item, dict) and isinstance(item.get(field), str)
    ]


def _structural_payload(result: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "status": result.get("status"),
        "request_id": result.get("request_id"),
    }
    thread = result.get("thread")
    if isinstance(thread, dict):
        summary.update(
            {
                "scenario_digest": thread.get("scenario_digest"),
                "delegation_id": (
                    thread["delegation"].get("delegation_id")
                    if isinstance(thread.get("delegation"), dict)
                    else None
                ),
                "message_ids": _string_ids(thread.get("messages"), "message_id"),
                "execution_attempt_ids": _string_ids(
                    thread.get("execution_attempts"), "execution_attempt_id"
                ),
                "call_fault_ids": _string_ids(thread.get("call_faults"), "fault_id"),
                "payload_digests": _string_ids(thread.get("events"), "payload_sha256"),
            }
        )
        if isinstance(thread.get("current_role_id"), str):
            summary["current_role_id"] = thread["current_role_id"]
    for entity, field in (
        ("delegation", "delegation_id"),
        ("message", "message_id"),
        ("call_fault", "fault_id"),
        ("execution_attempt", "execution_attempt_id"),
    ):
        value = result.get(entity)
        if isinstance(value, dict) and isinstance(value.get(field), str):
            summary[field] = value[field]
    return summary


def parse_codex_jsonl(
    text: str,
    *,
    exit_code: int | None,
    timed_out: bool = False,
) -> AgentRunResult:
    parsed = _new_result(exit_code=exit_code, timed_out=timed_out)
    unsafe_item_types = {
        "command_execution",
        "file_change",
        "web_search",
        "image_view",
        "dynamic_tool_call",
    }

    for event in _events(text, parsed["failures"]):
        event_type = event.get("type")
        if event_type == "thread.started":
            _set_session(parsed, event.get("thread_id"))
            parsed["machine_events"].append({"kind": "session_started"})
            continue

        item = event.get("item")
        if isinstance(item, dict):
            item_type = item.get("type")
            if item_type == "mcp_tool_call":
                if item.get("server") != SERVER_NAME or item.get("tool") not in HARNESS_TOOLS:
                    parsed["unexpected_tool_calls"].append(
                        {
                            "event": event_type,
                            "call_id": item.get("id"),
                            "tool": "unexpected_mcp",
                        }
                    )
                else:
                    structured = _structured_codex_result(item)
                    parsed["machine_events"].append(
                        {
                            "kind": "mcp_tool_call",
                            "event": event_type,
                            "call_id": item.get("id"),
                            "server": item.get("server"),
                            "tool": item.get("tool"),
                            "status": item.get("status"),
                            "request_id": structured.get("request_id"),
                            "structured_payload": _structural_payload(structured),
                        }
                    )
            elif item_type == "agent_message" and event_type == "item.completed":
                if isinstance(item.get("text"), str):
                    parsed["final_result"] = item["text"]
            elif item_type == "error" and event_type == "item.completed":
                parsed["machine_events"].append(
                    {
                        "kind": "diagnostic",
                        "severity": "warning",
                        "source": "item.error",
                    }
                )
            elif item_type in unsafe_item_types:
                unsafe = {
                    "event": event_type,
                    "call_id": item.get("id"),
                    "tool": item_type,
                }
                if unsafe not in parsed["unexpected_tool_calls"]:
                    parsed["unexpected_tool_calls"].append(unsafe)
            elif item_type not in {"agent_message", "reasoning"}:
                parsed["unexpected_tool_calls"].append(
                    {
                        "event": event_type,
                        "call_id": item.get("id"),
                        "tool": "unexpected_builtin",
                    }
                )

        if event_type == "turn.completed":
            parsed["terminal_completed"] = True
            if isinstance(event.get("usage"), dict):
                parsed["usage"].append(dict(event["usage"]))
            parsed["machine_events"].append({"kind": "terminal_result", "status": "completed"})
        elif event_type in {"error", "turn.failed"}:
            parsed["failures"].append({"kind": event_type})
            parsed["machine_events"].append({"kind": event_type})

    return _finish(parsed)


def _parse_tool_result_content(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        try:
            value = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                value = _parse_tool_result_content(block["text"])
                if value:
                    return value
    return {}


def parse_claude_stream_json(
    text: str,
    *,
    exit_code: int | None,
    timed_out: bool = False,
) -> AgentRunResult:
    parsed = _new_result(exit_code=exit_code, timed_out=timed_out)
    expected_tools = {"mcp__sg6__" + tool for tool in HARNESS_TOOLS}
    tool_names_by_call_id: dict[str, str] = {}
    init_seen = False

    for event in _events(text, parsed["failures"]):
        event_type = event.get("type")
        _set_session(parsed, event.get("session_id"))

        if event_type == "system" and event.get("subtype") == "init":
            init_seen = True
            servers = event.get("mcp_servers")
            connected = (
                isinstance(servers, list)
                and len(servers) == 1
                and isinstance(servers[0], dict)
                and servers[0].get("name") == SERVER_NAME
                and servers[0].get("status") == "connected"
            )
            actual_tools = event.get("tools")
            exact_tools = (
                isinstance(actual_tools, list)
                and len(actual_tools) == len(expected_tools)
                and set(actual_tools) == expected_tools
            )
            parsed["machine_events"].append(
                {
                    "kind": "session_started",
                    "mcp_server_connected": connected,
                    "tool_surface_valid": exact_tools,
                }
            )
            if not connected or not exact_tools:
                parsed["failures"].append({"kind": "invalid_tool_surface"})
                parsed["unexpected_tool_calls"].append(
                    {"event": "system.init", "call_id": None, "tool": "tool_surface"}
                )

        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                name = block.get("name")
                if block_type == "tool_use":
                    if name in expected_tools:
                        if isinstance(block.get("id"), str):
                            tool_names_by_call_id[block["id"]] = name.removeprefix(
                                "mcp__sg6__"
                            )
                        parsed["machine_events"].append(
                            {
                                "kind": "mcp_tool_call",
                                "call_id": block.get("id"),
                                "tool": name.removeprefix("mcp__sg6__"),
                            }
                        )
                    else:
                        parsed["unexpected_tool_calls"].append(
                            {"event": event_type, "call_id": block.get("id"), "tool": name}
                        )
                elif block_type == "server_tool_use":
                    parsed["unexpected_tool_calls"].append(
                        {"event": event_type, "call_id": block.get("id"), "tool": name}
                    )
                elif block_type == "tool_result":
                    result = _parse_tool_result_content(block.get("content"))
                    parsed["machine_events"].append(
                        {
                            "kind": "mcp_tool_result",
                            "call_id": block.get("tool_use_id"),
                            "tool": tool_names_by_call_id.get(block.get("tool_use_id")),
                            "request_id": result.get("request_id"),
                            "status": result.get("status"),
                            "is_error": bool(block.get("is_error", False)),
                            "structured_payload": _structural_payload(result),
                        }
                    )

        if event_type == "result":
            if isinstance(event.get("result"), str):
                parsed["final_result"] = event["result"]
            if isinstance(event.get("usage"), dict):
                usage = dict(event["usage"])
                if "total_cost_usd" in event:
                    usage["total_cost_usd"] = event["total_cost_usd"]
                parsed["usage"].append(usage)
            terminal_reason = event.get("terminal_reason")
            parsed["terminal_completed"] = (
                event.get("is_error") is False and terminal_reason == "completed"
            )
            parsed["machine_events"].append(
                {"kind": "terminal_result", "terminal_reason": terminal_reason}
            )
            if event.get("is_error") is True or terminal_reason not in (None, "completed"):
                parsed["failures"].append(
                    {"kind": "terminal_result", "terminal_reason": terminal_reason}
                )

    if not init_seen:
        parsed["failures"].append({"kind": "invalid_tool_surface"})
        parsed["unexpected_tool_calls"].append(
            {"event": "missing_init", "call_id": None, "tool": "tool_surface"}
        )

    return _finish(parsed)


def _validate_command_inputs(
    *,
    mode: str,
    session_id: str | None,
    trigger_text: str,
    workspace: str | os.PathLike[str],
    mcp_command: list[str],
) -> None:
    if mode not in {"start", "resume"}:
        raise ValueError("mode must be start or resume")
    if mode == "resume" and not session_id:
        raise ValueError("resume requires a session id")
    if mode == "start" and session_id is not None:
        raise ValueError("start must not receive a session id")
    if not isinstance(trigger_text, str) or not trigger_text:
        raise ValueError("trigger_text must be non-empty")
    if not isinstance(mcp_command, list) or not mcp_command or not all(
        isinstance(part, str) and part for part in mcp_command
    ):
        raise ValueError("mcp_command must be a non-empty string array")
    if not os.fspath(workspace):
        raise ValueError("workspace must be non-empty")


def _codex_mcp_options(mcp_command: list[str]) -> list[str]:
    enabled_tools = json.dumps(list(HARNESS_TOOLS), separators=(",", ":"))
    return [
        "-c",
        "mcp_servers.sg6.command={}".format(json.dumps(mcp_command[0])),
        "-c",
        "mcp_servers.sg6.args={}".format(json.dumps(mcp_command[1:], separators=(",", ":"))),
        "-c",
        "mcp_servers.sg6.required=true",
        "-c",
        "mcp_servers.sg6.startup_timeout_sec=10",
        "-c",
        "mcp_servers.sg6.tool_timeout_sec=20",
        "-c",
        "mcp_servers.sg6.enabled_tools={}".format(enabled_tools),
        "-c",
        'mcp_servers.sg6.default_tools_approval_mode="approve"',
    ]


def build_codex_command(
    *,
    executable: str,
    mode: str,
    session_id: str | None,
    trigger_text: str,
    workspace: str | os.PathLike[str],
    mcp_command: list[str],
) -> list[str]:
    _validate_command_inputs(
        mode=mode,
        session_id=session_id,
        trigger_text=trigger_text,
        workspace=workspace,
        mcp_command=mcp_command,
    )
    command = [
        executable,
        "exec",
        "--disable",
        "shell_tool",
        "--ignore-user-config",
        "--ignore-rules",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--json",
        "-C",
        os.fspath(workspace),
        *_codex_mcp_options(mcp_command),
    ]
    if mode == "resume":
        command.extend(("resume", session_id))
    command.append(trigger_text)
    return command


def build_claude_command(
    *,
    executable: str,
    mode: str,
    session_id: str | None,
    trigger_text: str,
    workspace: str | os.PathLike[str],
    mcp_command: list[str],
) -> list[str]:
    _validate_command_inputs(
        mode=mode,
        session_id=session_id,
        trigger_text=trigger_text,
        workspace=workspace,
        mcp_command=mcp_command,
    )
    mcp_config = json.dumps(
        {
            "mcpServers": {
                SERVER_NAME: {
                    "type": "stdio",
                    "command": mcp_command[0],
                    "args": mcp_command[1:],
                }
            }
        },
        separators=(",", ":"),
    )
    allowed_tools = ",".join("mcp__sg6__" + tool for tool in HARNESS_TOOLS)
    command = [
        executable,
        "-p",
        "--restricted",
        "--disable-slash-commands",
        "--strict-mcp-config",
        "--tools",
        "",
        "--allowedTools",
        allowed_tools,
        "--mcp-config",
        mcp_config,
        "--no-chrome",
        "--permission-mode",
        "dontAsk",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if mode == "resume":
        command.extend(("--resume", session_id))
    command.append(trigger_text)
    return command


def _stop_process_group(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except BaseException:
        pass
    try:
        return process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except BaseException:
            pass
        return process.communicate()
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except BaseException:
            pass
        try:
            process.wait(timeout=2)
        except BaseException:
            pass
        raise


def _abort_process_group(process: subprocess.Popen[str]) -> None:
    try:
        _stop_process_group(process)
    except BaseException:
        # Cleanup failures must not replace the exception that interrupted execution.
        pass


def _execute(command: list[str], *, workspace: Path, timeout_seconds: float):
    process = subprocess.Popen(
        command,
        cwd=workspace,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        shell=False,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        stdout, stderr = _stop_process_group(process)
    except BaseException:
        _abort_process_group(process)
        raise
    return stdout, stderr, process.returncode, timed_out


def _validate_run_paths(workspace: str | os.PathLike[str], evidence_dir: str | os.PathLike[str]):
    workspace_path = Path(workspace)
    if not workspace_path.is_dir() or not (workspace_path / ".git").exists():
        raise ValueError("workspace must be an existing Git workspace")
    evidence_path = Path(evidence_dir)
    evidence_path.mkdir(parents=True, exist_ok=True)
    return workspace_path, evidence_path


def _write_evidence(
    *,
    product: str,
    role_id: str,
    mode: str,
    timeout_seconds: float,
    stderr: str,
    result: AgentRunResult,
    evidence_dir: Path,
) -> str:
    command_shape = {
        "codex": [
            "<executable>",
            "exec",
            "<ignore-options>",
            "--sandbox",
            "read-only",
            "--json",
            "-C",
            "<workspace>",
            "<required-role-mcp-config>",
            "<session-if-resume>",
            "<trigger>",
        ],
        "claude": [
            "<executable>",
            "-p",
            "--restricted",
            "--strict-mcp-config",
            "--tools",
            "<empty>",
            "--allowedTools",
            "<role-mcp-tools>",
            "--mcp-config",
            "<mcp-config>",
            "--permission-mode",
            "dontAsk",
            "<session-if-resume>",
            "<trigger>",
        ],
    }[product]
    fixed_tool_kinds = {
        "command_execution",
        "file_change",
        "web_search",
        "image_view",
        "dynamic_tool_call",
        "unexpected_mcp",
        "tool_surface",
        "unexpected_builtin",
        "Bash",
        "PowerShell",
        "REPL",
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "NotebookEdit",
        "WebFetch",
        "WebSearch",
        "web_fetch",
    }
    evidence = {
        "product": product,
        "role_id": role_id if role_id in {"host-codex", "investigator-claude"} else "invalid",
        "mode": mode,
        "command": command_shape,
        "timeout_seconds": timeout_seconds,
        "process_exit": result.process_exit,
        "session_present": result.session_id is not None,
        "machine_event_kinds": [event.get("kind") for event in result.machine_events],
        "failure_kinds": [failure.get("kind") for failure in result.failures],
        "unexpected_tool_kinds": [
            call.get("tool") if call.get("tool") in fixed_tool_kinds else "unexpected_tool"
            for call in result.unexpected_tool_calls
        ],
        "usage_observation_count": len(result.usage),
        "stderr_present": bool(stderr),
    }
    path = evidence_dir / ("runner-" + uuid.uuid4().hex + ".json")
    path.write_text(json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n")
    return str(path)


class _Runner:
    product: str

    def __init__(self, executable: str):
        self.executable = executable

    def build_command(self, **kwargs) -> list[str]:
        builder = build_codex_command if self.product == "codex" else build_claude_command
        return builder(executable=self.executable, **kwargs)

    def parse(self, stdout: str, *, exit_code: int | None, timed_out: bool) -> AgentRunResult:
        parser = parse_codex_jsonl if self.product == "codex" else parse_claude_stream_json
        return parser(stdout, exit_code=exit_code, timed_out=timed_out)

    def run(
        self,
        *,
        role_id: str,
        mode: str,
        session_id: str | None,
        trigger_text: str,
        workspace: str | os.PathLike[str],
        mcp_command: list[str],
        timeout_seconds: float = MAX_TIMEOUT_SECONDS,
        evidence_dir: str | os.PathLike[str],
    ) -> AgentRunResult:
        if not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS:
            raise ValueError("timeout must be positive and at most five minutes")
        workspace_path, evidence_path = _validate_run_paths(workspace, evidence_dir)
        command = self.build_command(
            mode=mode,
            session_id=session_id,
            trigger_text=trigger_text,
            workspace=workspace_path,
            mcp_command=mcp_command,
        )
        stdout, stderr, exit_code, timed_out = _execute(
            command,
            workspace=workspace_path,
            timeout_seconds=timeout_seconds,
        )
        result = self.parse(stdout, exit_code=exit_code, timed_out=timed_out)
        written_path = _write_evidence(
            product=self.product,
            role_id=role_id,
            mode=mode,
            timeout_seconds=timeout_seconds,
            stderr=stderr,
            result=result,
            evidence_dir=evidence_path,
        )
        result = result._replace(evidence_path=written_path)
        if result.unexpected_tool_calls:
            raise UnexpectedToolCallError(result)
        return result


class CodexRunner(_Runner):
    product = "codex"

    def __init__(self, executable: str = "codex"):
        super().__init__(executable)


class ClaudeRunner(_Runner):
    product = "claude"

    def __init__(self, executable: str = "claude"):
        super().__init__(executable)
