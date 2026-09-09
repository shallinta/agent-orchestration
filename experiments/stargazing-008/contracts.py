import copy


class ContractError(ValueError):
    pass


_SIDE_EFFECTS = {
    "harness_recorded": {"visibility": "direct", "state": "recorded"},
    "workspace_observed": {"visibility": "bounded", "state": "marker_present"},
    "external_uncovered": {"visibility": "uncovered", "state": "unknown"},
}

_DECISION_ESCALATION = {
    "state": "required",
    "target": "responsible_actor",
    "notification_sent": False,
    "decision_taken": False,
    "automatic_action": "none",
}

_GRACEFUL_STOPPED = {
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
    "side_effects": _SIDE_EFFECTS,
    "decision_escalation": _DECISION_ESCALATION,
}

_FORCE_STOPPED = {
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
    "side_effects": _SIDE_EFFECTS,
    "decision_escalation": _DECISION_ESCALATION,
}

_GRACEFUL_STOPPED_UNKNOWN = {
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
    "side_effects": _SIDE_EFFECTS,
    "decision_escalation": _DECISION_ESCALATION,
}


def build_graceful_stopped_summary():
    return copy.deepcopy(_GRACEFUL_STOPPED)


def build_force_stopped_summary():
    return copy.deepcopy(_FORCE_STOPPED)


def build_graceful_stopped_unknown_summary():
    return copy.deepcopy(_GRACEFUL_STOPPED_UNKNOWN)


def validate_summary(summary):
    if summary not in (
        _GRACEFUL_STOPPED,
        _GRACEFUL_STOPPED_UNKNOWN,
        _FORCE_STOPPED,
    ):
        raise ContractError("summary does not match a fixed Stargazing 8 contract")
    return summary
