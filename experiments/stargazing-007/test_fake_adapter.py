import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ADAPTER = Path(__file__).resolve().parent / "fake_adapter.py"


class FakeAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.ledger_path = Path(self.temporary_directory.name) / "adapter.jsonl"

    def test_first_dispatch_is_accepted_and_records_minimal_ledger_entry(self):
        result = self._invoke("attempt-1")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {"accepted": True, "attempt_id": "attempt-1", "outcome": "accepted"},
        )
        self.assertEqual(
            self._ledger(),
            [{"sequence": 1, "attempt_id": "attempt-1", "outcome": "accepted"}],
        )

    def test_duplicate_dispatch_is_recorded_and_rejected(self):
        self.assertEqual(self._invoke("attempt-1").returncode, 0)

        duplicate = self._invoke("attempt-1")

        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual(
            json.loads(duplicate.stdout),
            {"accepted": False, "attempt_id": "attempt-1", "error": "duplicate"},
        )
        ledger = self._ledger()
        self.assertEqual(
            ledger,
            [
                {"sequence": 1, "attempt_id": "attempt-1", "outcome": "accepted"},
                {"sequence": 2, "attempt_id": "attempt-1", "outcome": "duplicate"},
            ],
        )
        self.assertEqual(len(ledger), 2)
        self.assertEqual(sum(row["outcome"] == "accepted" for row in ledger), 1)
        self.assertEqual(sum(row["outcome"] == "duplicate" for row in ledger), 1)

    def test_non_fixed_attempt_is_refused_without_ledger_entry(self):
        result = self._invoke("attempt-other")

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {"accepted": False, "attempt_id": "attempt-other", "error": "invalid_attempt_id"},
        )
        self.assertFalse(self.ledger_path.exists())

    def _invoke(self, attempt_id):
        return subprocess.run(
            [
                sys.executable,
                str(ADAPTER),
                "--ledger",
                str(self.ledger_path),
                "--attempt-id",
                attempt_id,
            ],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )

    def _ledger(self):
        return [json.loads(line) for line in self.ledger_path.read_text().splitlines()]


if __name__ == "__main__":
    unittest.main()
