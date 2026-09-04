import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS roles (
        role_id TEXT PRIMARY KEY,
        role_kind TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS delegations (
        delegation_id TEXT PRIMARY KEY,
        sender_role_id TEXT NOT NULL REFERENCES roles(role_id),
        target_role_id TEXT NOT NULL REFERENCES roles(role_id),
        completion_state TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS execution_attempts (
        attempt_id TEXT PRIMARY KEY,
        delegation_id TEXT NOT NULL REFERENCES delegations(delegation_id),
        role_id TEXT NOT NULL REFERENCES roles(role_id),
        dispatch_state TEXT NOT NULL CHECK (dispatch_state IN ('prepared', 'accepted')),
        terminal_state TEXT CHECK (
            terminal_state IS NULL OR terminal_state IN ('succeeded', 'failed')
        ),
        recovery_state TEXT CHECK (
            recovery_state IS NULL OR recovery_state = 'result_unknown'
        ),
        CHECK (
            dispatch_state = 'accepted'
            OR (terminal_state IS NULL AND recovery_state IS NULL)
        ),
        CHECK (terminal_state IS NULL OR recovery_state IS NULL)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_events (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_kind TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        UNIQUE(event_kind, entity_id)
    )
    """,
)


class RecoveryStore:
    def __init__(self, database_path):
        self.database_path = Path(database_path)

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize_schema(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)

    def add_role(self, role_id, role_kind):
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO roles(role_id, role_kind) VALUES (?, ?)",
                (role_id, role_kind),
            )
            self._append_event(connection, "role_created", role_id)

    def add_delegation(self, delegation_id, sender_role_id, target_role_id):
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO delegations(
                    delegation_id, sender_role_id, target_role_id, completion_state
                ) VALUES (?, ?, ?, NULL)
                """,
                (delegation_id, sender_role_id, target_role_id),
            )
            self._append_event(connection, "delegation_created", delegation_id)

    def add_attempt(self, attempt_id, delegation_id, role_id):
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO execution_attempts(
                    attempt_id, delegation_id, role_id,
                    dispatch_state, terminal_state, recovery_state
                ) VALUES (?, ?, ?, 'prepared', NULL, NULL)
                """,
                (attempt_id, delegation_id, role_id),
            )
            self._append_event(connection, "attempt_created", attempt_id)

    def record_acceptance(self, attempt_id):
        with self._transaction() as connection:
            attempt = self._get_attempt(connection, attempt_id)
            if attempt["dispatch_state"] == "accepted":
                return False
            connection.execute(
                "UPDATE execution_attempts SET dispatch_state = 'accepted' WHERE attempt_id = ?",
                (attempt_id,),
            )
            self._append_event(connection, "adapter_accepted", attempt_id)
            return True

    def record_terminal(self, attempt_id, terminal_state):
        if terminal_state not in {"succeeded", "failed"}:
            raise ValueError("terminal state must be succeeded or failed")
        with self._transaction() as connection:
            attempt = self._get_attempt(connection, attempt_id)
            if attempt["dispatch_state"] != "accepted":
                raise ValueError("only an accepted attempt can gain a terminal state")
            current = attempt["terminal_state"]
            if current is not None:
                if current != terminal_state:
                    raise ValueError("terminal state cannot be changed")
                return False
            if attempt["recovery_state"] is not None:
                raise ValueError("recovered attempt cannot gain a terminal state")
            connection.execute(
                "UPDATE execution_attempts SET terminal_state = ? WHERE attempt_id = ?",
                (terminal_state, attempt_id),
            )
            self._append_event(connection, "execution_terminal", attempt_id)
            return True

    def record_recovery_unknown(self, attempt_id):
        with self._transaction() as connection:
            attempt = self._get_attempt(connection, attempt_id)
            current = attempt["recovery_state"]
            if current is not None:
                if current != "result_unknown":
                    raise ValueError("recovery state cannot be changed")
                return False
            if attempt["dispatch_state"] != "accepted":
                raise ValueError("only an accepted attempt can become result_unknown")
            if attempt["terminal_state"] is not None:
                raise ValueError("terminal attempt cannot become result_unknown")
            connection.execute(
                """
                UPDATE execution_attempts
                SET recovery_state = 'result_unknown'
                WHERE attempt_id = ?
                """,
                (attempt_id,),
            )
            self._append_event(
                connection, "execution_recovered_unknown", attempt_id
            )
            return True

    def snapshot(self):
        connection = self._connect()
        try:
            roles = self._rows(
                connection,
                "SELECT role_id, role_kind FROM roles ORDER BY role_id",
            )
            delegations = self._rows(
                connection,
                """
                SELECT delegation_id, sender_role_id, target_role_id, completion_state
                FROM delegations ORDER BY delegation_id
                """,
            )
            attempts = self._rows(
                connection,
                """
                SELECT attempt_id, delegation_id, role_id,
                       dispatch_state, terminal_state, recovery_state
                FROM execution_attempts ORDER BY attempt_id
                """,
            )
            events = self._rows(
                connection,
                """
                SELECT sequence, event_kind, entity_id
                FROM fact_events ORDER BY sequence
                """,
            )
        finally:
            connection.close()
        return {
            "roles": roles,
            "delegations": delegations,
            "attempts": attempts,
            "events": events,
            "counts": {
                "messages": 0,
                "agent_results": 0,
                "acceptances": sum(
                    event["event_kind"] == "adapter_accepted" for event in events
                ),
            },
        }

    @staticmethod
    def _append_event(connection, event_kind, entity_id):
        connection.execute(
            "INSERT INTO fact_events(event_kind, entity_id) VALUES (?, ?)",
            (event_kind, entity_id),
        )

    @staticmethod
    def _get_attempt(connection, attempt_id):
        attempt = connection.execute(
            "SELECT * FROM execution_attempts WHERE attempt_id = ?", (attempt_id,)
        ).fetchone()
        if attempt is None:
            raise KeyError(attempt_id)
        return attempt

    @staticmethod
    def _rows(connection, query):
        return [dict(row) for row in connection.execute(query).fetchall()]
