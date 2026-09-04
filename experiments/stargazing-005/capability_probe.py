#!/usr/bin/env python3
"""Throwaway capability-backed CLI and loopback HTTP probe."""

import argparse
import datetime
import hashlib
import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from harness_server import FakeHarness


CAPABILITY_ENV = "SG5_CAPABILITY"
DEFAULT_REGISTRY = {
    "ad975852a5a51122e011626954be93d1b0cc4de7b3fae1cf0c27eaaf108f2caa": (
        "capability-probe-caller"
    )
}


class CapabilityRegistry:
    def __init__(self, digest_to_role=None):
        self.digest_to_role = dict(digest_to_role or DEFAULT_REGISTRY)

    def resolve(self, capability):
        if not isinstance(capability, str):
            return None
        digest = hashlib.sha256(capability.encode()).hexdigest()
        return self.digest_to_role.get(digest)


class CapabilityChannel:
    def __init__(self, log_path, registry=None):
        self.log_path = Path(log_path)
        self.registry = registry or CapabilityRegistry()
        self.harnesses = {}

    def call(self, capability, tool, arguments):
        caller_role_id = self.registry.resolve(capability)
        if caller_role_id is None:
            return self._unauthorized()
        harness = self.harnesses.setdefault(
            caller_role_id,
            FakeHarness(self.log_path, caller_role_id=caller_role_id),
        )
        return harness.call_tool(tool, arguments)

    def invalid_request(self, capability):
        caller_role_id = self.registry.resolve(capability)
        if caller_role_id is None:
            return self._unauthorized()
        harness = self.harnesses.setdefault(
            caller_role_id,
            FakeHarness(self.log_path, caller_role_id=caller_role_id),
        )
        return harness.call_tool(None, None)

    def _unauthorized(self):
        request_id = "req-" + uuid.uuid4().hex
        event = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": "capability_auth",
            "request_id": request_id,
            "caller_role_id": None,
            "tool": "invalid",
            "outcome": "unauthorized",
            "facts": {"capability_valid": False},
        }
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(event, separators=(",", ":")) + "\n")
        return {
            "request_id": request_id,
            "status": "error",
            "error": {"code": "unauthorized", "message": "invalid capability"},
        }


def status_code(result):
    if result["status"] == "ok":
        return 200
    return {
        "unauthorized": 401,
        "invalid_params": 400,
        "not_found": 404,
        "forbidden": 403,
    }.get(result["error"]["code"], 400)


class CapabilityHttpHandler(BaseHTTPRequestHandler):
    server_version = "SG5CapabilityProbe/0.1"

    def do_POST(self):
        if self.path != "/call":
            self._write(404, {"status": "error", "error": {"code": "not_found"}})
            return

        authorization = self.headers.get("Authorization", "")
        capability = authorization[7:] if authorization.startswith("Bearer ") else None
        if self.server.channel.registry.resolve(capability) is None:
            result = self.server.channel.call(capability, None, None)
            self._write(401, result)
            return

        try:
            length = int(self.headers.get("Content-Length", ""))
            body = json.loads(self.rfile.read(length))
        except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            result = self.server.channel.invalid_request(capability)
            self._write(400, result)
            return

        valid_body = (
            isinstance(body, dict)
            and "tool" in body
            and isinstance(body["tool"], str)
            and set(body).issubset({"tool", "arguments"})
        )
        if not valid_body:
            result = self.server.channel.invalid_request(capability)
        else:
            result = self.server.channel.call(
                capability,
                body["tool"],
                body.get("arguments", {}),
            )
        self._write(status_code(result), result)

    def _write(self, status, payload):
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format_string, *args):
        return


def create_http_server(log_path, registry=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), CapabilityHttpHandler)
    server.daemon_threads = True
    server.channel = CapabilityChannel(log_path, registry=registry)
    return server


def cli_main(args):
    channel = CapabilityChannel(args.log)
    capability = os.environ.get(CAPABILITY_ENV)
    try:
        arguments = json.loads(args.arguments)
    except json.JSONDecodeError:
        result = channel.invalid_request(capability)
    else:
        result = channel.call(capability, args.tool, arguments)
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
    if result["status"] == "ok":
        return 0
    if result["error"]["code"] == "unauthorized":
        return 3
    return 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="transport", required=True)
    cli = subparsers.add_parser("cli")
    cli.add_argument("--log", required=True)
    cli.add_argument("tool")
    cli.add_argument("--arguments", default="{}")
    args = parser.parse_args()
    if args.transport == "cli":
        return cli_main(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
