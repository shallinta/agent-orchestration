import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
PROBE_PATH = HERE / "capability_probe.py"
DRIVER_PATH = HERE / "structured_request_driver.py"
SCHEMA_PATH = HERE / "structured_request.schema.json"
VALID_CAPABILITY = "sg5-synthetic-capability-v1"
VALID_ATTEMPT = "sg5-structured-attempt-1"


def read_logs(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


class CapabilityCliTest(unittest.TestCase):
    def run_cli(self, capability, tool, arguments):
        self.assertTrue(PROBE_PATH.exists(), "capability probe is not implemented")
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "facts.jsonl"
            env = os.environ.copy()
            if capability is None:
                env.pop("SG5_CAPABILITY", None)
            else:
                env["SG5_CAPABILITY"] = capability
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROBE_PATH),
                    "cli",
                    "--log",
                    str(log_path),
                    tool,
                    "--arguments",
                    json.dumps(arguments),
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            return completed, read_logs(log_path)

    def test_cli_supports_three_harness_tools(self):
        cases = [
            ("query_thread", {}),
            ("send_message", {"target_role_id": "allowed-worker", "message": "hello"}),
            (
                "publish_delegation",
                {"target_role_id": "allowed-worker", "task": "inspect"},
            ),
        ]
        for tool, arguments in cases:
            with self.subTest(tool=tool):
                completed, logs = self.run_cli(VALID_CAPABILITY, tool, arguments)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                result = json.loads(completed.stdout)
                self.assertEqual(result["status"], "ok")
                self.assertEqual(logs[0]["caller_role_id"], "capability-probe-caller")

    def test_cli_rejects_invalid_capability_without_leaking_it(self):
        invalid_capability = "TOP-SECRET invalid-capability"
        completed, logs = self.run_cli(invalid_capability, "query_thread", {})

        self.assertEqual(completed.returncode, 3)
        result = json.loads(completed.stdout)
        self.assertEqual(result["error"]["code"], "unauthorized")
        self.assertNotIn(invalid_capability, completed.stdout + completed.stderr + json.dumps(logs))
        self.assertIsNone(logs[0]["caller_role_id"])

    def test_cli_rejects_identity_injection_and_business_forbidden(self):
        forged_role = "TOP-SECRET forged-role"
        injected, injected_logs = self.run_cli(
            VALID_CAPABILITY,
            "send_message",
            {
                "target_role_id": "allowed-worker",
                "message": "must not write",
                "caller_role_id": forged_role,
            },
        )
        forbidden, forbidden_logs = self.run_cli(
            VALID_CAPABILITY,
            "publish_delegation",
            {"target_role_id": "forbidden-worker", "task": "must reject"},
        )

        self.assertEqual(injected.returncode, 2)
        self.assertEqual(json.loads(injected.stdout)["error"]["code"], "invalid_params")
        self.assertNotIn(forged_role, json.dumps(injected_logs))
        self.assertEqual(forbidden.returncode, 2)
        self.assertEqual(json.loads(forbidden.stdout)["error"]["code"], "forbidden")
        self.assertEqual(forbidden_logs[0]["caller_role_id"], "capability-probe-caller")


