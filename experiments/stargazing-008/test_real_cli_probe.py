import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import blocking_mcp
from real_cli_probe import (
    CODEX_DISABLED_FEATURES,
    RealProbeError,
    build_claude_command,
    build_codex_command,
    preflight_shape,
    validate_codex_feature_surface,
    parse_claude_stream_json,
    parse_codex_jsonl,
    run_fake_cli_probe,
    run_real_cli_probe,
)


FAKE_CLI = r'''#!/usr/bin/env python3
import json, os, signal, subprocess, sys, time
from pathlib import Path

argv = sys.argv[1:]
product = "codex" if argv and argv[0] == "exec" else "claude"
behavior = os.environ.get("SG8_FAKE_BEHAVIOR", "force")
fixed_prompt = "Use only mcp__sg8__hold_until_stopped once, then wait."

def codex_config(key):
    pairs = [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == "-c"]
    values = [value.split("=", 1)[1] for value in pairs if value.startswith(key + "=")]
    if len(values) != 1: raise SystemExit(64)
    return json.loads(values[0])

if product == "codex":
    disabled_features = [
        "shell_tool", "unified_exec", "apps", "browser_use", "browser_use_external",
        "browser_use_full_cdp_access", "computer_use", "in_app_browser",
        "image_generation", "multi_agent", "goals", "workspace_dependencies",
        "skill_mcp_dependency_install", "tool_suggest", "code_mode_host", "memories",
    ]
    actual_disabled = [argv[index + 1] for index, value in enumerate(argv[:-1]) if value == "--disable"]
    if argv[:3] != ["exec", "--strict-config", "--ephemeral"] or actual_disabled != disabled_features: raise SystemExit(63)
    for flag, value in (("--sandbox", "read-only"), ("--color", "never")):
        if argv.count(flag) != 1 or argv[argv.index(flag) + 1] != value: raise SystemExit(63)
    if not {"--ignore-user-config", "--ignore-rules", "--json", "-C"}.issubset(argv) or Path(argv[argv.index("-C") + 1]).resolve() != Path.cwd().resolve() or argv[-1] != fixed_prompt: raise SystemExit(63)
    expected = {
        "mcp_servers.sg8.required":"true", "mcp_servers.sg8.startup_timeout_sec":"10",
        "mcp_servers.sg8.tool_timeout_sec":"20", "mcp_servers.sg8.enabled_tools":'["hold_until_stopped"]',
        "mcp_servers.sg8.default_tools_approval_mode":'"approve"',
    }
    for key, value in expected.items():
        pairs = [argv[i + 1] for i, item in enumerate(argv[:-1]) if item == "-c"]
        if pairs.count(key + "=" + value) != 1: raise SystemExit(63)
    command = [codex_config("mcp_servers.sg8.command"), *codex_config("mcp_servers.sg8.args")]
    expected_argv = [
        "exec", "--strict-config", "--ephemeral",
        *[part for feature in disabled_features for part in ("--disable", feature)],
        "--ignore-user-config", "--ignore-rules", "--sandbox", "read-only",
        "--color", "never", "--json", "-C", argv[argv.index("-C") + 1],
        "-c", "mcp_servers.sg8.command=" + json.dumps(command[0]),
        "-c", "mcp_servers.sg8.args=" + json.dumps(command[1:], separators=(",", ":")),
        "-c", "mcp_servers.sg8.required=true",
        "-c", "mcp_servers.sg8.startup_timeout_sec=10",
        "-c", "mcp_servers.sg8.tool_timeout_sec=20",
        "-c", 'mcp_servers.sg8.enabled_tools=["hold_until_stopped"]',
        "-c", 'mcp_servers.sg8.default_tools_approval_mode="approve"',
        fixed_prompt,
    ]
else:
    for flag, value in (("--tools", ""), ("--allowedTools", "mcp__sg8__hold_until_stopped"), ("--permission-mode", "dontAsk"), ("--permission-prompts", "none"), ("--max-budget-usd", "0.10"), ("--output-format", "stream-json")):
        if argv.count(flag) != 1 or argv[argv.index(flag) + 1] != value: raise SystemExit(63)
    if argv[0] != "-p" or not {"--restricted", "--disable-slash-commands", "--strict-mcp-config", "--no-chrome", "--no-session-persistence", "--verbose"}.issubset(argv) or argv[-1] != fixed_prompt: raise SystemExit(63)
    config = json.loads(argv[argv.index("--mcp-config") + 1])
    server = config["mcpServers"]["sg8"]
    if set(config["mcpServers"]) != {"sg8"} or server.get("type") != "stdio": raise SystemExit(63)
    command = [server["command"], *server["args"]]
    expected_config = {"mcpServers":{"sg8":{"type":"stdio", "command":command[0], "args":command[1:]}}}
    expected_argv = [
        "-p", "--restricted", "--disable-slash-commands", "--strict-mcp-config",
        "--tools", "", "--allowedTools", "mcp__sg8__hold_until_stopped",
        "--mcp-config", json.dumps(expected_config, sort_keys=True), "--no-chrome",
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--max-budget-usd", "0.10", "--no-session-persistence",
        "--output-format", "stream-json", "--verbose", fixed_prompt,
    ]

if argv != expected_argv: raise SystemExit(63)

mcp = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       text=True, shell=False)

def send(value, expect=True):
    mcp.stdin.write(json.dumps(value) + "\n"); mcp.stdin.flush()
    return json.loads(mcp.stdout.readline()) if expect else None

send({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":"2025-06-18", "capabilities":{}, "clientInfo":{"name":"fixture","version":"1"}}})
send({"jsonrpc":"2.0", "method":"notifications/initialized", "params":{}}, False)
listing = send({"jsonrpc":"2.0", "id":2, "method":"tools/list", "params":{}})
if [tool["name"] for tool in listing["result"]["tools"]] != ["hold_until_stopped"]: raise SystemExit(65)

def emit(value): print(json.dumps(value, sort_keys=True), flush=True)
if product == "codex":
    if behavior != "mcp-not-loaded":
        emit({"type":"thread.started", "thread_id":"fixture-session"})
        emit({"type":"turn.started"})
else:
    emit({"type":"system", "subtype":"init", "session_id":"fixture-session",
          "tools":["mcp__sg8__hold_until_stopped"],
          "mcp_servers":[{"name":"sg8","status":"failed" if behavior == "mcp-not-loaded" else "connected"}], "permissionMode":"dontAsk"})

if behavior == "early-completion": raise SystemExit(0)
if behavior == "unexpected-path": Path("unexpected.txt").write_text("unexpected\n")
if behavior not in {"tool-not-called", "never-ready"}:
    if product == "codex" and behavior != "mcp-not-loaded":
        emit({"type":"item.started", "item":{"id":"call-1", "type":"mcp_tool_call", "server":"sg8", "tool":"hold_until_stopped", "arguments":{}, "status":"in_progress"}})
    elif product == "claude":
        emit({"type":"assistant", "session_id":"fixture-session", "message":{"role":"assistant", "content":[{"type":"tool_use", "id":"call-1", "name":"mcp__sg8__hold_until_stopped", "input":{}}]}})
    send({"jsonrpc":"2.0", "id":3, "method":"tools/call", "params":{"name":"hold_until_stopped", "arguments":{}}}, False)
    ready = Path(command[command.index("--evidence-root") + 1]) / "mcp-ready.json"
    deadline = time.monotonic() + 1
    while not ready.exists() and time.monotonic() < deadline: time.sleep(0.002)
    if behavior == "wrong-pgid" and ready.exists():
        value = json.loads(ready.read_text()); value["mcp_pgid"] += 1
        temporary = ready.with_name(".mcp-ready.json.tmp")
        temporary.write_text(json.dumps(value)); os.replace(temporary, ready)

if behavior == "unexpected-tool":
    emit({"type":"item.started", "item":{"id":"bad", "type":"command_execution"}} if product == "codex" else {"type":"assistant", "message":{"content":[{"type":"tool_use","id":"bad","name":"Write","input":{}}]}})
if behavior == "unexpected-event": emit({"type":"mystery"})
if behavior == "malformed": print("not-json", flush=True)

grace = signal.SIGINT if product == "codex" else signal.SIGTERM
def stopped(_signal, _frame):
    if behavior == "late-write": Path("late.txt").write_text("late\n")
    if behavior == "graceful-terminal":
        if product == "codex": emit({"type":"turn.completed", "usage":{"input_tokens":1,"output_tokens":0}})
        else: emit({"type":"result", "subtype":"success", "is_error":False, "terminal_reason":"completed", "session_id":"fixture-session", "result":"", "usage":{"input_tokens":1,"output_tokens":0}})
    raise SystemExit(0)
if behavior == "force": signal.signal(grace, signal.SIG_IGN)
else: signal.signal(grace, stopped)
while True: time.sleep(30)
'''

