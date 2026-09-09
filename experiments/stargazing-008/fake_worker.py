"""Fixed artificial worker for the Stargazing 8 process-control probe."""

import argparse
import json
import os
import signal
import time
from pathlib import Path


FIXED_MARKER = "stargazing-8-fixed-marker\n"
FIXED_EFFECT = {"effect": "fixed_harness_effect"}


def write_json(path, value):
    temporary = path.with_name("." + path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def start_child(ignore_graceful):
    read_fd, write_fd = os.pipe()
    child_pid = os.fork()
    if child_pid == 0:
        os.close(read_fd)
        signal.signal(
            signal.SIGTERM,
            signal.SIG_IGN if ignore_graceful else signal.SIG_DFL,
        )
        os.write(write_fd, b"1")
        os.close(write_fd)
        while True:
            time.sleep(30)
    os.close(write_fd)
    if os.read(read_fd, 1) != b"1":
        raise RuntimeError("fixed child failed before ready")
    os.close(read_fd)
    return child_pid


def stop_child(child_pid):
    try:
        os.kill(child_pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        waited, _status = os.waitpid(child_pid, os.WNOHANG)
        if waited == child_pid:
            return
        time.sleep(0.005)
    try:
        os.kill(child_pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    os.waitpid(child_pid, 0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument(
        "--behavior",
        required=True,
        choices=(
            "graceful",
            "ignore",
            "missing_ready",
            "malformed_ready",
            "wrong_pgid",
            "missing_effect",
        ),
    )
    arguments = parser.parse_args()
    workspace = Path(arguments.workspace)
    marker = workspace / "marker.txt"
    effect = workspace / "effect.json"
    ready = workspace / "ready.json"
    terminal = workspace / "terminal.json"
    marker.write_text(FIXED_MARKER, encoding="utf-8")
    if arguments.behavior != "missing_effect":
        write_json(effect, FIXED_EFFECT)

    ignores_graceful = arguments.behavior in (
        "ignore", "missing_ready", "missing_effect"
    )
    child_pid = start_child(ignores_graceful)

    def finish(state):
        stop_child(child_pid)
        write_json(terminal, {"state": state, "evidence": "synthetic_worker_terminal"})
        raise SystemExit(0)

    def graceful_stop(_signum, _frame):
        finish("cancelled")

    def synthetic_complete(_signum, _frame):
        finish("succeeded")

    if ignores_graceful:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    else:
        signal.signal(signal.SIGTERM, graceful_stop)
    signal.signal(signal.SIGUSR1, synthetic_complete)

    if arguments.behavior == "malformed_ready":
        write_json(ready, {"leader_pid": "not-an-integer", "child_pid": child_pid, "pgid": os.getpgrp()})
    elif arguments.behavior != "missing_ready":
        reported_pgid = os.getpgrp() + 1 if arguments.behavior == "wrong_pgid" else os.getpgrp()
        write_json(
            ready,
            {"leader_pid": os.getpid(), "child_pid": child_pid, "pgid": reported_pgid},
        )

    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
