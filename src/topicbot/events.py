"""Inbound events (call, text, form) and how a customer is identified."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

KINDS = ("call", "text", "form")


def normalize_phone(raw: str | None) -> str | None:
    """Reduce a phone number to bare digits so formatting never splits a customer.

    A leading North American country code is dropped. Returns None when there
    are too few digits to be a phone number.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) >= 7 else None


def normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    email = raw.strip().lower()
    return email if "@" in email else None


@dataclass(frozen=True)
class InboundEvent:
    """One thing that happened, or one status change to a thing that happened.

    event_id is the id the source system gives the call, text or form. Every
    status update for the same call carries the same event_id; that is what
    lets the bot edit the existing message instead of posting another one.
    """

    event_id: str
    kind: str
    status: str
    phone: str | None = None
    email: str | None = None
    name: str | None = None
    body: str = ""
    occurred_at: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id is required")
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}, got {self.kind!r}")

    @property
    def customer_key(self) -> str | None:
        """Stable identity for the customer: phone first, then email."""
        phone = normalize_phone(self.phone)
        if phone:
            return f"phone:{phone}"
        email = normalize_email(self.email)
        if email:
            return f"email:{email}"
        return None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InboundEvent":
        return cls(
            event_id=str(data.get("event_id", "")),
            kind=str(data.get("kind", "")),
            status=str(data.get("status", "")),
            phone=data.get("phone") or None,
            email=data.get("email") or None,
            name=(data.get("name") or "").strip() or None,
            body=str(data.get("body") or ""),
            occurred_at=str(data.get("occurred_at") or ""),
        )
