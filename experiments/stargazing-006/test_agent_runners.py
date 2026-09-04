import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "agent_runners.py"


CODEX_SUCCESS = "\n".join(
    json.dumps(event)
    for event in (
        {"type": "thread.started", "thread_id": "codex-session-1"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "call-1",
                "type": "mcp_tool_call",
                "server": "sg6",
                "tool": "query_thread",
                "arguments": {},
                "status": "completed",
                "result": {
                    "structured_content": {
                        "status": "ok",
                        "request_id": "req-codex-1",
                        "thread": {
                            "current_role_id": "host-codex",
                            "scenario_digest": "scenario-digest-codex",
                            "delegation": {"delegation_id": "delegation-1"},
                            "messages": [{"message_id": "message-1"}],
                            "execution_attempts": [
                                {"execution_attempt_id": "attempt-1"}
                            ],
                            "call_faults": [{"fault_id": "fault-1"}],
                            "events": [{"payload_sha256": "payload-digest-1"}],
                        },
                    }
                },
            },
        },
        {
            "type": "item.completed",
            "item": {"id": "message-1", "type": "agent_message", "text": "host final"},
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 12, "cached_input_tokens": 3, "output_tokens": 4},
        },
    )
) + "\n"


CODEX_FAILURE_AND_UNEXPECTED_TOOL = "\n".join(
    json.dumps(event)
    for event in (
        {"type": "thread.started", "thread_id": "codex-session-2"},
        {
            "type": "item.started",
            "item": {
                "id": "unsafe-1",
                "type": "command_execution",
                "command": "synthetic command",
                "status": "in_progress",
            },
        },
        {"type": "error", "message": "required MCP server failed"},
        {"type": "turn.failed", "error": {"message": "turn did not start"}},
    )
) + "\n"


CLAUDE_SUCCESS = "\n".join(
    json.dumps(event)
    for event in (
        {
            "type": "system",
            "subtype": "init",
            "session_id": "claude-session-1",
            "tools": [
                "mcp__sg6__query_thread",
                "mcp__sg6__publish_delegation",
                "mcp__sg6__send_message",
            ],
            "mcp_servers": [{"name": "sg6", "status": "connected"}],
            "permissionMode": "dontAsk",
        },
        {
            "type": "assistant",
            "session_id": "claude-session-1",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu-1",
                        "name": "mcp__sg6__query_thread",
                        "input": {},
                    }
                ],
            },
        },
        {
            "type": "user",
            "session_id": "claude-session-1",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu-1",
                        "content": json.dumps(
                            {
                                "status": "ok",
                                "request_id": "req-claude-1",
                                "thread": {
                                    "current_role_id": "investigator-claude",
                                    "scenario_digest": "scenario-digest-claude",
                                    "delegation": {"delegation_id": "delegation-1"},
                                    "messages": [{"message_id": "message-1"}],
                                    "execution_attempts": [
                                        {"execution_attempt_id": "attempt-1"}
                                    ],
                                    "call_faults": [{"fault_id": "fault-1"}],
                                    "events": [
                                        {"payload_sha256": "payload-digest-1"}
                                    ],
                                },
                            },
                            separators=(",", ":"),
                        ),
                    }
                ],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "terminal_reason": "completed",
            "session_id": "claude-session-1",
            "result": "investigator final",
            "usage": {"input_tokens": 20, "output_tokens": 7},
            "total_cost_usd": 0.0,
        },
    )
) + "\n"


CLAUDE_FAILURE_AND_UNEXPECTED_TOOL = "\n".join(
    json.dumps(event)
    for event in (
        {
            "type": "system",
            "subtype": "init",
            "session_id": "claude-session-2",
            "tools": [],
            "mcp_servers": [{"name": "sg6", "status": "failed"}],
            "permissionMode": "dontAsk",
        },
        {
            "type": "assistant",
            "session_id": "claude-session-2",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "toolu-unsafe", "name": "Write", "input": {}},
                    {"type": "server_tool_use", "id": "web-unsafe", "name": "web_search"},
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "terminal_reason": "api_error",
            "session_id": "claude-session-2",
            "result": "MCP unavailable",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    )
) + "\n"


