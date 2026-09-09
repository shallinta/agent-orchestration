#!/usr/bin/env python3
"""One-tool synthetic STDIO MCP server for the bounded Stargazing 8 probe."""

import argparse
import json
import os
import sys
import time
from pathlib import Path


SUPPORTED_PROTOCOLS = {"2025-03-26", "2025-06-18"}


def _atomic_json(path, value):
    temporary = path.with_name("." + path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def tools_list_result():
    return {
        "tools": [{
            "name": "hold_until_stopped",
            "description": "Start one fixed artificial hold operation.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }]
    }


def record_hold_started(evidence_root):
    evidence_root = Path(evidence_root)
    fact = {"mcp_pid": os.getpid(), "mcp_pgid": os.getpgrp(), "child_pids": []}
    _atomic_json(evidence_root / "mcp-effect.json", {"effect": "hold_started"})
    (evidence_root / "mcp-marker.txt").write_text("sg8-hold-started\n", encoding="utf-8")
    _atomic_json(evidence_root / "mcp-ready.json", fact)
    return fact


def validate_hold_call(arguments, evidence_root):
    if arguments != {}:
        raise ValueError("hold_until_stopped accepts no arguments")
    return record_hold_started(evidence_root)


def _reply(request_id, result):
    print(json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}, sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--role-id", required=True)
    arguments = parser.parse_args()
    if arguments.role_id != "host":
        raise SystemExit(2)
    evidence_root = Path(arguments.evidence_root)
    if not evidence_root.is_dir():
        raise SystemExit(2)
    for line in sys.stdin:
        request = json.loads(line)
        method = request.get("method")
        if method == "initialize":
            protocol = request.get("params", {}).get("protocolVersion")
            if protocol not in SUPPORTED_PROTOCOLS:
                print(json.dumps({"jsonrpc":"2.0", "id":request.get("id"), "error":{"code":-32602, "message":"unsupported protocol"}}, sort_keys=True), flush=True)
                continue
            _reply(request.get("id"), {"protocolVersion": protocol, "capabilities": {"tools": {}}, "serverInfo": {"name": "sg8", "version": "fixture"}})
        elif method == "tools/list":
            _reply(request.get("id"), tools_list_result())
        elif method == "tools/call" and request.get("params", {}).get("name") == "hold_until_stopped":
            validate_hold_call(request.get("params", {}).get("arguments", {}), evidence_root)
            while True:
                time.sleep(30)
        elif request.get("id") is not None:
            print(json.dumps({"jsonrpc":"2.0", "id":request["id"], "error":{"code":-32601, "message":"unsupported"}}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
