#!/usr/bin/env python3
"""Throwaway driver for a post-turn structured Harness capability request."""

import argparse
import json
import sys
from pathlib import Path

from harness_server import FakeHarness, KNOWN_TOOL_NAMES


EXECUTION_ATTEMPTS = {"sg5-structured-attempt-1": "structured-probe-caller"}
SCHEMA_PATH = Path(__file__).with_name("structured_request.schema.json")


def valid_request(request, schema):
    tool_schema = schema["properties"]["tool"]
    arguments_schema = schema["properties"]["arguments"]
    return (
        isinstance(request, dict)
        and set(request) == set(schema["required"])
        and isinstance(request.get("tool"), str)
        and request["tool"] in tool_schema["enum"]
        and request["tool"] in KNOWN_TOOL_NAMES
        and isinstance(request.get("arguments"), dict)
        and set(request["arguments"]) == set(arguments_schema["required"])
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True)
    parser.add_argument("--execution-attempt", required=True)
    args = parser.parse_args()

    caller_role_id = EXECUTION_ATTEMPTS.get(args.execution_attempt)
    if caller_role_id is None:
        result = {"status": "error", "error": {"code": "unauthorized_attempt"}}
        sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
        return 3

    harness = FakeHarness(args.log, caller_role_id=caller_role_id)
    try:
        request = json.loads(sys.stdin.read())
        schema = json.loads(SCHEMA_PATH.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        result = harness.call_tool(None, None)
    else:
        if valid_request(request, schema):
            result = harness.call_tool(request["tool"], request["arguments"])
        else:
            result = harness.call_tool(None, None)

    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
