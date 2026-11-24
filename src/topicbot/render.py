"""Topic titles and message text. Pure functions, HTML parse mode."""

from __future__ import annotations

import re
from html import escape

from .store import FiledMessage

TOPIC_NAME_LIMIT = 128
MESSAGE_LIMIT = 4096

KIND_LABEL = {"call": "CALL", "text": "TEXT", "form": "FORM"}


def contact_label(customer_key: str) -> str:
    """Human form of a customer key: a dashed phone number or the email."""
    scheme, _, value = customer_key.partition(":")
    if scheme == "phone" and len(value) == 10:
        return f"{value[:3]}-{value[3:6]}-{value[6:]}"
    return value


def topic_title(display_name: str | None, customer_key: str) -> str:
    contact = contact_label(customer_key)
    title = f"{display_name} | {contact}" if display_name else contact
    return title[:TOPIC_NAME_LIMIT]


def render_message(message: FiledMessage, display_name: str | None) -> str:
    """Render the one message that represents an event for its whole life."""
    status = message.statuses[-1] if message.statuses else "unknown"
    who = contact_label(message.customer_key)
    if display_name:
        who = f"{display_name} ({who})"
    lines = [f"<b>{KIND_LABEL.get(message.kind, message.kind.upper())}</b> | {escape(status)}"]
    lines.append(f"From: {escape(who)}")
    if message.occurred_at:
        lines.append(f"At: {escape(message.occurred_at)}")
    footer = []
    if len(message.statuses) > 1:
        footer.append("History: " + escape(" > ".join(message.statuses)))
    footer.append(f"Ref: {escape(message.event_id)}")

    fixed = len("\n".join(lines + footer)) + 2
    body = escape(message.body.strip())
    room = MESSAGE_LIMIT - fixed
    if len(body) > room:
        # Cut to fit, then drop any HTML entity the cut left half written.
        body = re.sub(r"&[#\w]*$", "", body[: max(room - 3, 0)]) + "..."
    if body:
        lines.append(body)
    return "\n".join(lines + footer)
