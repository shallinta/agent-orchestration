import hashlib
import json
import unittest
from pathlib import Path


SCENARIO_PATH = Path(__file__).with_name("scenario.json")
EXPECTED_DIGEST = "3693a77a40317224222f302e2f6c01365bd3a2abcd1c8b05f03f11fd2702ad83"


def canonical_digest(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScenarioTest(unittest.TestCase):
    def test_frozen_agent_visible_scenario(self):
        self.assertTrue(SCENARIO_PATH.exists(), "scenario fixture is absent")
        scenario = json.loads(SCENARIO_PATH.read_text())
        self.assertTrue(scenario["goal"].strip())
        self.assertTrue(all(item.strip() for item in scenario["acceptance_criteria"]))
        evidence_ids = [item["id"] for item in scenario["evidence"]]
        self.assertEqual(evidence_ids, ["E{:02d}".format(i) for i in range(1, 19)])
        self.assertEqual(len(evidence_ids), len(set(evidence_ids)))
        self.assertTrue(all(item["fact"].strip() for item in scenario["evidence"]))
        self.assertNotIn("oracle", json.dumps(scenario, ensure_ascii=False).lower())
        self.assertEqual(canonical_digest(scenario), EXPECTED_DIGEST)
        self.assertEqual(canonical_digest(scenario), canonical_digest(scenario))


if __name__ == "__main__":
    unittest.main()
