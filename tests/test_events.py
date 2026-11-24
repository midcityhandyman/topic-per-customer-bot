import pytest

from topicbot import InboundEvent, normalize_phone
from topicbot.render import contact_label, render_message, topic_title
from topicbot.store import FiledMessage


@pytest.mark.parametrize(
    "raw",
    ["555-555-0101", "(555) 555-0101", "+1 555 555 0101", "1.555.555.0101", "5555550101"],
)
def test_phone_formats_collapse_to_one_identity(raw):
    assert normalize_phone(raw) == "5555550101"


def test_too_short_or_missing_phone_is_none():
    assert normalize_phone("0101") is None
    assert normalize_phone(None) is None


def test_customer_key_prefers_phone_then_email():
    both = InboundEvent("e1", "form", "new", phone="555-555-0102", email="Sam@Example.com")
    assert both.customer_key == "phone:5555550102"
    only_email = InboundEvent("e2", "form", "new", email=" Sam@Example.com ")
    assert only_email.customer_key == "email:sam@example.com"
    assert InboundEvent("e3", "call", "ringing").customer_key is None


def test_unknown_kind_and_missing_id_are_rejected():
    with pytest.raises(ValueError):
        InboundEvent("e1", "fax", "new", phone="555-555-0101")
    with pytest.raises(ValueError):
        InboundEvent("", "call", "new", phone="555-555-0101")


def test_from_dict_tolerates_missing_optional_fields():
    event = InboundEvent.from_dict({"event_id": "t-9", "kind": "text", "status": "received", "name": "  "})
    assert event.name is None and event.body == "" and event.phone is None


def test_titles_and_labels():
    assert contact_label("phone:5555550101") == "555-555-0101"
    assert topic_title("Alex Sample", "phone:5555550101") == "Alex Sample | 555-555-0101"
    assert topic_title(None, "email:sam@example.com") == "sam@example.com"
    assert len(topic_title("N" * 300, "phone:5555550101")) == 128


def test_render_escapes_html_and_shows_history():
    message = FiledMessage("c1", "phone:5555550101", "call", body="<b>hi</b> & bye",
                           occurred_at="2026-03-02 09:14", statuses=("ringing", "missed"))
    text = render_message(message, "Alex <Sample>")
    assert text.splitlines()[0] == "<b>CALL</b> | missed"
    assert "Alex &lt;Sample&gt; (555-555-0101)" in text
    assert "&lt;b&gt;hi&lt;/b&gt; &amp; bye" in text
    assert "History: ringing &gt; missed" in text


def test_render_truncates_to_telegram_limit_without_broken_entities():
    message = FiledMessage("c1", "phone:5555550101", "form", body="&" * 9000, statuses=("new",))
    text = render_message(message, None)
    assert len(text) <= 4096
    assert "..." in text and "&amp..." not in text and "&..." not in text
    assert text.endswith("Ref: c1")
