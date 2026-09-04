#!/usr/bin/env python3
"""Assemble one disposable Stargazing 6 run and emit a redacted summary."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_runners import ClaudeRunner, CodexRunner
from controller import Controller
from harness_state import HarnessState


HERE = Path(__file__).resolve().parent
HOST = "host-codex"
INVESTIGATOR = "investigator-claude"
TOTAL_LIMITS = {"success": 1800, "start-failure": 600}


def _git_workspace(root, name):
    workspace = root / name
    workspace.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return workspace


def _mcp_command(state_path, log_path, role_id):
    return [
        sys.executable,
        str(HERE / "harness_mcp.py"),
        "--state",
        str(state_path),
        "--log",
        str(log_path),
        "--caller-role",
        role_id,
    ]


def _safe_enum(value, allowed, fallback="invalid"):
    return value if value in allowed else fallback


def _sanitized_summary(result, mode, scenario_digest):
    turns = []
    for turn in getattr(result, "turns", ()):
        turns.append(
            {
                "role_id": _safe_enum(
                    getattr(turn, "role_id", None), {HOST, INVESTIGATOR}
                ),
                "mode": _safe_enum(getattr(turn, "mode", None), {"start", "resume"}),
                "session_present": bool(getattr(turn, "session_id", None)),
            }
        )
    deliveries = []
    for delivery in getattr(result, "deliveries", ()):
        send_digest = getattr(delivery, "send_digest", None)
        payload_digest = getattr(delivery, "payload_digest", None)
        deliveries.append(
            {
                "fact_kind": _safe_enum(
                    getattr(delivery, "fact_kind", None), {"delegation", "message"}
                ),
                "sender_role_id": _safe_enum(
                    getattr(delivery, "sender_role_id", None), {HOST, INVESTIGATOR}
                ),
                "target_role_id": _safe_enum(
                    getattr(delivery, "target_role_id", None), {HOST, INVESTIGATOR}
                ),
                "send_digest": send_digest if isinstance(send_digest, str) else None,
                "payload_digest": payload_digest if isinstance(payload_digest, str) else None,
            }
        )
    fault = getattr(result, "call_fault", None)
    return {
        "schema": "stargazing-006-run-summary-v1",
        "mode": mode,
        "outcome": "completed",
        "distinct_role_sessions": len(set(getattr(result, "sessions", {}).values()))
        == len(getattr(result, "sessions", {})),
        "scenario_digest": scenario_digest,
        "turn_count": len(turns),
        "turns": turns,
        "delivery_count": len(deliveries),
        "deliveries": deliveries,
        "call_fault_present": isinstance(fault, dict),
    }


def _write_summary(path, summary):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n",
        encoding="utf-8",
    )
    return summary


def _review_destination(path):
    destination = Path(path)
    repository = HERE.parents[1]
    resolved = destination.resolve(strict=False)
    if not destination.is_absolute() or resolved == repository or repository in resolved.parents:
        raise ValueError("review bundle path must be absolute and outside the repository")
    if not destination.parent.is_dir():
        raise ValueError("review bundle parent must already exist")
    return destination


def _write_review_bundle(path, result, scenario_digest):
    destination = _review_destination(path)
    bundle = {
        "schema": "stargazing-006-temporary-review-v1",
        "notice": (
            "unredacted; may contain sensitive Agent-authored text; local short-lived "
            "review only; never share or commit; securely delete immediately after review"
        ),
        "scenario_digest": scenario_digest,
        "outcome": _safe_enum(
            getattr(result, "outcome", None), {"success", "start_failed"}
        ),
        "turns": [
            {
                "turn": index,
                "role_id": _safe_enum(
                    getattr(turn, "role_id", None), {HOST, INVESTIGATOR}
                ),
                "mode": _safe_enum(getattr(turn, "mode", None), {"start", "resume"}),
                "final_text": getattr(turn, "final_result", None),
            }
            for index, turn in enumerate(getattr(result, "turns", ()), 1)
        ],
        "facts": [
            {
                "sequence": index,
                "fact_kind": _safe_enum(
                    getattr(item, "fact_kind", None), {"delegation", "message"}
                ),
                "fact_id": getattr(item, "fact_id", None),
                "sender_role_id": _safe_enum(
                    getattr(item, "sender_role_id", None), {HOST, INVESTIGATOR}
                ),
                "target_role_id": _safe_enum(
                    getattr(item, "target_role_id", None), {HOST, INVESTIGATOR}
                ),
                "body": getattr(item, "payload", None),
            }
            for index, item in enumerate(getattr(result, "deliveries", ()), 1)
        ],
        "final_host_text": getattr(result, "final_result", None),
    }
    payload = (
        json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as review_file:
            descriptor = -1
            review_file.write(payload)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return bundle


def run_probe(
    *,
    mode,
    summary_path,
    review_bundle_path,
    codex_executable="codex",
    claude_executable="claude",
    controller_class=Controller,
):
    if mode not in TOTAL_LIMITS:
        raise ValueError("mode must be success or start-failure")
    _review_destination(review_bundle_path)

    try:
        with tempfile.TemporaryDirectory(prefix="stargazing-006-") as temp_dir:
            root = Path(temp_dir)
            state_path = root / "thread-state.json"
            log_path = root / "harness-facts.jsonl"
            state = HarnessState(state_path, log_path, HERE / "scenario.json")
            workspaces = {
                HOST: _git_workspace(root, "host-workspace"),
                INVESTIGATOR: _git_workspace(root, "investigator-workspace"),
            }
            mcp_commands = {
                role: _mcp_command(state_path, log_path, role)
                for role in (HOST, INVESTIGATOR)
            }
            investigator_executable = claude_executable
            if mode == "start-failure":
                investigator_executable = str(root / "missing-claude-executable")
            runners = {
                HOST: CodexRunner(codex_executable),
                INVESTIGATOR: ClaudeRunner(investigator_executable),
            }
            controller = controller_class(
                state=state,
                runners=runners,
                workspaces=workspaces,
                mcp_commands=mcp_commands,
                evidence_dirs={
                    HOST: root / "host-evidence",
                    INVESTIGATOR: root / "investigator-evidence",
                },
                timeout_seconds=300,
                max_turns=7,
                success_deadline_seconds=TOTAL_LIMITS["success"],
                failure_deadline_seconds=TOTAL_LIMITS["start-failure"],
            )
            result = (
                controller.run_success()
                if mode == "success"
                else controller.run_start_failure()
            )
            if getattr(result, "outcome", None) is None:
                result.outcome = "success" if mode == "success" else "start_failed"
            summary = _sanitized_summary(result, mode, state.scenario_digest)
            _write_review_bundle(review_bundle_path, result, state.scenario_digest)
            return _write_summary(summary_path, summary)
    except Exception as exc:
        _write_summary(
            summary_path,
            {
                "schema": "stargazing-006-run-summary-v1",
                "mode": mode,
                "outcome": "stopped",
                "error_kind": _safe_enum(
                    type(exc).__name__,
                    {
                        "ControllerError",
                        "FileNotFoundError",
                        "TimeoutError",
                        "UnexpectedToolCallError",
                    },
                ),
            },
        )
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=tuple(TOTAL_LIMITS), required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--review-bundle", required=True)
    parser.add_argument("--codex-executable", default="codex")
    parser.add_argument("--claude-executable", default="claude")
    args = parser.parse_args(argv)
    summary = run_probe(
        mode=args.mode,
        summary_path=args.summary,
        review_bundle_path=args.review_bundle,
        codex_executable=args.codex_executable,
        claude_executable=args.claude_executable,
    )
    sys.stdout.write(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
