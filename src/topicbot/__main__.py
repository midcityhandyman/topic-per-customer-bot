"""Command line: replay a JSON file of events through the router.

    python -m topicbot replay demo/events.json          offline, fake client
    python -m topicbot replay demo/events.json --live   real Bot API, needs .env
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import FakeTelegramClient, HttpTelegramClient
from .config import Config
from .events import InboundEvent
from .router import TopicRouter, UnroutableEvent
from .store import Store

FAKE_CHAT_ID = -1000000000001


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="topicbot", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    replay = sub.add_parser("replay", help="file every event in a JSON array")
    replay.add_argument("events", type=Path)
    replay.add_argument("--live", action="store_true", help="call the real Telegram Bot API")
    replay.add_argument("--db", help="SQLite path (default: in memory offline, TOPICBOT_DB live)")
    args = parser.parse_args(argv)

    if args.live:
        config = Config.from_env()
        if not config.bot_token or not config.chat_id:
            print("--live needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (see .env.example)", file=sys.stderr)
            return 2
        client, chat_id = HttpTelegramClient(config.bot_token), config.chat_id
        store = Store(args.db or config.db_path)
    else:
        client, chat_id = FakeTelegramClient(), FAKE_CHAT_ID
        store = Store(args.db or ":memory:")

    router = TopicRouter(client, store, chat_id)
    failures = 0
    for raw in json.loads(args.events.read_text(encoding="utf-8")):
        try:
            result = router.handle(InboundEvent.from_dict(raw))
        except (UnroutableEvent, ValueError) as exc:
            failures += 1
            print(f"skipped   {raw.get('event_id', '?')}: {exc}")
            continue
        print(f"{result.action:<9} {raw['event_id']} -> topic {result.topic_id}, message {result.message_id}")
    customers, messages = store.counts()
    print(f"{customers} customer topics, {messages} filed messages, {failures} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
