"""The pattern itself: find or create the customer's topic, then send or edit."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace

from .client import MessageNotFound, MessageNotModified, TelegramClient, TopicNotFound, TopicNotModified
from .events import InboundEvent
from .render import render_message, topic_title
from .store import Customer, FiledMessage, Store


class UnroutableEvent(ValueError):
    """No phone, no email, and no earlier event with the same event_id."""


@dataclass(frozen=True)
class FilingResult:
    action: str  # sent | edited | unchanged | resent
    topic_id: int
    message_id: int
    topic_created: bool = False
    topic_renamed: bool = False


class TopicRouter:
    def __init__(self, client: TelegramClient, store: Store, chat_id: int) -> None:
        self.client = client
        self.store = store
        self.chat_id = chat_id
        # One lock for the whole router: two webhooks for a brand new customer
        # must not both create a topic. Simple, and fine at small-team volume.
        self._lock = threading.Lock()

    def handle(self, event: InboundEvent) -> FilingResult:
        with self._lock:
            filed = self.store.get_message(event.event_id)
            # A known event stays with the customer it was first filed under,
            # so bare status callbacks (no phone, no email) still route.
            key = filed.customer_key if filed else event.customer_key
            if key is None:
                raise UnroutableEvent(f"event {event.event_id} has no phone or email and is not known")

            customer, created, renamed = self._ensure_topic(key, event.name)

            if filed is None:
                draft = FiledMessage(
                    event_id=event.event_id,
                    customer_key=key,
                    kind=event.kind,
                    body=event.body,
                    occurred_at=event.occurred_at,
                    statuses=(event.status,) if event.status else (),
                )
                action = "sent"
            else:
                draft = filed.with_update(event.status, event.body)
                action = "edited"

            text = render_message(draft, customer.display_name)

            if filed is not None and text == filed.text:
                return FilingResult("unchanged", customer.topic_id, filed.message_id, created, renamed)

            message_id = filed.message_id if filed else 0
            if filed is not None:
                try:
                    self.client.edit_message_text(self.chat_id, filed.message_id, text)
                except MessageNotModified:
                    action = "unchanged"
                except MessageNotFound:
                    # Someone deleted the message (or its whole topic). Put it back.
                    filed = None
                    action = "resent"
            if filed is None:
                customer, message_id, recreated = self._send(customer, text)
                created = created or recreated

            self.store.save_message(replace(draft, message_id=message_id, text=text))
            return FilingResult(action, customer.topic_id, message_id, created, renamed)

    def _ensure_topic(self, key: str, event_name: str | None) -> tuple[Customer, bool, bool]:
        """Return the customer's topic, creating or renaming it when needed."""
        customer = self.store.get_customer(key)
        if customer is None:
            title = topic_title(event_name, key)
            topic_id = self.client.create_forum_topic(self.chat_id, title)
            customer = Customer(key, topic_id, title, event_name)
            self.store.save_customer(customer)
            return customer, True, False

        name = event_name or customer.display_name
        title = topic_title(name, key)
        if title == customer.topic_name:
            return customer, False, False
        # We learned the name (or a better one) after the topic was opened.
        renamed_customer = replace(customer, topic_name=title, display_name=name)
        try:
            self.client.edit_forum_topic(self.chat_id, customer.topic_id, title)
        except TopicNotFound:
            return self._recreate_topic(renamed_customer), True, False
        except TopicNotModified:
            # An earlier rename reached Telegram but was never stored (a crash
            # in between). Record it, or every later event would fail here.
            self.store.save_customer(renamed_customer)
            return renamed_customer, False, False
        self.store.save_customer(renamed_customer)
        return renamed_customer, False, True

    def _recreate_topic(self, customer: Customer) -> Customer:
        topic_id = self.client.create_forum_topic(self.chat_id, customer.topic_name)
        customer = replace(customer, topic_id=topic_id)
        self.store.save_customer(customer)
        return customer

    def _send(self, customer: Customer, text: str) -> tuple[Customer, int, bool]:
        """Send into the topic; if a human deleted the topic, open a new one once."""
        try:
            return customer, self.client.send_message(self.chat_id, customer.topic_id, text), False
        except TopicNotFound:
            customer = self._recreate_topic(customer)
            return customer, self.client.send_message(self.chat_id, customer.topic_id, text), True