class CapabilityHttpTest(unittest.TestCase):
    def load_probe(self):
        self.assertTrue(PROBE_PATH.exists(), "capability probe is not implemented")
        sys.path.insert(0, str(HERE))
        try:
            spec = importlib.util.spec_from_file_location("sg5_capability_probe", PROBE_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        finally:
            sys.path.pop(0)

    @staticmethod
    def post(url, capability, body):
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + capability,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            status = error.code
            payload = json.loads(error.read())
            error.close()
            return status, payload

    def test_loopback_http_success_and_rejections_are_structured(self):
        probe = self.load_probe()
        secret_text = "TOP-SECRET http-message"
        invalid_capability = "TOP-SECRET invalid-http-capability"
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "facts.jsonl"
            server = probe.create_http_server(log_path)
            self.assertEqual(server.server_address[0], "127.0.0.1")
            self.assertNotEqual(server.server_address[1], 0)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            url = "http://127.0.0.1:{}/call".format(server.server_address[1])
            try:
                ok_status, ok = self.post(
                    url,
                    VALID_CAPABILITY,
                    {
                        "tool": "send_message",
                        "arguments": {
                            "target_role_id": "allowed-worker",
                            "message": secret_text,
                        },
                    },
                )
                auth_status, auth = self.post(url, invalid_capability, {"tool": "query_thread"})
                injection_status, injection = self.post(
                    url,
                    VALID_CAPABILITY,
                    {"tool": "query_thread", "caller": "forged-role"},
                )
                forbidden_status, forbidden = self.post(
                    url,
                    VALID_CAPABILITY,
                    {
                        "tool": "publish_delegation",
                        "arguments": {"target_role_id": "forbidden-worker", "task": "reject"},
                    },
                )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertFalse(thread.is_alive())
            self.assertEqual((ok_status, ok["status"]), (200, "ok"))
            self.assertEqual(ok["message"]["attributed_caller_role_id"], "capability-probe-caller")
            self.assertEqual((auth_status, auth["error"]["code"]), (401, "unauthorized"))
            self.assertEqual((injection_status, injection["error"]["code"]), (400, "invalid_params"))
            self.assertEqual((forbidden_status, forbidden["error"]["code"]), (403, "forbidden"))
            serialized = json.dumps(read_logs(log_path))
            for secret in (VALID_CAPABILITY, invalid_capability, secret_text, "forged-role"):
                self.assertNotIn(secret, serialized)


class StructuredRequestDriverTest(unittest.TestCase):
    def run_driver(self, request_body):
        self.assertTrue(DRIVER_PATH.exists(), "structured request driver is not implemented")
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "facts.jsonl"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(DRIVER_PATH),
                    "--log",
                    str(log_path),
                    "--execution-attempt",
                    VALID_ATTEMPT,
                ],
                input=json.dumps(request_body),
                text=True,
                capture_output=True,
                check=False,
            )
            return completed, read_logs(log_path)

    def test_schema_has_only_tool_and_arguments(self):
        self.assertTrue(SCHEMA_PATH.exists(), "structured request schema is not implemented")
        schema = json.loads(SCHEMA_PATH.read_text())
        self.assertEqual(set(schema["properties"]), {"tool", "arguments"})
        self.assertEqual(set(schema["required"]), {"tool", "arguments"})
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["properties"]["tool"]["enum"], ["query_thread"])
        self.assertEqual(schema["properties"]["arguments"]["properties"], {})
        self.assertEqual(schema["properties"]["arguments"]["required"], [])
        self.assertFalse(schema["properties"]["arguments"]["additionalProperties"])
        for identity_field in ("caller", "caller_role_id", "role_id", "execution_attempt_id"):
            self.assertNotIn(identity_field, schema["properties"])

    def test_driver_rejects_request_outside_probe_schema(self):
        completed, logs = self.run_driver(
            {
                "tool": "send_message",
                "arguments": {
                    "target_role_id": "allowed-worker",
                    "message": "must not run",
                },
            }
        )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["error"]["code"], "invalid_params")
        self.assertEqual(logs[0]["tool"], "invalid")

    def test_driver_uses_execution_attempt_attribution(self):
        completed, logs = self.run_driver({"tool": "query_thread", "arguments": {}})

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["status"], "ok")
        self.assertIn("structured-probe-caller", result["thread"]["roles"])
        self.assertEqual(logs[0]["caller_role_id"], "structured-probe-caller")

    def test_driver_rejects_extra_identity_field_without_calling_tool(self):
        forged_role = "TOP-SECRET structured-forged-role"
        completed, logs = self.run_driver(
            {"tool": "query_thread", "arguments": {}, "caller_role_id": forged_role}
        )

        self.assertEqual(completed.returncode, 2)
        result = json.loads(completed.stdout)
        self.assertEqual(result["error"]["code"], "invalid_params")
        self.assertEqual(logs[0]["tool"], "invalid")
        self.assertNotIn(forged_role, json.dumps(logs))


if __name__ == "__main__":
    unittest.main()
