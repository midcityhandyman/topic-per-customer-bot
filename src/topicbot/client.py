"""Telegram Bot API behind a small interface, with a real and a fake client.

The router only ever talks to the TelegramClient protocol. Four methods are
enough for the whole pattern: create a topic, rename a topic, send into a
topic, edit a message.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


class TelegramError(Exception):
    def __init__(self, description: str, code: int = 400) -> None:
        super().__init__(f"{code}: {description}")
        self.description = description
        self.code = code


class TopicNotFound(TelegramError):
    """The forum topic was deleted or the thread id is no longer valid."""


class MessageNotFound(TelegramError):
    """The message to edit was deleted (or went away with its topic)."""


class MessageNotModified(TelegramError):
    """The edit would not change anything. Telegram treats this as an error."""


class RateLimited(TelegramError):
    def __init__(self, description: str, retry_after: float) -> None:
        super().__init__(description, 429)
        self.retry_after = retry_after


def classify_error(code: int, description: str, retry_after: float | None = None) -> TelegramError:
    """Turn a Bot API error response into the exception the router reacts to."""
    text = description.lower()
    if code == 429:
        return RateLimited(description, float(retry_after or 1))
    if "message is not modified" in text:
        return MessageNotModified(description, code)
    if "message to edit not found" in text or "message_id_invalid" in text:
        return MessageNotFound(description, code)
    if "message thread not found" in text or "topic_deleted" in text or "topic_id_invalid" in text:
        return TopicNotFound(description, code)
    return TelegramError(description, code)


class TelegramClient(Protocol):
    def create_forum_topic(self, chat_id: int, name: str) -> int:
        """Create a topic and return its message_thread_id."""

    def edit_forum_topic(self, chat_id: int, topic_id: int, name: str) -> None: ...

    def send_message(self, chat_id: int, topic_id: int, text: str) -> int:
        """Send into a topic and return the new message_id."""

    def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None: ...


Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


def urllib_transport(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST JSON and return the decoded Bot API envelope, also on 4xx."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(raw)
        except ValueError:
            return {"ok": False, "error_code": exc.code, "description": raw or str(exc)}


class HttpTelegramClient:
    """Real client. Standard library only; the transport is injectable for tests."""

    def __init__(
        self,
        token: str,
        *,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        max_rate_limit_retries: int = 2,
        base_url: str = "https://api.telegram.org",
    ) -> None:
        if not token:
            raise ValueError("a bot token is required for the live client")
        self._url = f"{base_url}/bot{token}/"
        self._transport = transport
        self._sleep = sleep
        self._retries = max_rate_limit_retries

    def _call(self, method: str, payload: dict[str, Any]) -> Any:
        attempt = 0
        while True:
            envelope = self._transport(self._url + method, payload)
            if envelope.get("ok"):
                return envelope.get("result")
            error = classify_error(
                int(envelope.get("error_code", 400)),
                str(envelope.get("description", "unknown error")),
                (envelope.get("parameters") or {}).get("retry_after"),
            )
            if isinstance(error, RateLimited) and attempt < self._retries:
                attempt += 1
                self._sleep(error.retry_after)
                continue
            raise error

    def create_forum_topic(self, chat_id: int, name: str) -> int:
        result = self._call("createForumTopic", {"chat_id": chat_id, "name": name})
        return int(result["message_thread_id"])

    def edit_forum_topic(self, chat_id: int, topic_id: int, name: str) -> None:
        self._call(
            "editForumTopic",
            {"chat_id": chat_id, "message_thread_id": topic_id, "name": name},
        )

    def send_message(self, chat_id: int, topic_id: int, text: str) -> int:
        result = self._call(
            "sendMessage",
            {
                "chat_id": chat_id,
                "message_thread_id": topic_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )
        return int(result["message_id"])

    def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        self._call(
            "editMessageText",
            {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"},
        )


@dataclass
class FakeTopic:
    topic_id: int
    name: str
    messages: dict[int, str] = field(default_factory=dict)
    edits: dict[int, int] = field(default_factory=dict)
    deleted: bool = False


class FakeTelegramClient:
    """In-memory supergroup that fails the same ways the real API does.

    It raises TopicNotFound for deleted topics, MessageNotFound for deleted
    messages and MessageNotModified for no-op edits, so the recovery paths in
    the router are exercised without a network.
    """

    def __init__(self) -> None:
        self.topics: dict[int, FakeTopic] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id = 1

    def _take_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _live_topic(self, topic_id: int) -> FakeTopic:
        topic = self.topics.get(topic_id)
        if topic is None or topic.deleted:
            raise TopicNotFound("Bad Request: message thread not found")
        return topic

    def _topic_of_message(self, message_id: int) -> FakeTopic:
        for topic in self.topics.values():
            if not topic.deleted and message_id in topic.messages:
                return topic
        raise MessageNotFound("Bad Request: message to edit not found")

    # TelegramClient interface
    def create_forum_topic(self, chat_id: int, name: str) -> int:
        self.calls.append(("createForumTopic", {"chat_id": chat_id, "name": name}))
        topic_id = self._take_id()  # the service message id doubles as the thread id
        self.topics[topic_id] = FakeTopic(topic_id, name)
        return topic_id

    def edit_forum_topic(self, chat_id: int, topic_id: int, name: str) -> None:
        self.calls.append(("editForumTopic", {"chat_id": chat_id, "topic_id": topic_id, "name": name}))
        self._live_topic(topic_id).name = name

    def send_message(self, chat_id: int, topic_id: int, text: str) -> int:
        self.calls.append(("sendMessage", {"chat_id": chat_id, "topic_id": topic_id, "text": text}))
        topic = self._live_topic(topic_id)
        message_id = self._take_id()
        topic.messages[message_id] = text
        return message_id

    def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        self.calls.append(("editMessageText", {"chat_id": chat_id, "message_id": message_id, "text": text}))
        topic = self._topic_of_message(message_id)
        if topic.messages[message_id] == text:
            raise MessageNotModified("Bad Request: message is not modified")
        topic.messages[message_id] = text
        topic.edits[message_id] = topic.edits.get(message_id, 0) + 1

    # Helpers for tests and the demo: things a human does in the group.
    def delete_topic(self, topic_id: int) -> None:
        self.topics[topic_id].deleted = True

    def delete_message(self, message_id: int) -> None:
        del self._topic_of_message(message_id).messages[message_id]

    def live_topics(self) -> list[FakeTopic]:
        return [t for t in self.topics.values() if not t.deleted]

    def count(self, method: str) -> int:
        return sum(1 for name, _ in self.calls if name == method)
