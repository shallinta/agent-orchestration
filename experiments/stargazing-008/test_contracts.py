import copy
import sys
import unittest
from pathlib import Path


PROBE_DIRECTORY = Path(__file__).resolve().parent
sys.path.insert(0, str(PROBE_DIRECTORY))

from contracts import (
    ContractError,
    build_force_stopped_summary,
    build_graceful_stopped_summary,
    build_graceful_stopped_unknown_summary,
    validate_summary,
)


EXPECTED_SIDE_EFFECTS = {
    "harness_recorded": {"visibility": "direct", "state": "recorded"},
    "workspace_observed": {"visibility": "bounded", "state": "marker_present"},
    "external_uncovered": {"visibility": "uncovered", "state": "unknown"},
}

EXPECTED_ESCALATION = {
    "state": "required",
    "target": "responsible_actor",
    "notification_sent": False,
    "decision_taken": False,
    "automatic_action": "none",
}


class ContractTest(unittest.TestCase):
    def test_builds_fixed_graceful_stopped_summary(self):
        summary = build_graceful_stopped_summary()

        self.assertEqual(
            summary,
            {
                "stop_request": {
                    "mode": "graceful",
                    "graceful_requested": True,
                    "deadline_expired": False,
                    "force_requested": False,
                },
                "stop_confirmation": "controlled_group_stopped",
                "terminal_state": "cancelled",
                "terminal_evidence": "synthetic_worker_terminal",
                "result_state": "cancelled",
                "slot_state": "released",
                "retry_eligibility": "blocked",
                "side_effects": EXPECTED_SIDE_EFFECTS,
                "decision_escalation": EXPECTED_ESCALATION,
            },
        )
        self.assertEqual(validate_summary(summary), summary)

    def test_builds_fixed_force_stopped_summary_without_terminal(self):
        summary = build_force_stopped_summary()

        self.assertEqual(
            summary,
            {
                "stop_request": {
                    "mode": "force_after_deadline",
                    "graceful_requested": True,
                    "deadline_expired": True,
                    "force_requested": True,
                },
                "stop_confirmation": "controlled_group_stopped",
                "terminal_state": None,
                "terminal_evidence": None,
                "result_state": "result_unknown",
                "slot_state": "released",
                "retry_eligibility": "blocked",
                "side_effects": EXPECTED_SIDE_EFFECTS,
                "decision_escalation": EXPECTED_ESCALATION,
            },
        )
        self.assertEqual(validate_summary(summary), summary)

    def test_builds_fixed_graceful_stopped_summary_without_terminal(self):
        summary = build_graceful_stopped_unknown_summary()

        self.assertEqual(
            summary,
            {
                "stop_request": {
                    "mode": "graceful",
                    "graceful_requested": True,
                    "deadline_expired": False,
                    "force_requested": False,
                },
                "stop_confirmation": "controlled_group_stopped",
                "terminal_state": None,
                "terminal_evidence": None,
                "result_state": "result_unknown",
                "slot_state": "released",
                "retry_eligibility": "blocked",
                "side_effects": EXPECTED_SIDE_EFFECTS,
                "decision_escalation": EXPECTED_ESCALATION,
            },
        )
        self.assertEqual(validate_summary(summary), summary)

    def test_rejects_overloaded_cancelled_field_and_non_exact_shapes(self):
        summary = build_graceful_stopped_summary()
        summary["cancelled"] = True

        with self.assertRaises(ContractError):
            validate_summary(summary)

    def test_rejects_side_effect_scope_or_bounded_state_drift(self):
        mutations = (
            lambda value: value["side_effects"].pop("external_uncovered"),
            lambda value: value["side_effects"].update(
                {"universal": {"visibility": "complete", "state": "absent"}}
            ),
            lambda value: value["side_effects"]["workspace_observed"].update(
                {"state": "all_effects_complete"}
            ),
            lambda value: value["side_effects"]["external_uncovered"].update(
                {"state": "rolled_back"}
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                summary = build_force_stopped_summary()
                mutate(summary)
                with self.assertRaises(ContractError):
                    validate_summary(summary)

    def test_rejects_released_slot_without_confirmed_stop(self):
        summary = build_force_stopped_summary()
        summary["stop_confirmation"] = "stop_requested_only"

        with self.assertRaises(ContractError):
            validate_summary(summary)

    def test_rejects_retry_allowed_with_unknown_result_or_side_effect(self):
        for summary in (
            build_force_stopped_summary(),
            build_graceful_stopped_summary(),
        ):
            with self.subTest(result_state=summary["result_state"]):
                summary["retry_eligibility"] = "allowed"
                with self.assertRaises(ContractError):
                    validate_summary(summary)

    def test_rejects_unknown_side_effect_without_fixed_decision_escalation(self):
        mutations = (
            None,
            {"state": "required", "target": "host"},
            {
                **EXPECTED_ESCALATION,
                "notification_sent": True,
            },
            {
                **EXPECTED_ESCALATION,
                "decision_taken": True,
            },
            {
                **EXPECTED_ESCALATION,
                "automatic_action": "retry",
            },
        )
        for escalation in mutations:
            with self.subTest(escalation=escalation):
                summary = build_force_stopped_summary()
                summary["decision_escalation"] = copy.deepcopy(escalation)
                with self.assertRaises(ContractError):
                    validate_summary(summary)

    def test_rejects_force_stop_without_prior_graceful_request_and_deadline(self):
        for field in ("graceful_requested", "deadline_expired"):
            with self.subTest(field=field):
                summary = build_force_stopped_summary()
                summary["stop_request"][field] = False
                with self.assertRaises(ContractError):
                    validate_summary(summary)

    def test_rejects_terminal_result_fabricated_from_process_exit(self):
        summary = build_graceful_stopped_summary()
        summary["terminal_evidence"] = "process_exit"

        with self.assertRaises(ContractError):
            validate_summary(summary)

    def test_rejects_result_and_terminal_contradictions(self):
        contradictions = (
            ("cancelled", None, None),
            ("result_unknown", "cancelled", "synthetic_worker_terminal"),
            ("succeeded", "cancelled", "synthetic_worker_terminal"),
        )
        for result_state, terminal_state, terminal_evidence in contradictions:
            with self.subTest(result_state=result_state):
                summary = build_force_stopped_summary()
                summary["result_state"] = result_state
                summary["terminal_state"] = terminal_state
                summary["terminal_evidence"] = terminal_evidence
                with self.assertRaises(ContractError):
                    validate_summary(summary)


if __name__ == "__main__":
    unittest.main()
