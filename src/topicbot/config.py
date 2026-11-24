"""Configuration from the environment, with an optional .env file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: str = ".env") -> None:
    """Minimal KEY=VALUE loader. Existing environment variables win."""
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    bot_token: str
    chat_id: int
    db_path: str

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()
        return cls(
            bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=int(os.environ.get("TELEGRAM_CHAT_ID") or 0),
            db_path=os.environ.get("TOPICBOT_DB", "topicbot.sqlite3"),
        )