def load_module():
    if not MODULE_PATH.exists():
        raise AssertionError("agent_runners.py is not implemented")
    spec = importlib.util.spec_from_file_location("sg6_agent_runners", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fake_executable(path, stdout, exit_code=0, sleep_seconds=0):
    source = "\n".join(
        (
            "#!/usr/bin/env python3",
            "import sys, time",
            "time.sleep({!r})".format(sleep_seconds),
            "sys.stdout.write({!r})".format(stdout),
            "raise SystemExit({!r})".format(exit_code),
            "",
        )
    )
    path.write_text(source, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ParserTest(unittest.TestCase):
    def test_codex_parser_preserves_session_mcp_result_exit_and_usage(self):
        runners = load_module()
        result = runners.parse_codex_jsonl(CODEX_SUCCESS, exit_code=0)

        self.assertEqual(result.session_id, "codex-session-1")
        self.assertEqual(result.final_result, "host final")
        self.assertEqual(result.process_exit, {"returncode": 0, "timed_out": False})
        self.assertEqual(result.usage[-1]["input_tokens"], 12)
        self.assertTrue(result.terminal_completed)
        self.assertFalse(result.nonzero_exit)
        self.assertEqual(result.failures, [])
        self.assertEqual(result.unexpected_tool_calls, [])
        self.assertEqual(
            [event for event in result.machine_events if event["kind"] == "mcp_tool_call"],
            [
                {
                    "kind": "mcp_tool_call",
                    "event": "item.completed",
                    "call_id": "call-1",
                    "server": "sg6",
                    "tool": "query_thread",
                    "status": "completed",
                    "request_id": "req-codex-1",
                    "structured_payload": {
                        "status": "ok",
                        "request_id": "req-codex-1",
                        "current_role_id": "host-codex",
                        "scenario_digest": "scenario-digest-codex",
                        "delegation_id": "delegation-1",
                        "message_ids": ["message-1"],
                        "execution_attempt_ids": ["attempt-1"],
                        "call_fault_ids": ["fault-1"],
                        "payload_digests": ["payload-digest-1"],
                    },
                }
            ],
        )

    def test_codex_parser_keeps_failure_timeout_exit_and_unexpected_tools_distinct(self):
        runners = load_module()
        result = runners.parse_codex_jsonl(
            CODEX_FAILURE_AND_UNEXPECTED_TOOL,
            exit_code=-15,
            timed_out=True,
        )

        self.assertEqual(result.process_exit, {"returncode": -15, "timed_out": True})
        self.assertFalse(result.terminal_completed)
        self.assertTrue(result.nonzero_exit)
        self.assertEqual([failure["kind"] for failure in result.failures], ["error", "turn.failed"])
        self.assertEqual(
            result.unexpected_tool_calls,
            [{"event": "item.started", "call_id": "unsafe-1", "tool": "command_execution"}],
        )

    def test_claude_parser_preserves_session_mcp_result_exit_and_usage(self):
        runners = load_module()
        result = runners.parse_claude_stream_json(CLAUDE_SUCCESS, exit_code=0)

        self.assertEqual(result.session_id, "claude-session-1")
        self.assertEqual(result.final_result, "investigator final")
        self.assertEqual(result.process_exit, {"returncode": 0, "timed_out": False})
        self.assertEqual(result.usage[-1]["output_tokens"], 7)
        self.assertTrue(result.terminal_completed)
        self.assertFalse(result.nonzero_exit)
        self.assertEqual(result.failures, [])
        self.assertEqual(result.unexpected_tool_calls, [])
        calls = [event for event in result.machine_events if event["kind"] == "mcp_tool_call"]
        results = [event for event in result.machine_events if event["kind"] == "mcp_tool_result"]
        self.assertEqual(calls[0]["tool"], "query_thread")
        self.assertEqual(results[0]["request_id"], "req-claude-1")
        self.assertEqual(results[0]["call_id"], "toolu-1")
        self.assertEqual(
            results[0]["structured_payload"],
            {
                "status": "ok",
                "request_id": "req-claude-1",
                "current_role_id": "investigator-claude",
                "scenario_digest": "scenario-digest-claude",
                "delegation_id": "delegation-1",
                "message_ids": ["message-1"],
                "execution_attempt_ids": ["attempt-1"],
                "call_fault_ids": ["fault-1"],
                "payload_digests": ["payload-digest-1"],
            },
        )

    def test_claude_parser_keeps_terminal_failure_and_unexpected_tools_distinct(self):
        runners = load_module()
        result = runners.parse_claude_stream_json(
            CLAUDE_FAILURE_AND_UNEXPECTED_TOOL,
            exit_code=1,
        )

        self.assertEqual(result.process_exit, {"returncode": 1, "timed_out": False})
        self.assertFalse(result.terminal_completed)
        self.assertTrue(result.nonzero_exit)
        self.assertEqual(result.failures[-1]["kind"], "terminal_result")
        self.assertEqual(result.failures[-1]["terminal_reason"], "api_error")
        self.assertEqual(
            {item["tool"] for item in result.unexpected_tool_calls},
            {"tool_surface", "Write", "web_search"},
        )

    def test_malformed_lines_are_machine_failures_not_agent_results(self):
        runners = load_module()
        codex = runners.parse_codex_jsonl('{"type":"thread.started"}\nnot-json\n', exit_code=2)
        claude = runners.parse_claude_stream_json("[]\n", exit_code=2)

        self.assertIsNone(codex.final_result)
        self.assertEqual(codex.failures[-1]["kind"], "invalid_jsonl")
        self.assertIn("invalid_event", [failure["kind"] for failure in claude.failures])
        self.assertIn("invalid_tool_surface", [failure["kind"] for failure in claude.failures])

    def test_codex_rejects_other_mcp_server_or_tool_as_unexpected(self):
        runners = load_module()
        cases = (
            ("other-server", "query_thread"),
            ("sg6", "other_tool"),
        )
        for server, tool in cases:
            with self.subTest(server=server, tool=tool):
                fixture = json.dumps(
                    {
                        "type": "item.started",
                        "item": {
                            "id": "unexpected-mcp",
                            "type": "mcp_tool_call",
                            "server": server,
                            "tool": tool,
                            "status": "in_progress",
                        },
                    }
                )
                result = runners.parse_codex_jsonl(fixture, exit_code=0)
                self.assertEqual(len(result.unexpected_tool_calls), 1)
                self.assertEqual(result.unexpected_tool_calls[0]["tool"], "unexpected_mcp")

    def test_codex_fails_closed_for_unknown_non_message_item_type(self):
        runners = load_module()
        fixture = json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "unknown-builtin",
                    "type": "future_builtin_tool",
                    "status": "in_progress",
                },
            }
        )

        result = runners.parse_codex_jsonl(fixture, exit_code=0)

        self.assertEqual(
            result.unexpected_tool_calls,
            [
                {
                    "event": "item.started",
                    "call_id": "unknown-builtin",
                    "tool": "unexpected_builtin",
                }
            ],
        )

    def test_codex_item_error_is_a_diagnostic_not_an_unexpected_tool(self):
        runners = load_module()
        fixture = "\n".join(
            json.dumps(event)
            for event in (
                {"type": "thread.started", "thread_id": "codex-session-diagnostic"},
                {
                    "type": "item.completed",
                    "item": {
                        "id": "diagnostic-1",
                        "type": "error",
                        "message": "arbitrary future informational diagnostic text",
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "query-1",
                        "type": "mcp_tool_call",
                        "server": "sg6",
                        "tool": "query_thread",
                        "status": "completed",
                        "result": {
                            "structured_content": {
                                "status": "ok",
                                "request_id": "req-diagnostic-query",
                                "thread": {
                                    "current_role_id": "host-codex",
                                    "scenario_digest": "scenario-digest",
                                    "delegation": None,
                                    "messages": [],
                                    "execution_attempts": [],
                                    "call_faults": [],
                                    "events": [],
                                },
                            }
                        },
                    },
                },
                {
                    "type": "item.completed",
                    "item": {
                        "id": "message-1",
                        "type": "agent_message",
                        "text": "host result",
                    },
                },
                {"type": "turn.completed", "usage": {"input_tokens": 1}},
            )
        )

        result = runners.parse_codex_jsonl(fixture, exit_code=0)

        self.assertEqual(result.unexpected_tool_calls, [])
        self.assertEqual(result.failures, [])
        self.assertTrue(result.terminal_completed)
        self.assertEqual(result.final_result, "host result")
        diagnostics = [
            event for event in result.machine_events if event.get("kind") == "diagnostic"
        ]
        self.assertEqual(
            diagnostics,
            [{"kind": "diagnostic", "severity": "warning", "source": "item.error"}],
        )
        self.assertNotIn("arbitrary future", json.dumps(result.machine_events))

    def test_codex_item_error_outside_item_completed_still_fails_closed(self):
        runners = load_module()
        for event_type in ("item.started", "future.event"):
            with self.subTest(event_type=event_type):
                fixture = json.dumps(
                    {
                        "type": event_type,
                        "item": {
                            "id": "error-outside-completed",
                            "type": "error",
                            "message": "arbitrary diagnostic text",
                        },
                    }
                )
                result = runners.parse_codex_jsonl(fixture, exit_code=0)
                self.assertEqual(
                    result.unexpected_tool_calls,
                    [
                        {
                            "event": event_type,
                            "call_id": "error-outside-completed",
                            "tool": "unexpected_builtin",
                        }
                    ],
                )
                self.assertFalse(
                    any(event.get("kind") == "diagnostic" for event in result.machine_events)
                )

    def test_claude_init_requires_connected_sg6_and_exact_three_tool_surface(self):
        runners = load_module()
        expected = ["mcp__sg6__" + tool for tool in runners.HARNESS_TOOLS]
        cases = (
            (expected + ["Read"], [{"name": "sg6", "status": "connected"}]),
            (expected + ["mcp__other__query"], [{"name": "sg6", "status": "connected"}]),
            (expected, [{"name": "sg6", "status": "failed"}]),
            (expected, []),
        )
        for tools, servers in cases:
            with self.subTest(tools=tools, servers=servers):
                fixture = json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "claude-init-boundary",
                        "tools": tools,
                        "mcp_servers": servers,
                    }
                )
                result = runners.parse_claude_stream_json(fixture, exit_code=0)
                self.assertFalse(result.terminal_completed)
                self.assertIn("tool_surface", [item["tool"] for item in result.unexpected_tool_calls])
                self.assertIn("invalid_tool_surface", [item["kind"] for item in result.failures])


