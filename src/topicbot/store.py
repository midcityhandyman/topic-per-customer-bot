"""SQLite map of customer to topic and event to message.

This is the only state the bot keeps. Lose it and the next event for every
customer opens a second topic, so in production it belongs on a real disk.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_key TEXT PRIMARY KEY,
    topic_id     INTEGER NOT NULL,
    topic_name   TEXT NOT NULL,
    display_name TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    event_id     TEXT PRIMARY KEY,
    customer_key TEXT NOT NULL REFERENCES customers(customer_key),
    message_id   INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    body         TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    statuses     TEXT NOT NULL,
    text         TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class Customer:
    customer_key: str
    topic_id: int
    topic_name: str
    display_name: str | None = None


@dataclass(frozen=True)
class FiledMessage:
    """What the bot last posted for one event, enough to re-render and compare."""

    event_id: str
    customer_key: str
    kind: str
    body: str = ""
    occurred_at: str = ""
    statuses: tuple[str, ...] = field(default_factory=tuple)
    message_id: int = 0
    text: str = ""

    def with_update(self, status: str, body: str) -> "FiledMessage":
        """Fold a later event for the same event_id into this record."""
        statuses = self.statuses
        if status and (not statuses or statuses[-1] != status):
            statuses = statuses + (status,)
        return replace(self, statuses=statuses, body=body or self.body)


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def get_customer(self, customer_key: str) -> Customer | None:
        row = self._db.execute(
            "SELECT customer_key, topic_id, topic_name, display_name FROM customers WHERE customer_key = ?",
            (customer_key,),
        ).fetchone()
        return Customer(*row) if row else None

    def save_customer(self, customer: Customer) -> None:
        self._db.execute(
            "INSERT INTO customers (customer_key, topic_id, topic_name, display_name) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(customer_key) DO UPDATE SET topic_id = excluded.topic_id, "
            "topic_name = excluded.topic_name, display_name = excluded.display_name",
            (customer.customer_key, customer.topic_id, customer.topic_name, customer.display_name),
        )
        self._db.commit()

    def get_message(self, event_id: str) -> FiledMessage | None:
        row = self._db.execute(
            "SELECT event_id, customer_key, kind, body, occurred_at, statuses, message_id, text "
            "FROM messages WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if not row:
            return None
        return FiledMessage(row[0], row[1], row[2], row[3], row[4], tuple(json.loads(row[5])), row[6], row[7])

    def save_message(self, m: FiledMessage) -> None:
        self._db.execute(
            "INSERT INTO messages (event_id, customer_key, message_id, kind, body, occurred_at, statuses, text) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(event_id) DO UPDATE SET message_id = excluded.message_id, body = excluded.body, "
            "statuses = excluded.statuses, text = excluded.text",
            (m.event_id, m.customer_key, m.message_id, m.kind, m.body, m.occurred_at,
             json.dumps(list(m.statuses)), m.text),
        )
        self._db.commit()

    def counts(self) -> tuple[int, int]:
        customers = self._db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        messages = self._db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return customers, messages
