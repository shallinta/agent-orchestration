#!/usr/bin/env python3
"""Throwaway in-memory Harness and newline-delimited JSON-RPC MCP surface."""

import argparse
import datetime
import json
import sys
import uuid
from pathlib import Path


PROTOCOL_VERSION = "2025-03-26"
CALLER_ROLE_ID = "probe-caller"
IDENTITY_FIELDS = {"caller_role_id", "caller", "role_id"}
KNOWN_TOOL_NAMES = {"query_thread", "send_message", "publish_delegation"}


TOOLS = [
    {
        "name": "query_thread",
        "description": "Read the fixed synthetic thread summary.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "send_message",
        "description": "Write a synthetic message to an existing role.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_role_id": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1},
            },
            "required": ["target_role_id", "message"],
            "additionalProperties": False,
        },
    },
    {
        "name": "publish_delegation",
        "description": "Write a synthetic delegation when the fixed caller is allowed.",
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
]


class FakeHarness:
    """A deliberately small, process-local set of synthetic Harness facts."""

    def __init__(self, log_path, caller_role_id=CALLER_ROLE_ID):
        self.log_path = Path(log_path)
        self.caller_role_id = caller_role_id
        self.roles = {"allowed-worker", "forbidden-worker"}
        self.delegation_targets = {"allowed-worker"}
        self.messages = []
        self.delegations = []

    def call_tool(self, tool_name, arguments):
        request_id = self._new_request_id()

        validation_error = self._validate(tool_name, arguments)
        if validation_error is not None:
            result = self._error(request_id, "invalid_params", validation_error)
            self._log(request_id, tool_name, "invalid_params", {})
            return result

        if tool_name == "query_thread":
            result = {
                "request_id": request_id,
                "status": "ok",
                "thread": self._thread_summary(),
            }
            self._log(
                request_id,
                tool_name,
                "ok",
                {
                    "message_count": len(self.messages),
                    "delegation_count": len(self.delegations),
                },
            )
            return result

        target_role_id = arguments["target_role_id"]
        if target_role_id not in self.roles:
            result = self._error(request_id, "not_found", "target role does not exist")
            self._log(
                request_id,
                tool_name,
                "not_found",
                {"target_exists": False, "target_authorized": False},
            )
            return result

        if tool_name == "publish_delegation" and target_role_id not in self.delegation_targets:
            result = self._error(
                request_id,
                "forbidden",
                "fixed caller may not publish a delegation to this role",
            )
            self._log(
                request_id,
                tool_name,
                "forbidden",
                {"target_exists": True, "target_authorized": False},
            )
            return result

        if tool_name == "send_message":
            message_id = "message-" + str(len(self.messages) + 1)
            record = {
                "message_id": message_id,
                "attributed_caller_role_id": self.caller_role_id,
                "target_role_id": target_role_id,
                "message": arguments["message"],
            }
            self.messages.append(record)
            result = {
                "request_id": request_id,
                "status": "ok",
                "message": {
                    key: value for key, value in record.items() if key != "message"
                },
            }
            self._log(
                request_id,
                tool_name,
                "ok",
                {
                    "message_id": message_id,
                    "target_exists": True,
                    "target_authorized": True,
                    "message_length": len(arguments["message"]),
                },
            )
            return result

        delegation_id = "delegation-" + str(len(self.delegations) + 1)
        record = {
            "delegation_id": delegation_id,
            "attributed_caller_role_id": self.caller_role_id,
            "target_role_id": target_role_id,
            "task": arguments["task"],
        }
        self.delegations.append(record)
        result = {
            "request_id": request_id,
            "status": "ok",
            "delegation": {
                key: value for key, value in record.items() if key != "task"
            },
        }
        self._log(
            request_id,
            tool_name,
            "ok",
            {
                "delegation_id": delegation_id,
                "target_exists": True,
                "target_authorized": True,
                "task_length": len(arguments["task"]),
            },
        )
        return result

    def record_unknown_tool(self):
        request_id = self._new_request_id()
        self._log(request_id, None, "tool_not_found", {})
        return request_id

    def record_invalid_tool_call(self):
        request_id = self._new_request_id()
        self._log(request_id, None, "invalid_params", {})
        return request_id

    @staticmethod
    def _new_request_id():
        return "req-" + uuid.uuid4().hex

    def _validate(self, tool_name, arguments):
        if not isinstance(tool_name, str) or tool_name not in KNOWN_TOOL_NAMES:
            return "unknown tool"
        if not isinstance(arguments, dict):
            return "arguments must be an object"
        if IDENTITY_FIELDS.intersection(arguments):
            return "caller identity fields are forbidden"

        expected = {
            "query_thread": set(),
            "send_message": {"target_role_id", "message"},
            "publish_delegation": {"target_role_id", "task"},
        }[tool_name]
        if set(arguments) != expected:
            return "arguments do not match the tool schema"
        for value in arguments.values():
            if not isinstance(value, str) or not value.strip():
                return "string arguments must be non-empty"
        return None

    def _thread_summary(self):
        return {
            "thread_id": "synthetic-thread-5.1",
            "title": "Stargazing 5 synthetic thread",
            "roles": [self.caller_role_id, "allowed-worker", "forbidden-worker"],
            "message_count": len(self.messages),
            "delegation_count": len(self.delegations),
        }

    @staticmethod
    def _error(request_id, code, message):
        return {
            "request_id": request_id,
            "status": "error",
            "error": {"code": code, "message": message},
        }

    def _log(self, request_id, tool_name, outcome, facts):
        event = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": "harness_tool_call",
            "request_id": request_id,
            "caller_role_id": self.caller_role_id,
            "tool": (
                tool_name
                if isinstance(tool_name, str) and tool_name in KNOWN_TOOL_NAMES
                else "invalid"
            ),
            "outcome": outcome,
            "facts": facts,
        }
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(event, separators=(",", ":")) + "\n")


