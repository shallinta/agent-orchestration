#!/usr/bin/env python3
"""Role-bound throwaway STDIO MCP server for Stargazing 6."""

import argparse
import json
import sys
from pathlib import Path

from harness_state import HarnessState, ROLES


PROTOCOL_VERSION = "2025-03-26"
TOOLS = [
    {
        "name": "query_thread",
        "description": "Read the synthetic scenario and current Harness facts.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "publish_delegation",
        "description": "Publish the single synthetic investigation delegation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_role_id": {"type": "string", "minLength": 1},
                "task": {"type": "string", "minLength": 1},
            },
            "required": ["target_role_id", "task"],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_message",
        "description": "Send a directed synthetic role message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_role_id": {"type": "string", "minLength": 1},
                "body": {"type": "string", "minLength": 1},
            },
            "required": ["target_role_id", "body"],
            "additionalProperties": False,
        },
    },
]


class Server:
    def __init__(self, state, caller_role_id):
        self.state = state
        self.caller_role_id = caller_role_id

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return error(None, -32600, "Invalid Request")
        method = message.get("method")
        request_id = message.get("id")
        if "id" not in message:
            return None
        if method == "initialize":
            return result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "stargazing-006-harness", "version": "0.1"},
                },
            )
        if method == "ping":
            return result(request_id, {})
        if method == "tools/list":
            params = message.get("params", {})
            valid = (
                isinstance(params, dict)
                and set(params).issubset({"_meta", "cursor"})
                and ("_meta" not in params or isinstance(params["_meta"], dict))
                and ("cursor" not in params or isinstance(params["cursor"], str))
            )
            return result(request_id, {"tools": TOOLS}) if valid else error(
                request_id, -32602, "Invalid params"
            )
        if method != "tools/call":
            return error(request_id, -32601, "Method not found")
        params = message.get("params")
        valid = (
            isinstance(params, dict)
            and isinstance(params.get("name"), str)
            and set(params).issubset({"name", "arguments", "_meta"})
            and ("_meta" not in params or isinstance(params["_meta"], dict))
        )
        if not valid:
            return error(request_id, -32602, "Invalid params")
        name = params["name"]
        arguments = params.get("arguments", {})
        if name == "query_thread":
            tool_result = self.state.query_thread(self.caller_role_id, arguments)
        elif name == "publish_delegation":
            tool_result = self.state.publish_delegation(self.caller_role_id, arguments)
        elif name == "send_message":
            tool_result = self.state.send_message(self.caller_role_id, arguments)
        else:
            return error(request_id, -32602, "Unknown tool")
        envelope = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(tool_result, ensure_ascii=False, separators=(",", ":")),
                }
            ],
            "structuredContent": tool_result,
            "isError": tool_result["status"] == "error",
        }
        return result(request_id, envelope)


def result(request_id, value):
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def error(request_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def serve(server):
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = error(None, -32700, "Parse error")
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("--caller-role", required=True, choices=ROLES)
    args = parser.parse_args()
    scenario_path = Path(__file__).with_name("scenario.json")
    state = HarnessState(args.state, args.log, scenario_path)
    serve(Server(state, args.caller_role))


if __name__ == "__main__":
    main()
