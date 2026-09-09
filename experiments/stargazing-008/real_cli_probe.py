"""Disposable fake-executable preflight for the Stargazing 8 real CLI stop probe."""

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from contracts import (
    build_force_stopped_summary,
    build_graceful_stopped_summary,
    build_graceful_stopped_unknown_summary,
    validate_summary,
)
from stop_controller import _emergency_cleanup, _final_safety_cleanup, _hard_cleanup


FIXED_PROMPT = "Use only mcp__sg8__hold_until_stopped once, then wait."
CODEX_DISABLED_FEATURES = (
    "shell_tool",
    "unified_exec",
    "apps",
    "browser_use",
    "browser_use_external",
    "browser_use_full_cdp_access",
    "computer_use",
    "in_app_browser",
    "image_generation",
    "multi_agent",
    "goals",
    "workspace_dependencies",
    "skill_mcp_dependency_install",
    "tool_suggest",
    "code_mode_host",
    "memories",
)
_VERSION = re.compile(r"^[A-Za-z0-9._-]+$")
_VERSION_OUTPUT = {
    "codex": re.compile(r"codex-cli ([A-Za-z0-9._-]+)\n?"),
    "claude": re.compile(r"([A-Za-z0-9._-]+) \(Claude Code\)\n?"),
}
_EVIDENCE_FILES = {"mcp-ready.json", "mcp-effect.json", "mcp-marker.txt", ".mcp-ready.json.tmp", ".mcp-effect.json.tmp"}


class RealProbeError(RuntimeError):
    def __init__(self, message, cleanup_outcome=None):
        super().__init__(message)
        self.cleanup_outcome = cleanup_outcome


def _mcp_config(command):
    return {"mcpServers": {"sg8": {"type": "stdio", "command": command[0], "args": command[1:]}}}


def build_codex_command(executable, workspace, mcp_command, prompt=FIXED_PROMPT):
    return [
        str(executable), "exec", "--strict-config", "--ephemeral",
        *[part for feature in CODEX_DISABLED_FEATURES for part in ("--disable", feature)],
        "--ignore-user-config",
        "--ignore-rules", "--sandbox", "read-only", "--color", "never", "--json", "-C", str(workspace),
        "-c", "mcp_servers.sg8.command=" + json.dumps(mcp_command[0]),
        "-c", "mcp_servers.sg8.args=" + json.dumps(mcp_command[1:], separators=(",", ":")),
        "-c", "mcp_servers.sg8.required=true",
        "-c", "mcp_servers.sg8.startup_timeout_sec=10",
        "-c", "mcp_servers.sg8.tool_timeout_sec=20",
        "-c", 'mcp_servers.sg8.enabled_tools=["hold_until_stopped"]',
        "-c", 'mcp_servers.sg8.default_tools_approval_mode="approve"',
        prompt,
    ]


def build_claude_command(executable, workspace, mcp_command, prompt=FIXED_PROMPT):
    return [
        str(executable), "-p", "--restricted", "--disable-slash-commands",
        "--strict-mcp-config", "--tools", "", "--allowedTools",
        "mcp__sg8__hold_until_stopped", "--mcp-config",
        json.dumps(_mcp_config(mcp_command), sort_keys=True), "--no-chrome",
        "--permission-mode", "dontAsk", "--permission-prompts", "none",
        "--max-budget-usd", "0.10", "--no-session-persistence",
        "--output-format", "stream-json",
        "--verbose", prompt,
    ]


def validate_codex_feature_surface(feature_output):
    rows = {}
    allowed_stages = {
        "stable", "experimental", "under development", "deprecated", "removed"
    }
    for line in feature_output.splitlines():
        parts = line.split()
        if len(parts) < 3 or parts[0] in rows:
            raise RealProbeError("unknown Codex feature-list shape")
        name, stage, enabled = parts[0], " ".join(parts[1:-1]), parts[-1]
        if stage not in allowed_stages or enabled not in {"true", "false"}:
            raise RealProbeError("unknown Codex feature-list shape")
        rows[name] = (stage, enabled)
    if any(feature not in rows for feature in CODEX_DISABLED_FEATURES):
        raise RealProbeError("required Codex feature is missing")
    return True


