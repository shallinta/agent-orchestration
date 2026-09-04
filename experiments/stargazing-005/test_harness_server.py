import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parent
SERVER_PATH = EXPERIMENT_DIR / "harness_server.py"


def rpc_request(request_id, method, params=None):
    request = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        request["params"] = params
    return request


def tool_call(request_id, name, arguments):
    return rpc_request(
        request_id,
        "tools/call",
        {"name": name, "arguments": arguments},
    )


class HarnessServerProtocolTest(unittest.TestCase):
    def run_server(self, messages):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "server-facts.jsonl"
            stdin = "".join(json.dumps(message) + "\n" for message in messages)
            completed = subprocess.run(
                [sys.executable, str(SERVER_PATH), "--log", str(log_path)],
                input=stdin,
                text=True,
                capture_output=True,
                check=False,
            )
            logs = []
            if log_path.exists():
                logs = [json.loads(line) for line in log_path.read_text().splitlines()]
            return completed, logs

    def assert_tool_result_consistent(self, response):
        result = response["result"]
        structured = result["structuredContent"]
        self.assertEqual(json.loads(result["content"][0]["text"]), structured)
        self.assertEqual(result["isError"], structured["status"] == "error")

    def test_stdio_mcp_surface_and_harness_outcomes(self):
        secret_message = "TOP-SECRET token=do-not-log"
        forged_role = "stolen-admin-role"
        messages = [
            rpc_request(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "probe-test", "version": "1"},
                },
            ),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            rpc_request(2, "tools/list", {}),
            tool_call(3, "query_thread", {}),
            tool_call(
                4,
                "send_message",
                {"target_role_id": "allowed-worker", "message": secret_message},
            ),
            tool_call(
                5,
                "send_message",
                {"target_role_id": "missing-worker", "message": "hello"},
            ),
            tool_call(
                6,
                "publish_delegation",
                {"target_role_id": "allowed-worker", "task": "Inspect synthetic facts"},
            ),
            tool_call(
                7,
                "publish_delegation",
                {"target_role_id": "forbidden-worker", "task": "Must be denied"},
            ),
            tool_call(
                8,
                "publish_delegation",
                {"target_role_id": "missing-worker", "task": "Must not exist"},
            ),
            tool_call(
                9,
                "send_message",
                {
                    "target_role_id": "allowed-worker",
                    "message": "forged attribution",
                    "caller_role_id": forged_role,
                },
            ),
            tool_call(
                10,
                "publish_delegation",
                {"target_role_id": "allowed-worker", "unexpected": "field"},
            ),
            tool_call(11, "query_thread", {}),
        ]

        completed, logs = self.run_server(messages)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([response["id"] for response in responses], list(range(1, 12)))

        initialize = responses[0]["result"]
        self.assertEqual(initialize["protocolVersion"], "2025-03-26")
        self.assertIn("tools", initialize["capabilities"])

        tools = responses[1]["result"]["tools"]
        self.assertEqual(
            {tool["name"] for tool in tools},
            {"query_thread", "send_message", "publish_delegation"},
        )
        for tool in tools:
            schema = tool["inputSchema"]
            self.assertFalse(schema["additionalProperties"])
            self.assertNotIn("caller_role_id", schema.get("properties", {}))
            self.assertNotIn("caller", schema.get("properties", {}))
            self.assertNotIn("role_id", schema.get("properties", {}))

        results = {
            response["id"]: response["result"]["structuredContent"]
            for response in responses[2:]
        }
        self.assertEqual(results[3]["status"], "ok")
        self.assertEqual(results[3]["thread"]["message_count"], 0)
        self.assertEqual(results[3]["thread"]["delegation_count"], 0)

        self.assertEqual(results[4]["status"], "ok")
        self.assertEqual(results[4]["message"]["attributed_caller_role_id"], "probe-caller")
        self.assertEqual(results[5]["error"]["code"], "not_found")

        self.assertEqual(results[6]["status"], "ok")
        self.assertEqual(results[6]["delegation"]["attributed_caller_role_id"], "probe-caller")
        self.assertEqual(results[7]["error"]["code"], "forbidden")
        self.assertEqual(results[8]["error"]["code"], "not_found")
        self.assertEqual(results[9]["error"]["code"], "invalid_params")
        self.assertEqual(results[10]["error"]["code"], "invalid_params")

        self.assertEqual(results[11]["thread"]["message_count"], 1)
        self.assertEqual(results[11]["thread"]["delegation_count"], 1)

        tool_responses = responses[2:]
        for response in tool_responses:
            self.assert_tool_result_consistent(response)
        self.assertEqual(len(logs), len(tool_responses))
        response_request_ids = {
            response["result"]["structuredContent"]["request_id"]
            for response in tool_responses
        }
        self.assertEqual(len(response_request_ids), len(tool_responses))
        self.assertEqual({entry["request_id"] for entry in logs}, response_request_ids)
        self.assertEqual({entry["caller_role_id"] for entry in logs}, {"probe-caller"})
        self.assertEqual(
            [entry["outcome"] for entry in logs],
            [
                "ok",
                "ok",
                "not_found",
                "ok",
                "forbidden",
                "not_found",
                "invalid_params",
                "invalid_params",
                "ok",
            ],
        )

        serialized_logs = "\n".join(json.dumps(entry) for entry in logs)
        self.assertNotIn(secret_message, serialized_logs)
        self.assertNotIn(forged_role, serialized_logs)
        self.assertNotIn("token=", serialized_logs)
        for target_role_id in ("allowed-worker", "forbidden-worker", "missing-worker"):
            self.assertNotIn(target_role_id, serialized_logs)

    def test_each_supported_identity_field_is_rejected_without_writes(self):
        messages = []
        request_id = 1
        for field in ("caller_role_id", "caller", "role_id"):
            messages.append(
                tool_call(
                    request_id,
                    "send_message",
                    {
                        "target_role_id": "allowed-worker",
                        "message": "must not be written",
                        field: "forged-role",
                    },
                )
            )
            request_id += 1
        for field in ("caller_role_id", "caller", "role_id"):
            request = tool_call(
                request_id,
                "send_message",
                {
                    "target_role_id": "allowed-worker",
                    "message": "outer injection must not be written",
                },
            )
            request["params"]["_meta"] = {"progressToken": "synthetic-meta"}
            request["params"][field] = "forged-role"
            messages.append(request)
            request_id += 1
        messages.append(tool_call(request_id, "query_thread", {}))

        completed, logs = self.run_server(messages)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        for response in responses[:3]:
            result = response["result"]["structuredContent"]
            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"]["code"], "invalid_params")
        for response in responses[3:6]:
            self.assertNotIn("result", response)
            self.assertEqual(response["error"]["code"], -32602)
            self.assertEqual(response["error"]["message"], "Invalid params")
        summary = responses[6]["result"]["structuredContent"]["thread"]
        self.assertEqual(summary["message_count"], 0)
        self.assertEqual(summary["delegation_count"], 0)
        self.assertEqual([entry["outcome"] for entry in logs], [
            "invalid_params",
            "invalid_params",
            "invalid_params",
            "invalid_params",
            "invalid_params",
            "invalid_params",
            "ok",
        ])

    def test_log_never_contains_agent_controlled_tool_or_target_strings(self):
        secret_tool = "TOP-SECRET token=unknown-tool"
        secret_target = "TOP-SECRET token=unknown-target"
        messages = [
            tool_call(1, secret_tool, {"target_role_id": "allowed-worker"}),
            tool_call(
                2,
                "send_message",
                {"target_role_id": secret_target, "message": "hello"},
            ),
        ]

        completed, logs = self.run_server(messages)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(len(logs), 2)
        serialized_logs = "\n".join(json.dumps(entry) for entry in logs)
        self.assertNotIn(secret_tool, serialized_logs)
        self.assertNotIn(secret_target, serialized_logs)
        self.assertNotIn("TOP-SECRET", serialized_logs)
        self.assertEqual(logs[0]["tool"], "invalid")
        self.assertNotIn("target_role_id", logs[1]["facts"])

    def test_unknown_tool_is_a_json_rpc_error(self):
        completed, logs = self.run_server(
            [tool_call(1, "not-a-harness-tool", {})]
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertNotIn("result", response)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(response["error"]["message"], "Unknown tool")
        self.assertEqual(response["error"]["data"]["request_id"], logs[0]["request_id"])
        self.assertEqual(logs[0]["tool"], "invalid")
        self.assertEqual(logs[0]["outcome"], "tool_not_found")

    def test_non_string_tool_name_is_protocol_invalid_params(self):
        completed, logs = self.run_server([tool_call(1, ["not-a-string"], {})])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertNotIn("result", response)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(response["error"]["message"], "Invalid params")
        self.assertEqual(response["error"]["data"]["request_id"], logs[0]["request_id"])
        self.assertEqual(logs[0]["tool"], "invalid")
        self.assertEqual(logs[0]["outcome"], "invalid_params")

    def test_query_thread_allows_omitted_arguments(self):
        completed, logs = self.run_server(
            [rpc_request(1, "tools/call", {"name": "query_thread"})]
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assert_tool_result_consistent(response)
        self.assertEqual(response["result"]["structuredContent"]["status"], "ok")
        self.assertEqual(len(logs), 1)

    def test_tools_call_accepts_protocol_meta(self):
        secret_meta = "TOP-SECRET token=protocol-meta"
        request = tool_call(1, "query_thread", {})
        request["params"]["_meta"] = {"progressToken": secret_meta}

        completed, logs = self.run_server([request])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assert_tool_result_consistent(response)
        self.assertEqual(response["result"]["structuredContent"]["status"], "ok")
        self.assertEqual(logs[0]["tool"], "query_thread")
        self.assertNotIn(secret_meta, json.dumps(logs))

    def test_tools_call_rejects_non_object_meta_at_protocol_layer(self):
        request = tool_call(1, "query_thread", {})
        request["params"]["_meta"] = "not-an-object"

        completed, logs = self.run_server([request])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertNotIn("result", response)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(response["error"]["message"], "Invalid params")
        self.assertEqual(response["error"]["data"]["request_id"], logs[0]["request_id"])
        self.assertEqual(logs[0]["outcome"], "invalid_params")

    def test_tools_call_rejects_extra_outer_fields_at_protocol_layer(self):
        request = tool_call(1, "query_thread", {})
        request["params"]["unexpected"] = "must-not-be-accepted"

        completed, logs = self.run_server([request])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertNotIn("result", response)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(response["error"]["message"], "Invalid params")
        self.assertEqual(response["error"]["data"]["request_id"], logs[0]["request_id"])
        self.assertEqual(logs[0]["outcome"], "invalid_params")

    def test_ping_returns_an_empty_result(self):
        completed, logs = self.run_server([rpc_request(1, "ping", {})])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertEqual(response, {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(logs, [])

    def test_tools_list_accepts_meta_and_optional_string_cursor(self):
        completed, logs = self.run_server(
            [
                rpc_request(
                    1,
                    "tools/list",
                    {"_meta": {"progressToken": "synthetic-meta"}},
                ),
                rpc_request(2, "tools/list", {"_meta": {}, "cursor": ""}),
                rpc_request(3, "tools/list", {"cursor": "synthetic-cursor"}),
            ]
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(len(responses), 3)
        for response in responses:
            self.assertIn("result", response, response)
            self.assertEqual(
                {tool["name"] for tool in response["result"]["tools"]},
                {"query_thread", "send_message", "publish_delegation"},
            )
        self.assertEqual(logs, [])

    def test_tools_list_rejects_extra_fields(self):
        completed, logs = self.run_server(
            [
                rpc_request(
                    1,
                    "tools/list",
                    {"_meta": {}, "cursor": "synthetic-cursor", "unexpected": True},
                )
            ]
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)
        self.assertEqual(response["error"]["code"], -32602)
        self.assertEqual(response["error"]["message"], "Invalid params")
        self.assertEqual(logs, [])


if __name__ == "__main__":
    unittest.main()
