"""Offline demo: replay a morning of synthetic events against a fake supergroup.

    python demo/run_demo.py

No network, no token. All names, numbers and addresses are made up.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from topicbot import FakeTelegramClient, InboundEvent, Store, TopicRouter  # noqa: E402

CHAT_ID = -1000000000001


def describe(result) -> str:
    notes = [result.action.upper()]
    if result.topic_created:
        notes.append("new topic")
    if result.topic_renamed:
        notes.append("topic renamed")
    return ", ".join(notes)


def show_group(client: FakeTelegramClient) -> None:
    for topic in client.live_topics():
        print(f"  # {topic.name}  (thread {topic.topic_id})")
        for message_id, text in topic.messages.items():
            edits = topic.edits.get(message_id, 0)
            print(f"    message {message_id}, edited {edits}x")
            for line in text.splitlines():
                print(f"      {line}")


def main() -> None:
    client = FakeTelegramClient()
    router = TopicRouter(client, Store(), CHAT_ID)
    events = [InboundEvent.from_dict(e) for e in json.loads((ROOT / "demo" / "events.json").read_text("utf-8"))]

    print("== 1. Replay 12 inbound events ==")
    for event in events:
        result = router.handle(event)
        print(f"  {event.event_id:<10} {event.kind:<5} {event.status:<10} -> {describe(result)}")

    print()
    print("== 2. What the team sees in the supergroup ==")
    show_group(client)

    print()
    print("== 3. Someone deletes a topic by hand; the next event heals it ==")
    victim = client.live_topics()[0]
    print(f"  deleted topic '{victim.name}' (thread {victim.topic_id})")
    client.delete_topic(victim.topic_id)
    for event in (
        InboundEvent("form-2001", "form", "completed"),
        InboundEvent("text-3002", "text", "received", phone="555-555-0101", body="Thanks, all sorted."),
    ):
        result = router.handle(event)
        print(f"  {event.event_id:<10} {event.kind:<5} {event.status:<10} -> {describe(result)}")
    show_group(client)

    print()
    print("== 4. Bot API calls made ==")
    handled = len(events) + 2
    for method in ("createForumTopic", "editForumTopic", "sendMessage", "editMessageText"):
        print(f"  {method:<17} {client.count(method)}")
    print(f"  {handled} events handled, {client.count('sendMessage')} messages sent, "
          f"{len(client.live_topics())} live topics")


if __name__ == "__main__":
    main()
