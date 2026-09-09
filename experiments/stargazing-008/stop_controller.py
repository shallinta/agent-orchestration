"""Bounded POSIX process-group controller for the Stargazing 8 probe."""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
import uuid
from pathlib import Path

from contracts import (
    build_force_stopped_summary,
    build_graceful_stopped_summary,
    build_graceful_stopped_unknown_summary,
    validate_summary,
)


_ARTIFACT_ALLOWLIST = {
    "dispatch.jsonl", "ready.json", "effect.json", "marker.txt", "terminal.json",
    ".ready.json.tmp", ".effect.json.tmp", ".terminal.json.tmp",
}


@dataclass(frozen=True)
class StopReceipt:
    execution_identity: str
    summary: dict
    observed_pids: tuple
    control_token: object = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class CompletionReceipt:
    execution_identity: str
    terminal_state: str
    control_token: object = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ManagedWorker:
    execution_identity: str
    process: object
    pgid: int
    observed_pids: tuple
    child_pgid: int
    workspace: Path
    control_token: object = field(repr=False, compare=False)


def start_managed_worker(
    *, worker_path, workspace, behavior="ignore", ready_timeout=10.0,
    cleanup_timeout=1.0, popen_factory=subprocess.Popen,
):
    workspace = Path(workspace)
    if not workspace.exists() or not workspace.is_dir() or any(workspace.iterdir()):
        raise ProbeError("workspace must be an existing empty directory")
    process = None
    pgid = None
    observed = []
    try:
        (workspace / "dispatch.jsonl").write_text(
            json.dumps(
                {"attempt": "fixed-attempt", "event": "dispatch"}, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        process = popen_factory(
            [sys.executable, str(Path(worker_path)), "--workspace", str(workspace), "--behavior", behavior],
            shell=False, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pgid = process.pid
        observed.append(process.pid)
        ready_path = workspace / "ready.json"
        if not _wait_until(lambda: ready_path.exists() or process.poll() is not None, time.monotonic() + ready_timeout):
            raise ProbeError("ready evidence was not observed")
        ready = _read_ready(ready_path)
        observed.append(ready["child_pid"])
        if ready["leader_pid"] != process.pid or ready["pgid"] != pgid:
            raise ProbeError("PID or PGID evidence does not match the controlled group")
        child_pgid = os.getpgid(ready["child_pid"])
        if child_pgid != pgid:
            raise ProbeError("recorded child is outside the controlled group")
        effect = json.loads((workspace / "effect.json").read_text(encoding="utf-8"))
        marker = (workspace / "marker.txt").read_text(encoding="utf-8")
        if effect != {"effect": "fixed_harness_effect"} or marker != "stargazing-8-fixed-marker\n":
            raise ProbeError("effect evidence has an unknown shape")
        return ManagedWorker(
            uuid.uuid4().hex,
            process,
            pgid,
            tuple(observed),
            child_pgid,
            workspace,
            object(),
        )
    except BaseException as error:
        _raise_after_cleanup(
            error, process, pgid, observed, workspace, cleanup_timeout,
            "managed worker start failed",
        )


def _confirm_managed_stopped(handle, timeout):
    handle.process.wait(timeout=timeout)
    if not _wait_until(lambda: all(_pid_gone(pid) for pid in handle.observed_pids), time.monotonic() + timeout):
        raise ProbeError("a recorded PID survived stop")
    if not _wait_until(lambda: _group_gone(handle.pgid), time.monotonic() + timeout):
        raise ProbeError("controlled process group stop could not be confirmed")


def stop_managed_worker(handle, *, graceful_timeout=0.05, cleanup_timeout=1.0):
    if not isinstance(handle, ManagedWorker) or not _leader_owns_group(handle.process, handle.pgid):
        raise ProbeError("managed execution identity is not active")
    try:
        os.killpg(handle.pgid, signal.SIGTERM)
        graceful = _wait_until(
            lambda: handle.process.poll() is not None,
            time.monotonic() + graceful_timeout,
        )
        if not graceful:
            if not _leader_owns_group(handle.process, handle.pgid):
                raise ProbeError("managed execution identity was lost before force stop")
            os.killpg(handle.pgid, signal.SIGKILL)
        _confirm_managed_stopped(handle, cleanup_timeout)
        terminal_path = handle.workspace / "terminal.json"
        if graceful and terminal_path.exists():
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            summary = (
                build_graceful_stopped_summary()
                if terminal
                == {"state": "cancelled", "evidence": "synthetic_worker_terminal"}
                else None
            )
        else:
            summary = (
                build_graceful_stopped_unknown_summary()
                if graceful
                else build_force_stopped_summary()
            )
        if summary is None:
            raise ProbeError("synthetic terminal has an unknown shape")
        validate_summary(summary)
        if _remove_artifacts(handle.workspace) != "completed":
            raise ProbeError("workspace contains unexpected artifacts")
        return StopReceipt(
            handle.execution_identity,
            summary,
            handle.observed_pids,
            handle.control_token,
        )
    except BaseException as error:
        _raise_after_cleanup(
            error, handle.process, handle.pgid, handle.observed_pids,
            handle.workspace, cleanup_timeout, "managed worker stop failed",
        )


def complete_managed_worker(handle, *, cleanup_timeout=1.0):
    if not isinstance(handle, ManagedWorker) or not _leader_owns_group(handle.process, handle.pgid):
        raise ProbeError("managed execution identity is not active")
    try:
        os.killpg(handle.pgid, signal.SIGUSR1)
        _confirm_managed_stopped(handle, cleanup_timeout)
        terminal = json.loads(
            (handle.workspace / "terminal.json").read_text(encoding="utf-8")
        )
        if terminal != {"state": "succeeded", "evidence": "synthetic_worker_terminal"}:
            raise ProbeError("synthetic completion has an unknown shape")
        if _remove_artifacts(handle.workspace) != "completed":
            raise ProbeError("workspace contains unexpected artifacts")
        return CompletionReceipt(
            handle.execution_identity, "succeeded", handle.control_token
        )
    except BaseException as error:
        _raise_after_cleanup(
            error, handle.process, handle.pgid, handle.observed_pids,
            handle.workspace, cleanup_timeout, "managed worker completion failed",
        )


class ProbeError(RuntimeError):
    def __init__(self, message, observed_pids=(), cleanup_outcome=None):
        super().__init__(message)
        self.observed_pids = tuple(observed_pids)
        self.cleanup_outcome = cleanup_outcome


def _pid_gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _group_gone(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


def _wait_until(predicate, deadline):
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _read_ready(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProbeError("ready evidence is missing or malformed") from error
    if set(value) != {"leader_pid", "child_pid", "pgid"}:
        raise ProbeError("ready evidence has an unknown shape")
    if any(type(value[field]) is not int or value[field] <= 0 for field in value):
        raise ProbeError("PID or PGID evidence is malformed")
    return value


def _remove_artifacts(workspace):
    incomplete = 0
    for path in workspace.iterdir():
        if path.name in _ARTIFACT_ALLOWLIST and path.is_file() and not path.is_symlink():
            path.unlink(missing_ok=True)
        else:
            incomplete += 1
    return "completed" if incomplete == 0 else "incomplete"


def _leader_owns_group(process, pgid, getpgid=os.getpgid):
    if process.poll() is not None:
        return False
    try:
        return getpgid(process.pid) == pgid
    except (ProcessLookupError, PermissionError):
        return False


def _hard_cleanup(process, pgid, observed_pids, timeout, operations=None):
    operations = operations or {}
    kill_group = operations.get("kill_group", os.killpg)
    wait_leader = operations.get("wait_leader", lambda target, seconds: target.wait(timeout=seconds))
    pid_gone = operations.get("pid_gone", _pid_gone)
    group_gone = operations.get("group_gone", _group_gone)
    leader_owns_group = operations.get("leader_owns_group", _leader_owns_group)
    outcome = {
        "group_kill": "not_needed",
        "leader_reap": "not_attempted",
        "pid_signal": "not_sent",
        "pid_observation": "complete",
        "remaining_pid_count": 0,
        "group_state": "unknown",
        "complete": False,
        "emergency_cleanup": "not_needed",
        "final_safety_cleanup": "not_needed",
    }
    if leader_owns_group(process, pgid):
        try:
            kill_group(pgid, signal.SIGKILL)
            outcome["group_kill"] = "sent"
        except ProcessLookupError:
            outcome["group_kill"] = "not_found"
        except PermissionError:
            outcome["group_kill"] = "permission_denied"
        except BaseException:
            outcome["group_kill"] = "operation_failed"
    elif process.poll() is None:
        outcome["group_kill"] = "identity_unconfirmed"
    else:
        outcome["group_kill"] = "identity_lost"
    try:
        wait_leader(process, timeout)
        outcome["leader_reap"] = "reaped"
    except subprocess.TimeoutExpired:
        outcome["leader_reap"] = "timeout"
    except BaseException:
        outcome["leader_reap"] = "operation_failed"
    if outcome["leader_reap"] == "timeout":
        try:
            wait_leader(process, timeout)
            outcome["leader_reap"] = "reaped"
        except subprocess.TimeoutExpired:
            pass
        except BaseException:
            outcome["leader_reap"] = "operation_failed"
    try:
        _wait_until(lambda: all(pid_gone(pid) for pid in observed_pids), time.monotonic() + timeout)
        remaining = sum(not pid_gone(pid) for pid in observed_pids)
    except BaseException:
        outcome["pid_observation"] = "operation_failed"
        remaining = len(observed_pids)
    outcome["remaining_pid_count"] = remaining
    try:
        outcome["group_state"] = "gone" if group_gone(pgid) else "present_or_unconfirmed"
    except BaseException:
        outcome["group_state"] = "observation_failed"
    outcome["complete"] = (
        outcome["leader_reap"] == "reaped"
        and remaining == 0
        and outcome["group_state"] == "gone"
    )
    return outcome


def _emergency_cleanup(process, pgid, observed_pids, timeout, operations=None):
    operations = operations or {}
    kill_group = operations.get("kill_group", os.killpg)
    wait_leader = operations.get("wait_leader", lambda target, seconds: target.wait(timeout=seconds))
    pid_gone = operations.get("pid_gone", _pid_gone)
    group_gone = operations.get("group_gone", _group_gone)
    leader_owns_group = operations.get("leader_owns_group", _leader_owns_group)
    outcome = {
        "group_kill": "not_needed",
        "leader_reap": "not_attempted",
        "remaining_pid_count": len(observed_pids),
        "group_state": "unknown",
        "complete": False,
    }
    if leader_owns_group(process, pgid):
        try:
            kill_group(pgid, signal.SIGKILL)
            outcome["group_kill"] = "sent"
        except ProcessLookupError:
            outcome["group_kill"] = "not_found"
        except PermissionError:
            outcome["group_kill"] = "permission_denied"
        except BaseException:
            outcome["group_kill"] = "operation_failed"
    elif process.poll() is None:
        outcome["group_kill"] = "identity_unconfirmed"
    else:
        outcome["group_kill"] = "identity_lost"
    try:
        wait_leader(process, timeout)
        outcome["leader_reap"] = "reaped"
    except subprocess.TimeoutExpired:
        outcome["leader_reap"] = "timeout"
    except BaseException:
        outcome["leader_reap"] = "operation_failed"
    try:
        _wait_until(lambda: all(pid_gone(pid) for pid in observed_pids), time.monotonic() + timeout)
        outcome["remaining_pid_count"] = sum(not pid_gone(pid) for pid in observed_pids)
    except BaseException:
        outcome["remaining_pid_count"] = len(observed_pids)
    try:
        outcome["group_state"] = "gone" if group_gone(pgid) else "present_or_unconfirmed"
    except BaseException:
        outcome["group_state"] = "observation_failed"
    outcome["complete"] = (
        outcome["leader_reap"] == "reaped"
        and outcome["remaining_pid_count"] == 0
        and outcome["group_state"] == "gone"
    )
    return outcome


def _final_safety_cleanup(process, pgid, observed_pids, timeout, operations=None):
    operations = operations or {}
    kill_group = operations.get("kill_group", os.killpg)
    leader_owns_group = operations.get("leader_owns_group", _leader_owns_group)
    outcome = {"group_kill": "not_needed", "complete": False}
    try:
        if leader_owns_group(process, pgid):
            try:
                kill_group(pgid, signal.SIGKILL)
                outcome["group_kill"] = "sent"
            except ProcessLookupError:
                outcome["group_kill"] = "not_found"
            except PermissionError:
                outcome["group_kill"] = "permission_denied"
            except BaseException:
                outcome["group_kill"] = "operation_failed"
        elif process.poll() is None:
            outcome["group_kill"] = "identity_unconfirmed"
        else:
            outcome["group_kill"] = "identity_lost"
        process.wait(timeout=timeout)
        outcome["complete"] = _wait_until(
            lambda: all(_pid_gone(pid) for pid in observed_pids) and _group_gone(pgid),
            time.monotonic() + timeout,
        )
        return outcome
    except BaseException:
        outcome["complete"] = False
        return outcome


def _cleanup_failure(
    process, pgid, observed_pids, workspace, timeout,
    cleanup_ops=None, emergency_ops=None, final_ops=None,
):
    if process is None:
        outcome = {
            "group_kill": "not_needed",
            "leader_reap": "not_started",
            "pid_signal": "not_sent",
            "pid_observation": "complete",
            "remaining_pid_count": 0,
            "group_state": "not_started",
            "complete": True,
            "emergency_cleanup": "not_needed",
            "final_safety_cleanup": "not_needed",
        }
    else:
        try:
            outcome = _hard_cleanup(
                process, pgid, observed_pids, timeout, cleanup_ops
            )
        except BaseException:
            outcome = {
                "group_kill": "operation_failed",
                "leader_reap": "unknown",
                "pid_signal": "not_sent",
                "pid_observation": "unknown",
                "remaining_pid_count": len(observed_pids),
                "group_state": "unknown",
                "complete": False,
                "emergency_cleanup": "not_needed",
                "final_safety_cleanup": "not_needed",
            }
        if not outcome["complete"]:
            try:
                outcome["emergency_cleanup"] = _emergency_cleanup(
                    process, pgid, observed_pids, timeout, emergency_ops
                )
            except BaseException:
                outcome["emergency_cleanup"] = {
                    "group_kill": "operation_failed",
                    "leader_reap": "unknown",
                    "remaining_pid_count": len(observed_pids),
                    "group_state": "unknown",
                    "complete": False,
                }
            if not outcome["emergency_cleanup"]["complete"]:
                outcome["final_safety_cleanup"] = _final_safety_cleanup(
                    process, pgid, observed_pids, timeout, final_ops
                )
    try:
        artifact_cleanup = _remove_artifacts(workspace)
    except BaseException:
        artifact_cleanup = "incomplete"
    outcome["artifact_cleanup"] = artifact_cleanup
    if artifact_cleanup != "completed":
        outcome["complete"] = False
    return outcome


def _raise_after_cleanup(
    error, process, pgid, observed_pids, workspace, timeout, normal_message,
    cleanup_ops=None, emergency_ops=None, final_ops=None,
):
    outcome = _cleanup_failure(
        process, pgid, observed_pids, workspace, timeout,
        cleanup_ops, emergency_ops, final_ops,
    )
    if not isinstance(error, Exception):
        if not outcome["complete"]:
            error.add_note(
                "Stargazing 8 cleanup incomplete: "
                + json.dumps(outcome, sort_keys=True)
            )
        try:
            error.sg8_cleanup_outcome = outcome
        except Exception:
            pass
        raise error
    if isinstance(error, ProbeError):
        raise ProbeError(str(error), observed_pids, outcome) from error
    raise ProbeError(normal_message, observed_pids, outcome) from error


def run_stop_probe(
    *, worker_path, workspace, behavior, ready_timeout, graceful_timeout,
    cleanup_timeout, group_gone=None, pid_gone=None, checkpoint=None,
    cleanup_ops=None, emergency_ops=None, final_ops=None,
    popen_factory=subprocess.Popen,
):
    workspace = Path(workspace)
    worker_path = Path(worker_path)
    if not workspace.exists() or not workspace.is_dir() or any(workspace.iterdir()):
        raise ProbeError(
            "workspace must be an existing empty directory",
            cleanup_outcome={"workspace": "rejected", "complete": False},
        )
    dispatch_path = workspace / "dispatch.jsonl"
    dispatch_path.write_text(
        json.dumps({"attempt": "fixed-attempt", "event": "dispatch"}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    process = popen_factory(
        [sys.executable, str(worker_path), "--workspace", str(workspace), "--behavior", behavior],
        shell=False,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pgid = process.pid
    observed_pids = [process.pid]
    ready_path = workspace / "ready.json"
    force_requested_at = None
    try:
        ready_deadline = time.monotonic() + ready_timeout
        if not _wait_until(lambda: ready_path.exists() or process.poll() is not None, ready_deadline):
            raise ProbeError("ready evidence was not observed")
        ready = _read_ready(ready_path)
        observed_pids.append(ready["child_pid"])
        if ready["leader_pid"] != process.pid or ready["pgid"] != pgid:
            raise ProbeError("PID or PGID evidence does not match the controlled group")
        try:
            child_pgid = os.getpgid(ready["child_pid"])
        except ProcessLookupError as error:
            raise ProbeError("recorded child disappeared before validation") from error
        if child_pgid != pgid:
            raise ProbeError("recorded child is outside the controlled group")

        try:
            effect = json.loads((workspace / "effect.json").read_text(encoding="utf-8"))
            marker = (workspace / "marker.txt").read_text(encoding="utf-8")
        except (OSError, json.JSONDecodeError) as error:
            raise ProbeError("effect evidence is missing or malformed") from error
        if effect != {"effect": "fixed_harness_effect"} or marker != "stargazing-8-fixed-marker\n":
            raise ProbeError("effect evidence has an unknown shape")

        observed_facts = {
            "leader_pid": process.pid,
            "child_pid": ready["child_pid"],
            "pgid": pgid,
        }
        if checkpoint is not None:
            checkpoint("after_ready", observed_facts.copy())

        graceful_requested_at = time.monotonic()
        os.killpg(pgid, signal.SIGTERM)
        signals = ["graceful"]
        stopped_gracefully = _wait_until(
            lambda: process.poll() is not None,
            graceful_requested_at + graceful_timeout,
        )
        if not stopped_gracefully:
            force_requested_at = time.monotonic()
            os.killpg(pgid, signal.SIGKILL)
            signals.append("force")
            if checkpoint is not None:
                checkpoint("after_force", observed_facts.copy())

        try:
            process.wait(timeout=cleanup_timeout)
        except subprocess.TimeoutExpired as error:
            raise ProbeError("controlled leader could not be reaped") from error
        if checkpoint is not None:
            checkpoint("after_reap", observed_facts.copy())
        pid_probe = pid_gone or _pid_gone
        if not _wait_until(
            lambda: all(pid_probe(pid) for pid in observed_pids),
            time.monotonic() + cleanup_timeout,
        ):
            raise ProbeError("a recorded PID survived stop")
        group_probe = group_gone or _group_gone
        if not _wait_until(lambda: group_probe(pgid), time.monotonic() + cleanup_timeout):
            raise ProbeError("controlled process group stop could not be confirmed")

        if stopped_gracefully:
            try:
                terminal = json.loads((workspace / "terminal.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ProbeError("graceful worker did not emit a reliable terminal") from error
            if terminal != {"state": "cancelled", "evidence": "synthetic_worker_terminal"}:
                raise ProbeError("synthetic terminal has an unknown shape")
            summary = build_graceful_stopped_summary()
        else:
            summary = build_force_stopped_summary()
        validate_summary(summary)
        dispatch_ledger = [
            json.loads(line)
            for line in dispatch_path.read_text(encoding="utf-8").splitlines()
        ]
        if dispatch_ledger != [{"attempt": "fixed-attempt", "event": "dispatch"}]:
            raise ProbeError("dispatch ledger has an unknown shape")
        result = {
            "dispatch_count": len(dispatch_ledger), "redispatch_count": 0,
            "dispatch_ledger": dispatch_ledger, "signals": signals,
            "leader_pid": process.pid, "pgid": pgid,
            "observed_child_pgid": child_pgid, "all_recorded_pids_gone": True,
            "graceful_requested_at": graceful_requested_at,
            "force_requested_at": force_requested_at, "summary": summary,
        }
        artifact_cleanup = _remove_artifacts(workspace)
        if artifact_cleanup != "completed":
            raise ProbeError("workspace contains unexpected artifacts")
        return result
    except BaseException as error:
        _raise_after_cleanup(
            error, process, pgid, observed_pids, workspace, cleanup_timeout,
            "probe failed closed", cleanup_ops, emergency_ops, final_ops,
        )
