"""One forum topic per customer; inbound events are filed and edited in place."""

from .client import (
    FakeTelegramClient,
    HttpTelegramClient,
    MessageNotFound,
    MessageNotModified,
    RateLimited,
    TelegramClient,
    TelegramError,
    TopicNotFound,
)
from .events import InboundEvent, normalize_phone
from .router import FilingResult, TopicRouter, UnroutableEvent
from .store import Store

__all__ = [
    "FakeTelegramClient",
    "FilingResult",
    "HttpTelegramClient",
    "InboundEvent",
    "MessageNotFound",
    "MessageNotModified",
    "RateLimited",
    "Store",
    "TelegramClient",
    "TelegramError",
    "TopicNotFound",
    "TopicRouter",
    "UnroutableEvent",
    "normalize_phone",
]
