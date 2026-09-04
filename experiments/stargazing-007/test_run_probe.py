import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROBE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE_DIRECTORY))

from run_probe import run_probe


RUN_PROBE = PROBE_DIRECTORY / "run_probe.py"


EXPECTED_SUMMARY = {
    "schema_version": "stargazing-007-probe-v1",
    "planned_crash_observed": True,
    "fact_counts": {
        "roles": 2,
        "delegations": 1,
        "attempts": 1,
        "events": 6,
        "messages": 0,
        "agent_results": 0,
        "delegation_completions": 0,
        "acceptances": 1,
    },
    "states": {
        "dispatch": "accepted",
        "terminal": None,
        "recovery": "result_unknown",
    },
    "adapter_counts": {"total": 1, "accepted": 1, "duplicate": 0},
    "unknown_event_count": 1,
    "redispatch_count": 0,
    "idempotent": True,
}


class RunProbeTest(unittest.TestCase):
    def test_three_process_probe_in_one_temporary_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = run_probe(Path(directory))

        self.assertEqual(summary, EXPECTED_SUMMARY)

    def test_cli_emits_only_the_sanitized_structural_summary(self):
        result = subprocess.run(
            [sys.executable, str(RUN_PROBE)],
            shell=False,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(len(result.stdout.splitlines()), 1)
        self.assertEqual(json.loads(result.stdout), EXPECTED_SUMMARY)
        for forbidden_key in (
            "path",
            "database",
            "ledger",
            "environment",
            "prompt",
            "stdout",
            "stderr",
            "payload",
        ):
            self.assertNotIn(forbidden_key, result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
