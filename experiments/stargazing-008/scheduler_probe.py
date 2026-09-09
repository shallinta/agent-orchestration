import copy

from contracts import validate_summary
from stop_controller import (
    CompletionReceipt,
    StopReceipt,
    complete_managed_worker,
    start_managed_worker,
    stop_managed_worker,
)


class SchedulerError(RuntimeError):
    pass


class SchedulerProbe:
    def __init__(self):
        self._roles = {
            "writer": self._new_role("writer", set()),
            "analyst": self._new_role("analyst", set()),
            "host-role": self._new_role("host-role", {"host"}),
            "supervisor-role": self._new_role("supervisor-role", {"supervisor"}),
        }
        self._attempts = {}
        self._dispatch_ledger = []

    @staticmethod
    def _new_role(role_id, labels):
        return {
            "role_id": role_id,
            "instance_identity": "fixed-" + role_id,
            "enabled": True,
            "capacity": 1,
            "labels": labels,
        }

    @property
    def dispatch_ledger(self):
        return copy.deepcopy(self._dispatch_ledger)

    def role(self, role_id):
        return copy.deepcopy(self._role_internal(role_id))

    def _role_internal(self, role_id):
        try:
            return self._roles[role_id]
        except KeyError as error:
            raise SchedulerError("unknown role") from error

    def active_attempts(self, role_id):
        self._role_internal(role_id)
        return [
            key
            for key, value in self._attempts.items()
            if value["role_id"] == role_id and value["state"] == "active"
        ]

    def dispatch_count(self, attempt_id):
        return self._dispatch_ledger.count(attempt_id)

    def submit(self, attempt_id, role_id, *, worker_path=None, workspace=None, ready_timeout=10.0):
        if attempt_id in self._attempts:
            raise SchedulerError("duplicate attempt")
        role = self._role_internal(role_id)
        active = role["enabled"] and not self.active_attempts(role_id)
        handle = None
        if active:
            if worker_path is None or workspace is None:
                raise SchedulerError("active dispatch requires managed worker")
            handle = start_managed_worker(
                worker_path=worker_path,
                workspace=workspace,
                ready_timeout=ready_timeout,
            )
        attempt = {
            "attempt_id": attempt_id,
            "role_id": role_id,
            "state": "active" if active else "pending",
            "terminal_state": None,
            "result_state": None,
            "retry_eligibility": "not_applicable",
            "execution_identity": handle.execution_identity if handle else None,
            "_handle": handle,
        }
        self._attempts[attempt_id] = attempt
        if active:
            self._dispatch_ledger.append(attempt_id)
        return self._attempt_view(attempt)

    def force_stop_attempt(self, attempt_id, **timeouts):
        attempt = self._active(attempt_id)
        receipt = stop_managed_worker(attempt["_handle"], **timeouts)
        self.apply_stop_receipt(attempt_id, receipt)
        return receipt

    def apply_stop_receipt(self, attempt_id, receipt):
        attempt = self._active(attempt_id)
        if (
            not isinstance(receipt, StopReceipt)
            or receipt.execution_identity != attempt["execution_identity"]
            or receipt.control_token is not attempt["_handle"].control_token
        ):
            raise SchedulerError("stop receipt identity mismatch")
        try:
            validate_summary(receipt.summary)
        except (TypeError, ValueError) as error:
            raise SchedulerError("invalid stop receipt summary") from error
        attempt.update(
            state="stopped",
            terminal_state=receipt.summary["terminal_state"],
            result_state=receipt.summary["result_state"],
            retry_eligibility=receipt.summary["retry_eligibility"],
        )
        return self._attempt_view(attempt)

    def complete_execution(self, attempt_id, *, cleanup_timeout=1.0):
        attempt = self._active(attempt_id)
        receipt = complete_managed_worker(
            attempt["_handle"], cleanup_timeout=cleanup_timeout
        )
        self.complete(attempt_id, receipt)
        return receipt

    def complete(self, attempt_id, receipt):
        attempt = self._active(attempt_id)
        if (
            not isinstance(receipt, CompletionReceipt)
            or receipt.execution_identity != attempt["execution_identity"]
            or receipt.control_token is not attempt["_handle"].control_token
            or receipt.terminal_state not in {"succeeded", "failed"}
        ):
            raise SchedulerError("completion receipt identity mismatch")
        attempt.update(
            state="completed",
            terminal_state=receipt.terminal_state,
            result_state=receipt.terminal_state,
            retry_eligibility="blocked",
        )
        return self._attempt_view(attempt)

    def disable_role(self, role_id, *, mode, **timeouts):
        if mode not in {"graceful", "force"}:
            raise SchedulerError("invalid disable mode")
        role = self._role_internal(role_id)
        if role["labels"] & {"host", "supervisor"}:
            raise SchedulerError("protected label must be transferred before disable")
        active = self.active_attempts(role_id)
        if mode == "graceful" or not active:
            role["enabled"] = False
            return {"mode": mode, "stop_invoked": False}
        receipt = self.force_stop_attempt(active[0], **timeouts)
        role["enabled"] = False
        return {
            "mode": "force",
            "stop_invoked": True,
            "stop_summary": copy.deepcopy(receipt.summary),
            "execution_identity": receipt.execution_identity,
            "observed_pids": receipt.observed_pids,
        }

    def enable_role(self, role_id):
        role = self._role_internal(role_id)
        role["enabled"] = True
        return copy.deepcopy(role)

    def transfer_label(self, label, source_role_id, target_role_id):
        if label not in {"host", "supervisor"}:
            raise SchedulerError("unknown protected label")
        source = self._role_internal(source_role_id)
        target = self._role_internal(target_role_id)
        if (
            label not in source["labels"]
            or label in target["labels"]
            or not target["enabled"]
        ):
            raise SchedulerError("invalid label transfer")
        source["labels"].remove(label)
        target["labels"].add(label)

    def snapshot(self):
        attempts = {key: self._attempt_view(value) for key, value in self._attempts.items()}
        return copy.deepcopy(
            {"roles": self._roles, "attempts": attempts, "dispatch_ledger": self._dispatch_ledger}
        )

    def _active(self, attempt_id):
        try:
            attempt = self._attempts[attempt_id]
        except KeyError as error:
            raise SchedulerError("unknown attempt") from error
        if attempt["state"] != "active":
            raise SchedulerError("attempt is not active")
        return attempt

    @staticmethod
    def _attempt_view(attempt):
        return copy.deepcopy({key: value for key, value in attempt.items() if key != "_handle"})