CODEX_PREFLIGHT = {
    "product": "codex",
    "version": "fixture-version",
    "required_flags_present": True,
    "codex_feature_surface_confirmed": True,
}


class BlockingMcpTest(unittest.TestCase):
    def test_exposes_only_fixed_hold_tool_without_identity_or_path_arguments(self):
        listing = blocking_mcp.tools_list_result()
        self.assertEqual([tool["name"] for tool in listing["tools"]], ["hold_until_stopped"])
        self.assertEqual(listing["tools"][0]["inputSchema"], {
            "type": "object", "properties": {}, "additionalProperties": False,
        })

    def test_hold_startup_writes_atomic_fixed_evidence_from_server_context(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = blocking_mcp.record_hold_started(root)
            self.assertEqual(result["mcp_pid"], os.getpid())
            self.assertEqual(result["mcp_pgid"], os.getpgrp())
            self.assertEqual(json.loads((root / "mcp-effect.json").read_text()), {"effect":"hold_started"})
            self.assertEqual((root / "mcp-marker.txt").read_text(), "sg8-hold-started\n")
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_hold_rejects_any_tool_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                blocking_mcp.validate_hold_call({"role":"forged"}, Path(directory))

    def test_stdio_protocol_lists_only_the_hold_tool(self):
        for protocol in ("2025-03-26", "2025-06-18"):
            with self.subTest(protocol=protocol), tempfile.TemporaryDirectory() as directory:
                requests = "\n".join((
                    json.dumps({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":protocol, "capabilities":{}, "clientInfo":{"name":"fixture","version":"1"}}}),
                    json.dumps({"jsonrpc":"2.0", "id":2, "method":"tools/list"}),
                )) + "\n"
                completed = subprocess.run(
                    [sys.executable, str(HERE / "blocking_mcp.py"), "--evidence-root", directory, "--role-id", "host"],
                    input=requests, text=True, capture_output=True, shell=False, timeout=1, check=True,
                )
                replies = [json.loads(line) for line in completed.stdout.splitlines()]
                self.assertEqual(replies[0]["result"]["protocolVersion"], protocol)
                self.assertEqual(replies[1]["result"], blocking_mcp.tools_list_result())
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_stdio_server_rejects_an_unbound_role_before_serving(self):
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [sys.executable, str(HERE / "blocking_mcp.py"), "--evidence-root", directory, "--role-id", "forged"],
                input="", text=True, capture_output=True, shell=False, timeout=1,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_stdio_server_rejects_an_unsupported_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            request = json.dumps({"jsonrpc":"2.0", "id":1, "method":"initialize", "params":{"protocolVersion":"2099-01-01"}}) + "\n"
            completed = subprocess.run(
                [sys.executable, str(HERE / "blocking_mcp.py"), "--evidence-root", directory, "--role-id", "host"],
                input=request, text=True, capture_output=True, shell=False, timeout=1, check=True,
            )
            reply = json.loads(completed.stdout)
            self.assertEqual(reply["error"]["code"], -32602)
            self.assertEqual(list(Path(directory).iterdir()), [])


class CommandBuilderTest(unittest.TestCase):
    def setUp(self):
        self.mcp = [
            "/fixed/python", "/fixed/blocking_mcp.py", "--evidence-root", "/fixed/root",
            "--role-id", "host",
        ]

    def test_codex_command_has_exact_restricted_surface(self):
        command = build_codex_command("/fixed/codex", "/fixed/git", self.mcp, "fixed prompt")
        rendered = "\n".join(command)
        self.assertEqual(command[:2], ["/fixed/codex", "exec"])
        self.assertIn("--ignore-user-config", command)
        self.assertIn("--ignore-rules", command)
        self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
        self.assertIn("--json", command)
        self.assertEqual(command[command.index("--color") + 1], "never")
        self.assertIn("--strict-config", command)
        self.assertIn("--ephemeral", command)
        disabled = [
            command[index + 1]
            for index, value in enumerate(command[:-1])
            if value == "--disable"
        ]
        self.assertEqual(disabled, list(CODEX_DISABLED_FEATURES))
        self.assertIn("mcp_servers.sg8.required=true", rendered)
        self.assertIn('enabled_tools=["hold_until_stopped"]', rendered)
        self.assertIn('mcp_servers.sg8.command="/fixed/python"', rendered)
        self.assertIn('mcp_servers.sg8.args=["/fixed/blocking_mcp.py"', rendered)
        self.assertEqual(command[-1], "fixed prompt")

    def test_claude_command_has_exact_restricted_surface(self):
        command = build_claude_command("/fixed/claude", "/fixed/git", self.mcp, "fixed prompt")
        self.assertEqual(command[0], "/fixed/claude")
        for flag in ("-p", "--restricted", "--disable-slash-commands", "--strict-mcp-config"):
            self.assertIn(flag, command)
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--allowedTools") + 1], "mcp__sg8__hold_until_stopped")
        self.assertEqual(command[command.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(command[command.index("--permission-prompts") + 1], "none")
        self.assertEqual(command[command.index("--max-budget-usd") + 1], "0.10")
        self.assertIn("--no-session-persistence", command)
        self.assertEqual(command[command.index("--output-format") + 1], "stream-json")
        config = json.loads(command[command.index("--mcp-config") + 1])
        self.assertEqual(config["mcpServers"]["sg8"]["command"], self.mcp[0])
        self.assertEqual(config["mcpServers"]["sg8"]["args"], self.mcp[1:])
        self.assertEqual(config["mcpServers"]["sg8"]["type"], "stdio")

    def test_builder_commands_reject_all_token_mutations_in_fake_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            evidence = root / "evidence"
            workspace.mkdir(); evidence.mkdir(); (workspace / ".git").mkdir()
            fake = root / "fake-cli"
            fake.write_text(FAKE_CLI, encoding="utf-8")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            mcp = [sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(evidence), "--role-id", "host"]
            environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SG8_FAKE_BEHAVIOR":"force"}
            mutations = []
            for product, command in (
                ("codex", build_codex_command(fake, workspace, mcp)),
                ("claude", build_claude_command(fake, workspace, mcp)),
            ):
                mutations.extend((
                    (product, "extra_flag", command[:-1] + ["--extra", command[-1]]),
                    (product, "duplicate_token", command[:2] + [command[1]] + command[2:]),
                    (product, "extra_config_flag", command[:-1] + ["-c", "unexpected=true", command[-1]]),
                ))
            claude = build_claude_command(fake, workspace, mcp)
            config_index = claude.index("--mcp-config") + 1
            altered = list(claude)
            config = json.loads(altered[config_index]); config["extra"] = True
            altered[config_index] = json.dumps(config, sort_keys=True)
            mutations.append(("claude", "altered_mcp_config", altered))
            for product, mutation_name, command in mutations:
                with self.subTest(product=product, mutation_name=mutation_name):
                    completed = subprocess.run(command, cwd=workspace, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
                    self.assertEqual(completed.returncode, 63)
                    self.assertEqual(list(evidence.iterdir()), [])

    def test_preflight_keeps_only_version_and_required_flag_shape(self):
        feature_output = "\n".join(
            feature + " stable true" for feature in CODEX_DISABLED_FEATURES
        )
        facts = preflight_shape(
            "codex", "codex-cli 0.fixture", "--json --sandbox --disable --strict-config --ephemeral",
            feature_output,
        )
        self.assertEqual(facts, {
            "product":"codex", "version":"0.fixture", "required_flags_present":True,
            "codex_feature_surface_confirmed":True,
        })
        self.assertNotIn("--json", json.dumps(facts))
        missing_strict = preflight_shape(
            "codex", "codex-cli 0.fixture", "--json --sandbox --disable --ephemeral",
            feature_output,
        )
        self.assertFalse(missing_strict["required_flags_present"])

    def test_preflight_uses_exact_product_specific_version_shapes(self):
        feature_output = "\n".join(
            feature + " stable false" for feature in CODEX_DISABLED_FEATURES
        )
        fixtures = (
            ("codex", "codex-cli 0.144.6\n", feature_output, "0.144.6"),
            ("claude", "2.1.261 (Claude Code)\n", None, "2.1.261"),
        )
        for product, output, features, expected_version in fixtures:
            with self.subTest(product=product):
                facts = preflight_shape(product, output, "", features)
                self.assertEqual(facts["version"], expected_version)
                self.assertNotIn(output.strip(), json.dumps(facts))

    def test_preflight_rejects_injected_or_malformed_version_output(self):
        feature_output = "\n".join(
            feature + " stable false" for feature in CODEX_DISABLED_FEATURES
        )
        invalid = (
            ("codex", "codex-cli 0.144.6\nextra", feature_output),
            ("codex", "/tmp/codex-cli 0.144.6", feature_output),
            ("codex", "prefix codex-cli 0.144.6", feature_output),
            ("codex", "codex-cli 0.144.6 suffix", feature_output),
            ("codex", "codex-cli 0.144.6\n\n", feature_output),
            ("codex", "codex-cli ../../unsafe", feature_output),
            ("claude", "2.1.261 (Claude Code)\nextra", None),
            ("claude", "/tmp/2.1.261 (Claude Code)", None),
            ("claude", "prefix 2.1.261 (Claude Code)", None),
            ("claude", "2.1.261 (Claude Code) suffix", None),
            ("claude", "2.1.261 (Claude Code)\n\n", None),
            ("claude", "../../unsafe (Claude Code)", None),
            ("claude", "claude 2.1.261", None),
        )
        for product, output, features in invalid:
            with self.subTest(product=product, output=repr(output)):
                with self.assertRaisesRegex(RealProbeError, "unsafe version shape"):
                    preflight_shape(product, output, "", features)

    def test_codex_feature_surface_blocks_missing_unknown_or_malformed_required_rows(self):
        stages = ("stable", "experimental", "under development", "deprecated", "removed")
        valid = "\n".join(
            feature + " " + stages[index % len(stages)] + " false"
            for index, feature in enumerate(CODEX_DISABLED_FEATURES)
        )
        self.assertTrue(validate_codex_feature_surface(valid))
        for invalid in (
            "\n".join(valid.splitlines()[:-1]),
            valid.replace(" stable false", " unknown false", 1),
            valid + "\n" + CODEX_DISABLED_FEATURES[0] + " stable false",
        ):
            with self.subTest(invalid=invalid[-40:]):
                with self.assertRaises(RealProbeError):
                    validate_codex_feature_surface(invalid)

    def test_product_parsers_accept_only_observed_machine_shapes(self):
        codex = "\n".join(json.dumps(value) for value in (
            {"type":"thread.started", "thread_id":"fixture-session"},
            {"type":"turn.started"},
            {"type":"item.started", "item":{"id":"call-1", "type":"mcp_tool_call", "server":"sg8", "tool":"hold_until_stopped", "arguments":{}, "status":"in_progress"}},
            {"type":"turn.completed", "usage":{"input_tokens":1,"output_tokens":0}},
        ))
        claude = "\n".join(json.dumps(value) for value in (
            {"type":"system", "subtype":"init", "session_id":"fixture-session", "tools":["mcp__sg8__hold_until_stopped"], "mcp_servers":[{"name":"sg8","status":"connected"}], "permissionMode":"dontAsk"},
            {"type":"assistant", "session_id":"fixture-session", "message":{"role":"assistant", "content":[{"type":"tool_use", "id":"call-1", "name":"mcp__sg8__hold_until_stopped", "input":{}}]}},
            {"type":"result", "subtype":"success", "is_error":False, "terminal_reason":"completed", "session_id":"fixture-session", "result":"", "usage":{"input_tokens":1,"output_tokens":0}},
        ))
        self.assertEqual(parse_codex_jsonl(codex), (1, 1, 1))
        self.assertEqual(parse_claude_stream_json(claude), (1, 1, 1))
        for parser in (parse_codex_jsonl, parse_claude_stream_json):
            with self.assertRaises(RealProbeError):
                parser(json.dumps({"type":"unknown"}))


class FakeLiveControllerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.evidence = self.root / "evidence"
        self.workspace.mkdir()
        self.evidence.mkdir()
        (self.workspace / ".git").mkdir()
        self.fake = self.root / "fake-cli"
        self.fake.write_text(FAKE_CLI, encoding="utf-8")
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)

    def probe(self, product="codex", behavior="force", **kwargs):
        ready_timeout = kwargs.pop("ready_timeout", 10.0)
        graceful_timeout = kwargs.pop("graceful_timeout", 0.04)
        cleanup_timeout = kwargs.pop("cleanup_timeout", 0.7)
        return run_fake_cli_probe(
            product=product,
            executable=self.fake,
            version="fixture-version",
            workspace=self.workspace,
            evidence_root=self.evidence,
            mcp_command=[
                sys.executable, str(HERE / "blocking_mcp.py"),
                "--evidence-root", str(self.evidence), "--role-id", "host",
            ],
            behavior=behavior,
            ready_timeout=ready_timeout,
            graceful_timeout=graceful_timeout,
            cleanup_timeout=cleanup_timeout,
            **kwargs,
        )

    def test_three_success_contracts_and_sanitized_shape(self):
        for behavior, terminal, result, layer in (
            ("graceful-terminal", True, "cancelled", "graceful"),
            ("graceful-unknown", False, "result_unknown", "graceful"),
            ("force", False, "result_unknown", "force_after_deadline"),
        ):
            with self.subTest(behavior=behavior):
                result_value = self.probe(behavior=behavior)
                self.assertEqual(result_value["terminal_present"], terminal)
                self.assertEqual(result_value["result_state"], result)
                self.assertEqual(result_value["stop_layer"], layer)
                self.assertEqual(result_value["slot_state"], "released")
                self.assertEqual(result_value["retry_eligibility"], "blocked")
                self.assertTrue(result_value["process_group_confirmed"])
                self.assertEqual(set(result_value), {
                    "schema_version", "product", "version", "stop_layer",
                    "terminal_present", "result_state", "slot_state",
                    "retry_eligibility", "side_effects", "process_group_confirmed",
                    "event_counts", "decision_escalation",
                })
                self.assertNotIn("fixed prompt", json.dumps(result_value))
                self.reset_dirs()

    def test_both_product_signal_paths(self):
        for product in ("codex", "claude"):
            with self.subTest(product=product):
                self.assertEqual(self.probe(product=product, behavior="graceful-unknown")["product"], product)
                self.reset_dirs()

    def test_fail_closed_scenarios(self):
        for behavior in (
            "early-completion", "mcp-not-loaded", "tool-not-called",
            "unexpected-tool", "unexpected-event", "malformed", "never-ready",
            "unexpected-path",
            "late-write",
        ):
            with self.subTest(behavior=behavior):
                with self.assertRaises(RealProbeError) as caught:
                    self.probe(behavior=behavior, ready_timeout=0.2 if behavior == "never-ready" else 10.0)
                self.assertNotIn("released", str(caught.exception))
                self.reset_dirs()

    def test_mcp_pid_outside_expected_group_fails_closed(self):
        with self.assertRaises(RealProbeError):
            self.probe(getpgid=lambda _pid: os.getpgrp())

    def test_identity_lost_with_live_mcp_preserves_evidence_and_never_claims_release(self):
        captured = {}
        ready = self.evidence / "mcp-ready.json"

        class IdentityLostView:
            def __init__(self, process):
                self._process = process
                self.pid = process.pid
                self.stdout = process.stdout
                self.stderr = process.stderr

            def poll(self):
                return 0 if ready.exists() else self._process.poll()

            def wait(self, timeout=None):
                return self._process.wait(timeout=timeout)

            def communicate(self, timeout=None):
                return self._process.communicate(timeout=timeout)

        def factory(*args, **kwargs):
            process = subprocess.Popen(*args, **kwargs)
            captured["process"] = process
            return IdentityLostView(process)

        try:
            with self.assertRaises(RealProbeError) as caught:
                self.probe(popen_factory=factory, cleanup_timeout=0.03)
            self.assertFalse(caught.exception.cleanup_outcome["complete"])
            self.assertTrue(ready.exists())
            self.assertNotIn("released", str(caught.exception))
        finally:
            process = captured.get("process")
            if process is not None and process.poll() is None:
                self.assertEqual(os.getpgid(process.pid), process.pid)
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1)
                for stream in (process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()

    def test_start_failure_fails_closed(self):
        self.fake.unlink()
        with self.assertRaises(RealProbeError):
            self.probe()

    def test_surviving_observation_and_group_confirmation_fail_closed(self):
        for override in (
            {"pid_gone": lambda _pid: False},
            {"group_gone": lambda _pgid: False},
        ):
            with self.subTest(override=tuple(override)):
                with self.assertRaises(RealProbeError):
                    self.probe(**override)
                self.reset_dirs()

    def test_unknown_product_and_version_or_parser_shape_fail_closed(self):
        with self.assertRaises(RealProbeError):
            self.probe(product="other")
        with self.assertRaises(RealProbeError):
            run_fake_cli_probe(
                product="codex", executable=self.fake, version="private/path version",
                workspace=self.workspace, evidence_root=self.evidence,
                mcp_command=["fixed"], behavior="force",
            )

    def test_mcp_startup_binding_cannot_be_omitted_or_redirected(self):
        for command in (
            [sys.executable, str(HERE / "blocking_mcp.py")],
            [sys.executable, str(HERE / "blocking_mcp.py"), "--evidence-root", "/other", "--role-id", "host"],
            [sys.executable, str(HERE / "blocking_mcp.py"), "--evidence-root", str(self.evidence), "--role-id", "other"],
            [sys.executable, str(HERE / "blocking_mcp.py"), "--evidence-root", str(self.evidence), "--role-id", "host", "--extra"],
        ):
            with self.subTest(command=command):
                with self.assertRaises(RealProbeError):
                    run_fake_cli_probe(
                        product="codex", executable=self.fake, version="fixture-version",
                        workspace=self.workspace, evidence_root=self.evidence,
                        mcp_command=command, behavior="force",
                    )
                self.assertEqual(list(self.evidence.iterdir()), [])

    def test_real_entry_requires_preflight_separate_environment_deadline_and_0600_raw_target(self):
        raw = self.root / "raw-review.json"
        raw.touch(mode=0o600)
        result = run_real_cli_probe(
            product="codex", executable=self.fake, version="fixture-version",
            workspace=self.workspace, evidence_root=self.evidence,
            mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
            preflight=CODEX_PREFLIGHT,
            launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            total_timeout=3.0, raw_evidence_path=raw,
            ready_timeout=10.0, graceful_timeout=0.04, cleanup_timeout=0.7,
        )
        self.assertEqual(result["result_state"], "result_unknown")
        self.assertEqual(raw.stat().st_mode & 0o777, 0o600)
        audit = json.loads(raw.read_text())
        self.assertEqual(audit["command_shape"]["tool"], "hold_until_stopped")
        self.assertEqual(
            audit["command_shape"]["disabled_features"],
            list(CODEX_DISABLED_FEATURES),
        )
        self.assertTrue(audit["command_shape"]["strict_config"])
        self.assertTrue(audit["command_shape"]["ephemeral"])
        self.assertEqual(audit["cli"]["pid"], audit["cli"]["pgid"])
        self.assertEqual(len(audit["observed_pids"]), 2)
        self.assertEqual(audit["signal_requests"][0]["layer"], "graceful")
        self.assertIn("configured_deadlines", audit)
        self.assertTrue(all(audit["confirmation"]["pids"].values()))
        self.assertTrue(audit["confirmation"]["group_gone"])
        self.assertIn("stdout", audit)
        self.assertIn("stderr", audit)
        self.assertNotIn(str(raw), json.dumps(result))
        self.assertNotIn("fixture-session", json.dumps(result))
        raw.unlink()

    def test_claude_raw_command_shape_records_every_restricted_surface_fact(self):
        raw = self.root / "claude-review.json"
        result = run_real_cli_probe(
            product="claude", executable=self.fake, version="fixture-version",
            workspace=self.workspace, evidence_root=self.evidence,
            mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
            preflight={"product":"claude", "version":"fixture-version", "required_flags_present":True},
            launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            total_timeout=5.0, raw_evidence_path=raw,
            ready_timeout=10.0, graceful_timeout=0.04, cleanup_timeout=0.7,
        )
        self.assertEqual(result["product"], "claude")
        shape = json.loads(raw.read_text())["command_shape"]
        self.assertEqual({key: shape[key] for key in (
            "builtins_empty", "allowed_tool", "restricted", "strict_mcp",
            "permission_mode", "permission_prompts", "max_budget_usd",
            "no_session_persistence", "no_chrome", "slash_disabled",
        )}, {
            "builtins_empty": True, "allowed_tool": "mcp__sg8__hold_until_stopped",
            "restricted": True, "strict_mcp": True, "permission_mode": "dontAsk",
            "permission_prompts": "none", "max_budget_usd": "0.10",
            "no_session_persistence": True, "no_chrome": True, "slash_disabled": True,
        })
        raw.unlink()

    def test_real_entry_requires_raw_path_before_launch(self):
        with self.assertRaises(RealProbeError):
            run_real_cli_probe(
                product="codex", executable=self.fake, version="fixture-version",
                workspace=self.workspace, evidence_root=self.evidence,
                mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
                preflight=CODEX_PREFLIGHT,
                launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                total_timeout=3.0, raw_evidence_path=None,
            )
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_baseexception_preserves_object_and_exposes_cleanup_and_raw_outcomes(self):
        raw = self.root / "interrupt-review.json"
        interrupt = KeyboardInterrupt("fixture interrupt")

        def interrupted(_pid):
            raise interrupt

        with self.assertRaises(KeyboardInterrupt) as caught:
            run_real_cli_probe(
                product="codex", executable=self.fake, version="fixture-version",
                workspace=self.workspace, evidence_root=self.evidence,
                mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
                preflight=CODEX_PREFLIGHT,
                launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                total_timeout=3.0, raw_evidence_path=raw, getpgid=interrupted,
                ready_timeout=10.0, cleanup_timeout=0.7,
            )
        self.assertIs(caught.exception, interrupt)
        self.assertTrue(hasattr(interrupt, "sg8_cleanup_outcome"))
        self.assertIn("cleanup_outcome", json.loads(raw.read_text()))
        raw.unlink()

    def test_raw_write_failure_never_masks_baseexception(self):
        interrupt = KeyboardInterrupt("fixture interrupt")

        class BrokenRaw:
            closed = False
            def write(self, _value):
                raise OSError("fixture raw failure")
            def flush(self):
                pass
            def close(self):
                self.closed = True

        with self.assertRaises(KeyboardInterrupt) as caught:
            run_real_cli_probe(
                product="codex", executable=self.fake, version="fixture-version",
                workspace=self.workspace, evidence_root=self.evidence,
                mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
                preflight=CODEX_PREFLIGHT,
                launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                total_timeout=3.0, raw_evidence_path=self.root / "unused.json",
                raw_open=lambda _path: BrokenRaw(), getpgid=lambda _pid: (_ for _ in ()).throw(interrupt),
                ready_timeout=10.0, cleanup_timeout=0.7,
            )
        self.assertIs(caught.exception, interrupt)
        self.assertEqual(interrupt.sg8_raw_evidence_outcome, "write_failed")
        self.assertTrue(hasattr(interrupt, "sg8_cleanup_outcome"))

    def test_raw_write_failure_prevents_a_success_result(self):
        class BrokenRaw:
            closed = False
            def write(self, _value):
                raise OSError("fixture raw failure")
            def flush(self):
                pass
            def close(self):
                self.closed = True

        with self.assertRaisesRegex(RealProbeError, "raw evidence write failed"):
            run_real_cli_probe(
                product="codex", executable=self.fake, version="fixture-version",
                workspace=self.workspace, evidence_root=self.evidence,
                mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
                preflight=CODEX_PREFLIGHT,
                launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                total_timeout=3.0, raw_evidence_path=self.root / "unused.json",
                raw_open=lambda _path: BrokenRaw(), ready_timeout=10.0, cleanup_timeout=0.7,
            )

    def test_real_entry_never_overwrites_existing_raw_evidence(self):
        raw = self.root / "raw-review.json"
        raw.write_text("sentinel\n")
        raw.chmod(0o600)
        with self.assertRaises(RealProbeError):
            run_real_cli_probe(
                product="codex", executable=self.fake, version="fixture-version",
                workspace=self.workspace, evidence_root=self.evidence,
                mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
                preflight=CODEX_PREFLIGHT,
                launch_environment={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                total_timeout=3.0, raw_evidence_path=raw,
            )
        self.assertEqual(raw.read_text(), "sentinel\n")
        self.assertEqual(list(self.evidence.iterdir()), [])

    def test_real_entry_rejects_failed_preflight_fake_environment_and_repo_raw_path(self):
        common = dict(
            product="codex", executable=self.fake, version="fixture-version",
            workspace=self.workspace, evidence_root=self.evidence,
            mcp_command=[sys.executable, str((HERE / "blocking_mcp.py").resolve()), "--evidence-root", str(self.evidence), "--role-id", "host"],
            total_timeout=3.0, raw_evidence_path=HERE / "forbidden-raw.json",
        )
        with self.assertRaises(RealProbeError):
            run_real_cli_probe(preflight={**CODEX_PREFLIGHT, "required_flags_present":False}, launch_environment={"PATH":"/usr/bin"}, **common)
        with self.assertRaises(RealProbeError):
            run_real_cli_probe(preflight=CODEX_PREFLIGHT, launch_environment={"SG8_FAKE_BEHAVIOR":"force"}, **common)
        with self.assertRaises(RealProbeError):
            run_real_cli_probe(preflight=CODEX_PREFLIGHT, launch_environment={"PATH":"/usr/bin"}, **common)
        self.assertFalse((HERE / "forbidden-raw.json").exists())

    def reset_dirs(self):
        for directory in (self.workspace, self.evidence):
            for item in directory.iterdir():
                if item.name != ".git":
                    if item.is_dir():
                        item.rmdir()
                    else:
                        item.unlink()


if __name__ == "__main__":
    unittest.main()