def preflight_shape(product, version_output, help_output, feature_output=None):
    required = {
        "codex": (
            "--json", "--sandbox", "--disable", "--strict-config", "--ephemeral"
        ),
        "claude": (
            "--restricted", "--strict-mcp-config", "--allowedTools",
            "--no-session-persistence", "--permission-prompts", "--max-budget-usd",
        ),
    }
    if product not in required:
        raise RealProbeError("unsupported product")
    match = _VERSION_OUTPUT[product].fullmatch(version_output)
    if match is None:
        raise RealProbeError("unsafe version shape")
    version = match.group(1)
    facts = {
        "product": product,
        "version": version,
        "required_flags_present": all(flag in help_output for flag in required[product]),
    }
    if product == "codex":
        facts["codex_feature_surface_confirmed"] = validate_codex_feature_surface(
            feature_output if isinstance(feature_output, str) else ""
        )
    return facts


def _gone_pid(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _gone_group(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _wait(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.004)
    return predicate()


def _leader_owns(process, pgid):
    if process.poll() is not None:
        return False
    try:
        return os.getpgid(process.pid) == pgid
    except (ProcessLookupError, PermissionError):
        return False


def _cleanup(process, pgid, observed, timeout):
    if process is None:
        return {"complete": True, "group_kill": "not_started"}
    outcome = _hard_cleanup(process, pgid, observed, timeout)
    if not outcome["complete"]:
        outcome["emergency_cleanup"] = _emergency_cleanup(process, pgid, observed, timeout)
        if not outcome["emergency_cleanup"]["complete"]:
            outcome["final_safety_cleanup"] = _final_safety_cleanup(process, pgid, observed, timeout)
    return outcome


def _read_events(product, stdout):
    loaded = 0
    calls = 0
    terminals = 0
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise RealProbeError("malformed machine output") from error
        if not isinstance(event, dict):
            raise RealProbeError("unknown machine event")
        if product == "codex":
            kind = event.get("type")
            if kind in {"thread.started", "turn.started"}:
                continue
            item = event.get("item")
            if kind == "item.started" and isinstance(item, dict):
                if item.get("type") == "mcp_tool_call" and item.get("server") == "sg8" and item.get("tool") == "hold_until_stopped" and item.get("arguments") == {}:
                    loaded = 1
                    calls += 1
                    continue
                raise RealProbeError("unexpected Codex tool event")
            if kind == "turn.completed" and isinstance(event.get("usage"), dict):
                terminals += 1
                continue
            raise RealProbeError("unknown Codex JSONL event")
        else:
            kind = event.get("type")
            if kind == "system" and event.get("subtype") == "init":
                if event.get("tools") != ["mcp__sg8__hold_until_stopped"] or event.get("mcp_servers") != [{"name":"sg8","status":"connected"}] or event.get("permissionMode") != "dontAsk":
                    raise RealProbeError("invalid Claude tool surface")
                loaded += 1
                continue
            content = event.get("message", {}).get("content") if isinstance(event.get("message"), dict) else None
            if kind == "assistant" and isinstance(content, list) and len(content) == 1:
                block = content[0]
                if block.get("type") == "tool_use" and block.get("name") == "mcp__sg8__hold_until_stopped" and block.get("input") == {}:
                    calls += 1
                    continue
                raise RealProbeError("unexpected Claude tool event")
            if kind == "result" and event.get("is_error") is False and event.get("terminal_reason") == "completed" and isinstance(event.get("usage"), dict):
                terminals += 1
                continue
            raise RealProbeError("unknown Claude stream-json event")
    return loaded, calls, terminals


def parse_codex_jsonl(text):
    return _read_events("codex", text)


def parse_claude_stream_json(text):
    return _read_events("claude", text)


def _remove_known(root):
    for item in root.iterdir():
        if item.name in _EVIDENCE_FILES and item.is_file() and not item.is_symlink():
            item.unlink()


def _startup_value(command, flag):
    try:
        index = command.index(flag)
        return command[index + 1]
    except (ValueError, IndexError):
        return None


def _open_raw_evidence(path):
    if path is None:
        return None
    path = Path(path)
    repository = Path(__file__).resolve().parents[2]
    try:
        path.resolve().relative_to(repository)
    except ValueError:
        pass
    else:
        raise RealProbeError("raw evidence must be outside repository")
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.stat().st_size != 0 or (path.stat().st_mode & 0o777) != 0o600:
            raise RealProbeError("raw evidence target is not an empty 0600 file")
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    else:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return os.fdopen(descriptor, "w", encoding="utf-8")


def _run_cli_probe(
    *, product, executable, version, workspace, evidence_root, mcp_command,
    launch_environment, ready_timeout=10.0, graceful_timeout=0.05, cleanup_timeout=1.0,
    total_timeout=3.0, raw_evidence_path=None, pid_gone=None, group_gone=None,
    getpgid=os.getpgid, popen_factory=subprocess.Popen, raw_open=_open_raw_evidence,
):
    if product not in {"codex", "claude"} or not _VERSION.fullmatch(version) or total_timeout <= 0:
        raise RealProbeError("invalid sanitized preflight")
    workspace, evidence_root = Path(workspace), Path(evidence_root)
    expected_mcp = [
        sys.executable, str((Path(__file__).resolve().parent / "blocking_mcp.py").resolve()),
        "--evidence-root", str(evidence_root), "--role-id", "host",
    ]
    if mcp_command != expected_mcp:
        raise RealProbeError("MCP startup binding mismatch")
    if (
        not workspace.is_dir()
        or not (workspace / ".git").is_dir()
        or {item.name for item in workspace.iterdir()} != {".git"}
        or not evidence_root.is_dir()
        or any(evidence_root.iterdir())
    ):
        raise RealProbeError("probe paths are not fresh")
    builder = build_codex_command if product == "codex" else build_claude_command
    command = builder(executable, workspace, mcp_command, FIXED_PROMPT)
    if not isinstance(launch_environment, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in launch_environment.items()):
        raise RealProbeError("launch environment shape is invalid")
    overall_deadline = time.monotonic() + total_timeout
    started_at = time.monotonic()
    stdout = ""
    stderr = ""
    audit = {
        "schema_version": 1,
        "command_shape": {
            "product": product,
            "server": "sg8",
            "tool": "hold_until_stopped",
            "argv_count": len(command),
            "mcp_argv_count": len(mcp_command),
            "disabled_features": (
                list(CODEX_DISABLED_FEATURES) if product == "codex" else []
            ),
            "strict_config": product == "codex",
            "ephemeral": product == "codex",
            "builtins_empty": product == "claude",
            "allowed_tool": (
                "mcp__sg8__hold_until_stopped" if product == "claude" else None
            ),
            "restricted": product == "claude",
            "strict_mcp": product == "claude",
            "permission_mode": "dontAsk" if product == "claude" else None,
            "permission_prompts": "none" if product == "claude" else None,
            "max_budget_usd": "0.10" if product == "claude" else None,
            "no_session_persistence": product == "claude",
            "no_chrome": product == "claude",
            "slash_disabled": product == "claude",
            "restricted_flags": (
                ["exec", "ignore-user-config", "ignore-rules", "read-only", "json", "disable-shell"]
                if product == "codex"
                else ["print", "restricted", "strict-mcp", "no-slash", "empty-builtins", "dontAsk", "stream-json"]
            ),
        },
        "configured_deadlines": {
            "ready_seconds": ready_timeout,
            "graceful_seconds": graceful_timeout,
            "cleanup_seconds": cleanup_timeout,
            "total_run_seconds": total_timeout,
        },
        "cli": {"pid": None, "pgid": None, "returncode": None},
        "observed_pids": [],
        "signal_requests": [],
        "confirmation": {"pids": {}, "group_gone": False},
        "cleanup_outcome": "not_needed",
        "stdout": "",
        "stderr": "",
    }
    process = None
    pgid = None
    observed = []
    raw_output = raw_open(raw_evidence_path)
    pending_error = None
    try:
        process = popen_factory(
            command, cwd=workspace, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, shell=False, start_new_session=True,
            env=dict(launch_environment),
        )
        pgid = process.pid
        observed.append(process.pid)
        audit["cli"].update({"pid": process.pid, "pgid": pgid})
        audit["observed_pids"] = list(observed)
        ready_path = evidence_root / "mcp-ready.json"
        if not _wait(lambda: ready_path.exists() or process.poll() is not None, min(ready_timeout, max(0, overall_deadline - time.monotonic()))):
            raise RealProbeError("MCP ready timeout")
        if process.poll() is not None and not ready_path.exists():
            raise RealProbeError("Agent completed before hold tool")
        ready = json.loads(ready_path.read_text(encoding="utf-8"))
        if set(ready) != {"mcp_pid", "mcp_pgid", "child_pids"} or type(ready["mcp_pid"]) is not int or type(ready["mcp_pgid"]) is not int or not isinstance(ready["child_pids"], list) or any(type(pid) is not int for pid in ready["child_pids"]):
            raise RealProbeError("malformed MCP ready shape")
        observed.extend([ready["mcp_pid"], *ready["child_pids"]])
        audit["observed_pids"] = list(observed)
        if ready["mcp_pgid"] != pgid or any(getpgid(pid) != pgid for pid in observed):
            raise RealProbeError("MCP process group mismatch")
        if json.loads((evidence_root / "mcp-effect.json").read_text()) != {"effect":"hold_started"} or (evidence_root / "mcp-marker.txt").read_text() != "sg8-hold-started\n":
            raise RealProbeError("MCP evidence mismatch")
        if {item.name for item in evidence_root.iterdir()} != {"mcp-ready.json", "mcp-effect.json", "mcp-marker.txt"}:
            raise RealProbeError("unexpected evidence path")
        if {item.name for item in workspace.iterdir()} != {".git"}:
            raise RealProbeError("unexpected workspace path")
        graceful_signal = signal.SIGINT if product == "codex" else signal.SIGTERM
        if not _leader_owns(process, pgid):
            raise RealProbeError("CLI identity lost before stop")
        audit["signal_requests"].append({"layer":"graceful", "at_seconds":time.monotonic() - started_at, "deadline_expired":False})
        os.killpg(pgid, graceful_signal)
        graceful = _wait(lambda: process.poll() is not None, min(graceful_timeout, max(0, overall_deadline - time.monotonic())))
        if not graceful:
            if process.poll() is not None:
                graceful = True
            elif not _leader_owns(process, pgid):
                raise RealProbeError("CLI identity lost before force")
            else:
                audit["signal_requests"].append({"layer":"force", "at_seconds":time.monotonic() - started_at, "deadline_expired":True})
                os.killpg(pgid, signal.SIGKILL)
        try:
            stdout, stderr = process.communicate(timeout=min(cleanup_timeout, max(0.001, overall_deadline - time.monotonic())))
        except subprocess.TimeoutExpired as error:
            raise RealProbeError("CLI reap timeout") from error
        audit["cli"]["returncode"] = process.returncode
        gone = pid_gone or _gone_pid
        group_probe = group_gone or _gone_group
        if not _wait(lambda: all(gone(pid) for pid in observed), min(cleanup_timeout, max(0, overall_deadline - time.monotonic()))):
            raise RealProbeError("observed process survived")
        if not _wait(lambda: group_probe(pgid), min(cleanup_timeout, max(0, overall_deadline - time.monotonic()))):
            raise RealProbeError("process group not confirmed")
        audit["confirmation"] = {
            "pids": {str(pid): bool(gone(pid)) for pid in observed},
            "group_gone": bool(group_probe(pgid)),
        }
        parser = parse_codex_jsonl if product == "codex" else parse_claude_stream_json
        loaded, calls, terminals = parser(stdout)
        if loaded != 1:
            raise RealProbeError("MCP was not loaded exactly once")
        if calls != 1:
            raise RealProbeError("hold tool was not called exactly once")
        if terminals > 1:
            raise RealProbeError("multiple terminal events")
        if terminals:
            if not graceful:
                raise RealProbeError("terminal appeared after force")
            summary = build_graceful_stopped_summary()
        elif graceful:
            summary = build_graceful_stopped_unknown_summary()
        else:
            summary = build_force_stopped_summary()
        validate_summary(summary)
        result = {
            "schema_version": 1, "product": product, "version": version,
            "stop_layer": summary["stop_request"]["mode"],
            "terminal_present": bool(terminals), "result_state": summary["result_state"],
            "slot_state": summary["slot_state"], "retry_eligibility": summary["retry_eligibility"],
            "side_effects": summary["side_effects"], "process_group_confirmed": True,
            "event_counts": {"mcp_loaded": loaded, "hold_calls": calls, "terminal": terminals},
            "decision_escalation": summary["decision_escalation"],
        }
        if {item.name for item in workspace.iterdir()} != {".git"} or {item.name for item in evidence_root.iterdir()} != {"mcp-ready.json", "mcp-effect.json", "mcp-marker.txt"}:
            raise RealProbeError("late unexpected path effect")
        _remove_known(evidence_root)
        return result
    except BaseException as error:
        outcome = _cleanup(process, pgid, observed, cleanup_timeout)
        audit["cleanup_outcome"] = outcome
        if outcome.get("complete"):
            _remove_known(evidence_root)
        if not isinstance(error, Exception):
            pending_error = error
            try:
                error.sg8_cleanup_outcome = outcome
            except Exception:
                pass
            if not outcome.get("complete") and hasattr(error, "add_note"):
                error.add_note("Stargazing 8 cleanup incomplete")
            raise
        if isinstance(error, RealProbeError):
            pending_error = RealProbeError(str(error), outcome)
            raise pending_error from error
        if not isinstance(error, Exception):
            raise
        pending_error = RealProbeError("CLI probe failed closed", outcome)
        raise pending_error from error
    finally:
        if process is not None and stdout == "" and stderr == "":
            try:
                stdout, stderr = process.communicate(timeout=0.01)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                pass
        audit["elapsed_seconds"] = time.monotonic() - started_at
        if process is not None:
            audit["cli"]["returncode"] = process.poll()
        if observed and not audit["confirmation"]["pids"]:
            audit["confirmation"] = {
                "pids": {str(pid): bool(_gone_pid(pid)) for pid in observed},
                "group_gone": bool(_gone_group(pgid)) if pgid is not None else False,
            }
        audit["stdout"] = stdout
        audit["stderr"] = stderr
        raw_error = None
        if raw_output is not None:
            try:
                raw_output.write(json.dumps(audit, sort_keys=True) + "\n")
                raw_output.flush()
            except BaseException as error:
                raw_error = error
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
        if raw_output is not None and not raw_output.closed:
            try:
                raw_output.close()
            except BaseException as error:
                raw_error = raw_error or error
        if raw_error is not None:
            active = pending_error or sys.exc_info()[1]
            if active is not None:
                try:
                    active.sg8_raw_evidence_outcome = "write_failed"
                except Exception:
                    pass
                if hasattr(active, "add_note"):
                    active.add_note("Stargazing 8 raw evidence write failed")
            else:
                raise RealProbeError("raw evidence write failed") from raw_error


def run_fake_cli_probe(*, behavior, **kwargs):
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "SG8_FAKE_BEHAVIOR": behavior,
    }
    return _run_cli_probe(launch_environment=environment, **kwargs)


def run_real_cli_probe(*, preflight, launch_environment, total_timeout, raw_evidence_path, **kwargs):
    if raw_evidence_path is None:
        raise RealProbeError("real CLI raw evidence path is required")
    expected_preflight = {
        "product": kwargs.get("product"),
        "version": kwargs.get("version"),
        "required_flags_present": True,
    }
    if kwargs.get("product") == "codex":
        expected_preflight["codex_feature_surface_confirmed"] = True
    if preflight != expected_preflight:
        raise RealProbeError("real CLI preflight did not pass")
    if any(key.startswith("SG8_FAKE_") for key in launch_environment):
        raise RealProbeError("fake-only environment is forbidden for a real run")
    return _run_cli_probe(
        launch_environment=launch_environment,
        total_timeout=total_timeout,
        raw_evidence_path=raw_evidence_path,
        **kwargs,
    )
