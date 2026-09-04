import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
SERVER = HERE / "harness_mcp.py"


def request(request_id, method, params=None):
    value = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        value["params"] = params
    return value


class HarnessMcpTest(unittest.TestCase):
    def run_server(self, messages, caller="host-codex"):
        self.assertTrue(SERVER.exists(), "MCP server is absent")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = root / "state.json"
            log = root / "facts.jsonl"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SERVER),
                    "--state",
                    str(state),
                    "--log",
                    str(log),
                    "--caller-role",
                    caller,
                ],
                input="".join(json.dumps(item) + "\n" for item in messages),
                text=True,
                capture_output=True,
                check=False,
            )
            logs = [] if not log.exists() else [json.loads(line) for line in log.read_text().splitlines()]
            snapshot = None if not state.exists() else json.loads(state.read_text())
            return completed, logs, snapshot

    def test_protocol_surface_and_request_correlation(self):
        messages = [
            request(1, "initialize", {"protocolVersion": "2025-03-26"}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            request(2, "ping", {}),
            request(3, "tools/list", {"_meta": {"progressToken": "secret"}}),
            request(
                4,
                "tools/call",
                {"name": "query_thread", "arguments": {}, "_meta": {}},
            ),
            request(
                5,
                "tools/call",
                {
                    "name": "publish_delegation",
                    "arguments": {
                        "target_role_id": "investigator-claude",
                        "task": "agent-authored task",
                    },
                    "_meta": {"progressToken": "secret"},
                },
            ),
        ]
        completed, logs, snapshot = self.run_server(messages)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stderr, "")
        responses = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual([item["id"] for item in responses], [1, 2, 3, 4, 5])
        tools = responses[2]["result"]["tools"]
        self.assertEqual(
            {item["name"] for item in tools},
            {"query_thread", "publish_delegation", "send_message"},
        )
        for tool in tools:
            schema = tool["inputSchema"]
            self.assertFalse(schema["additionalProperties"])
            for field in ("caller", "caller_role_id", "session_id", "execution_attempt_id", "authority"):
                self.assertNotIn(field, schema.get("properties", {}))

        query = responses[3]["result"]["structuredContent"]
        delegation = responses[4]["result"]["structuredContent"]
        self.assertEqual(query["status"], "ok")
        self.assertEqual(query["thread"]["current_role_id"], "host-codex")
        self.assertNotIn("oracle", json.dumps(query, ensure_ascii=False).lower())
        self.assertEqual(delegation["status"], "ok")
        for response in responses[3:]:
            tool_result = response["result"]
            self.assertEqual(json.loads(tool_result["content"][0]["text"]), tool_result["structuredContent"])
        request_ids = {query["request_id"], delegation["request_id"]}
        self.assertEqual({entry["request_id"] for entry in logs}, request_ids)
        self.assertEqual(snapshot["delegation"]["publisher_role_id"], "host-codex")

    def test_query_rejects_non_object_arguments(self):
        completed, _, _ = self.run_server(
            [request(1, "tools/call", {"name": "query_thread", "arguments": []})]
        )
        response = json.loads(completed.stdout)["result"]
        self.assertTrue(response["isError"])
        self.assertEqual(response["structuredContent"]["error"]["code"], "invalid_params")

    def test_business_error_is_structured_and_does_not_write(self):
        messages = [
            request(
                1,
                "tools/call",
                {
                    "name": "publish_delegation",
                    "arguments": {
                        "target_role_id": "investigator-claude",
                        "task": "forbidden",
                    },
                },
            )
        ]
        completed, logs, snapshot = self.run_server(messages, caller="investigator-claude")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        response = json.loads(completed.stdout)["result"]
        self.assertTrue(response["isError"])
        self.assertEqual(response["structuredContent"]["error"]["code"], "forbidden")
        self.assertIsNone(snapshot["delegation"])
        self.assertEqual(logs[0]["request_id"], response["structuredContent"]["request_id"])

    def test_invalid_startup_caller_is_rejected_before_serving(self):
        self.assertTrue(SERVER.exists(), "MCP server is absent")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SERVER),
                    "--state",
                    str(root / "state.json"),
                    "--log",
                    str(root / "facts.jsonl"),
                    "--caller-role",
                    "forged-role",
                ],
                input="",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse((root / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