class StdioMcpServer:
    def __init__(self, harness):
        self.harness = harness

    def handle(self, message):
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return self._rpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")

        method = message.get("method")
        request_id = message.get("id")
        if method == "notifications/initialized" and "id" not in message:
            return None
        if "id" not in message:
            return None

        if method == "initialize":
            return self._rpc_result(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "stargazing-005-fake-harness", "version": "0.1"},
                },
            )
        if method == "tools/list":
            params = message.get("params", {})
            valid_params = (
                isinstance(params, dict)
                and set(params).issubset({"_meta", "cursor"})
                and ("_meta" not in params or isinstance(params["_meta"], dict))
                and ("cursor" not in params or isinstance(params["cursor"], str))
            )
            if not valid_params:
                return self._rpc_error(request_id, -32602, "Invalid params")
            return self._rpc_result(request_id, {"tools": TOOLS})
        if method == "ping":
            return self._rpc_result(request_id, {})
        if method == "tools/call":
            params = message.get("params")
            valid_params = (
                isinstance(params, dict)
                and "name" in params
                and isinstance(params["name"], str)
                and set(params).issubset({"name", "arguments", "_meta"})
                and ("_meta" not in params or isinstance(params["_meta"], dict))
            )
            if not valid_params:
                harness_request_id = self.harness.record_invalid_tool_call()
                return self._rpc_error(
                    request_id,
                    -32602,
                    "Invalid params",
                    {"request_id": harness_request_id},
                )

            tool_name = params["name"]
            arguments = params.get("arguments", {})
            if tool_name not in KNOWN_TOOL_NAMES:
                harness_request_id = self.harness.record_unknown_tool()
                return self._rpc_error(
                    request_id,
                    -32602,
                    "Unknown tool",
                    {"request_id": harness_request_id},
                )
            result = self.harness.call_tool(tool_name, arguments)
            tool_result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, separators=(",", ":")),
                    }
                ],
                "structuredContent": result,
                "isError": result["status"] == "error",
            }
            return self._rpc_result(request_id, tool_result)
        return self._rpc_error(request_id, -32601, "Method not found")

    @staticmethod
    def _rpc_result(request_id, result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _rpc_error(request_id, code, message, data=None):
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
        if data is not None:
            response["error"]["data"] = data
        return response


def serve(log_path):
    server = StdioMcpServer(FakeHarness(log_path))
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = StdioMcpServer._rpc_error(None, -32700, "Parse error")
        else:
            response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, help="Path for redacted server-fact JSONL")
    args = parser.parse_args()
    serve(args.log)


if __name__ == "__main__":
    main()