class CommandConstructionTest(unittest.TestCase):
    def setUp(self):
        self.runners = load_module()
        self.workspace = "/tmp/SENSITIVE-workspace"
        self.mcp_command = [
            "/tmp/SENSITIVE-python",
            "-B",
            "/tmp/SENSITIVE-harness_mcp.py",
            "--caller-role",
            "host-codex",
        ]

    def test_codex_start_and_resume_keep_verified_restrictions_and_required_mcp(self):
        for mode, session_id in (("start", None), ("resume", "SENSITIVE-session")):
            with self.subTest(mode=mode):
                command = self.runners.build_codex_command(
                    executable="/tmp/codex",
                    mode=mode,
                    session_id=session_id,
                    trigger_text="SENSITIVE prompt",
                    workspace=self.workspace,
                    mcp_command=self.mcp_command,
                )
                self.assertIsInstance(command, list)
                self.assertEqual(command[:2], ["/tmp/codex", "exec"])
                self.assertEqual(command[2:4], ["--disable", "shell_tool"])
                self.assertEqual(command.count("--disable"), 1)
                self.assertEqual(command.count("shell_tool"), 1)
                self.assertIn("--ignore-user-config", command)
                self.assertIn("--ignore-rules", command)
                self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
                self.assertIn("--json", command)
                self.assertEqual(command[command.index("-C") + 1], self.workspace)
                rendered = "\n".join(command)
                self.assertIn("mcp_servers.sg6.required=true", rendered)
                self.assertIn("mcp_servers.sg6.enabled_tools", rendered)
                self.assertIn("query_thread", rendered)
                self.assertIn("publish_delegation", rendered)
                self.assertIn("send_message", rendered)
                self.assertNotIn("dangerously-bypass", rendered)
                self.assertNotIn("danger-full-access", rendered)
                self.assertNotIn("--skip-git-repo-check", command)
                self.assertNotIn("--ephemeral", command)
                self.assertEqual(command[-1], "SENSITIVE prompt")
                if mode == "resume":
                    self.assertEqual(command[-3:-1], ["resume", "SENSITIVE-session"])
                else:
                    self.assertNotIn("resume", command)

    def test_claude_start_and_resume_expose_only_explicit_mcp_tools(self):
        for mode, session_id in (("start", None), ("resume", "SENSITIVE-session")):
            with self.subTest(mode=mode):
                command = self.runners.build_claude_command(
                    executable="/tmp/claude",
                    mode=mode,
                    session_id=session_id,
                    trigger_text="SENSITIVE prompt",
                    workspace=self.workspace,
                    mcp_command=self.mcp_command,
                )
                rendered = "\n".join(command)
                self.assertEqual(command[0], "/tmp/claude")
                self.assertIn("-p", command)
                self.assertIn("--restricted", command)
                self.assertIn("--strict-mcp-config", command)
                self.assertIn("--disable-slash-commands", command)
                self.assertEqual(command[command.index("--tools") + 1], "")
                self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
                self.assertEqual(command[command.index("--output-format") + 1], "stream-json")
                allowed = command[command.index("--allowedTools") + 1]
                self.assertEqual(
                    set(allowed.split(",")),
                    {
                        "mcp__sg6__query_thread",
                        "mcp__sg6__publish_delegation",
                        "mcp__sg6__send_message",
                    },
                )
                mcp_config = json.loads(command[command.index("--mcp-config") + 1])
                self.assertEqual(mcp_config["mcpServers"]["sg6"]["command"], self.mcp_command[0])
                self.assertEqual(mcp_config["mcpServers"]["sg6"]["args"], self.mcp_command[1:])
                self.assertNotIn("--safe-mode", command)
                self.assertNotIn("bypassPermissions", rendered)
                self.assertEqual(command[-1], "SENSITIVE prompt")
                if mode == "resume":
                    self.assertEqual(command[-3:-1], ["--resume", "SENSITIVE-session"])

    def test_builders_reject_bad_mode_or_missing_and_extra_session(self):
        kwargs = {
            "executable": "codex",
            "trigger_text": "fixture",
            "workspace": self.workspace,
            "mcp_command": self.mcp_command,
        }
        with self.assertRaises(ValueError):
            self.runners.build_codex_command(mode="resume", session_id=None, **kwargs)
        with self.assertRaises(ValueError):
            self.runners.build_codex_command(mode="start", session_id="unexpected", **kwargs)
        with self.assertRaises(ValueError):
            self.runners.build_codex_command(mode="other", session_id=None, **kwargs)


class SubprocessBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.runners = load_module()

    def run_in_temp(self, runner_class, stdout, **runner_overrides):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        workspace = root / "SENSITIVE-workspace"
        evidence = root / "evidence"
        workspace.mkdir()
        (workspace / ".git").mkdir()
        fake_cli = root / "fake-cli"
        write_fake_executable(
            fake_cli,
            stdout,
            exit_code=runner_overrides.pop("exit_code", 0),
            sleep_seconds=runner_overrides.pop("sleep_seconds", 0),
        )
        runner = runner_class(executable=str(fake_cli))
        result = runner.run(
            role_id="host-codex",
            mode="start",
            session_id=None,
            trigger_text="SENSITIVE trigger text",
            workspace=workspace,
            mcp_command=[str(root / "SENSITIVE-python"), str(root / "SENSITIVE-server")],
            timeout_seconds=runner_overrides.pop("timeout_seconds", 300),
            evidence_dir=evidence,
            **runner_overrides,
        )
        return root, result

    def test_runners_launch_fake_executables_and_write_only_redacted_evidence(self):
        cases = (
            (self.runners.CodexRunner, CODEX_SUCCESS, "codex-session-1"),
            (self.runners.ClaudeRunner, CLAUDE_SUCCESS, "claude-session-1"),
        )
        for runner_class, fixture, expected_session in cases:
            with self.subTest(runner=runner_class.__name__):
                root, result = self.run_in_temp(runner_class, fixture)
                self.assertEqual(result.session_id, expected_session)
                evidence = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
                serialized = json.dumps(evidence)
                self.assertEqual(evidence["timeout_seconds"], 300)
                self.assertEqual(evidence["process_exit"], {"returncode": 0, "timed_out": False})
                self.assertTrue(evidence["session_present"])
                for secret in (
                    str(root),
                    "SENSITIVE trigger text",
                    expected_session,
                    "SENSITIVE-python",
                    "SENSITIVE-server",
                    "mcpServers",
                ):
                    self.assertNotIn(secret, serialized)

    def test_timeout_is_returned_as_a_distinct_process_fact(self):
        _, result = self.run_in_temp(
            self.runners.CodexRunner,
            "",
            sleep_seconds=1,
            timeout_seconds=0.05,
        )

        self.assertTrue(result.timed_out)
        self.assertTrue(result.process_exit["timed_out"])
        self.assertIsNotNone(result.process_exit["returncode"])
        self.assertIsNone(result.final_result)

    def test_unexpected_base_exception_terminates_and_reaps_process_group(self):
        class FakeProcess:
            pid = 4242
            returncode = -9

            def __init__(self):
                self.communicate_calls = 0
                self.wait_calls = 0

            def communicate(self, timeout=None):
                self.communicate_calls += 1
                if self.communicate_calls == 1:
                    raise KeyboardInterrupt()
                raise OSError("synthetic pipe failure")

            def wait(self, timeout=None):
                self.wait_calls += 1
                return self.returncode

        process = FakeProcess()
        with mock.patch.object(self.runners.subprocess, "Popen", return_value=process), mock.patch.object(
            self.runners.os, "killpg"
        ) as killpg:
            with self.assertRaises(KeyboardInterrupt):
                self.runners._execute(
                    ["fake"], workspace=Path("/tmp"), timeout_seconds=1
                )

        self.assertEqual(
            [call.args for call in killpg.call_args_list],
            [(4242, self.runners.signal.SIGTERM), (4242, self.runners.signal.SIGKILL)],
        )
        self.assertEqual(process.communicate_calls, 2)
        self.assertEqual(process.wait_calls, 1)

    def test_unexpected_tool_stops_runner_after_writing_redacted_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            evidence = root / "evidence"
            workspace.mkdir()
            (workspace / ".git").mkdir()
            fake_cli = root / "fake-cli"
            write_fake_executable(fake_cli, CODEX_FAILURE_AND_UNEXPECTED_TOOL)
            runner = self.runners.CodexRunner(executable=str(fake_cli))

            with self.assertRaises(RuntimeError) as raised:
                runner.run(
                    role_id="host-codex",
                    mode="start",
                    session_id=None,
                    trigger_text="SENSITIVE stop prompt",
                    workspace=workspace,
                    mcp_command=[str(root / "SENSITIVE-server")],
                    timeout_seconds=300,
                    evidence_dir=evidence,
                )

            self.assertEqual(
                raised.exception.result.unexpected_tool_calls[0]["tool"],
                "command_execution",
            )
            written = list(evidence.glob("runner-*.json"))
            self.assertEqual(len(written), 1)
            serialized = written[0].read_text(encoding="utf-8")
            self.assertIn("command_execution", serialized)
            self.assertNotIn("SENSITIVE stop prompt", serialized)
            self.assertNotIn(str(root), serialized)

    def test_agent_controlled_unexpected_tool_name_is_not_written_to_evidence(self):
        secret_tool = "SENSITIVE_agent_chosen_tool_name"
        fixture = "\n".join(
            (
                json.dumps(
                    {
                        "type": "system",
                        "subtype": "init",
                        "session_id": "claude-session-secret-tool",
                        "mcp_servers": [{"name": "sg6", "status": "connected"}],
                    }
                ),
                json.dumps(
                    {
                        "type": "assistant",
                        "session_id": "claude-session-secret-tool",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "tool-secret",
                                    "name": secret_tool,
                                    "input": {},
                                }
                            ]
                        },
                    }
                ),
            )
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            evidence = root / "evidence"
            workspace.mkdir()
            (workspace / ".git").mkdir()
            fake_cli = root / "fake-cli"
            write_fake_executable(fake_cli, fixture)
            runner = self.runners.ClaudeRunner(executable=str(fake_cli))

            with self.assertRaises(RuntimeError):
                runner.run(
                    role_id="investigator-claude",
                    mode="start",
                    session_id=None,
                    trigger_text="fixture",
                    workspace=workspace,
                    mcp_command=[str(root / "server")],
                    timeout_seconds=300,
                    evidence_dir=evidence,
                )

            serialized = next(evidence.glob("runner-*.json")).read_text(encoding="utf-8")
            self.assertNotIn(secret_tool, serialized)
            self.assertIn("unexpected_tool", serialized)

    def test_missing_executable_file_not_found_is_not_converted_to_agent_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            (workspace / ".git").mkdir()
            runner = self.runners.ClaudeRunner(executable=str(root / "does-not-exist"))
            with self.assertRaises(FileNotFoundError):
                runner.run(
                    role_id="investigator-claude",
                    mode="start",
                    session_id=None,
                    trigger_text="fixture",
                    workspace=workspace,
                    mcp_command=["python3", "server.py"],
                    timeout_seconds=300,
                    evidence_dir=root / "evidence",
                )

    def test_workspace_must_be_an_existing_git_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            runner = self.runners.CodexRunner(executable="does-not-matter")
            with self.assertRaises(ValueError):
                runner.run(
                    role_id="host-codex",
                    mode="start",
                    session_id=None,
                    trigger_text="fixture",
                    workspace=root,
                    mcp_command=["python3", "server.py"],
                    timeout_seconds=300,
                    evidence_dir=root / "evidence",
                )


if __name__ == "__main__":
    unittest.main()
