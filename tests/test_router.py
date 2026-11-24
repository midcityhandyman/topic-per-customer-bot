import threading

import pytest

from topicbot import FakeTelegramClient, InboundEvent, Store, TopicRouter, UnroutableEvent
from topicbot.render import render_message

from conftest import CHAT


def test_first_event_creates_topic_and_sends(router, client, make_event):
    result = router.handle(make_event(name="Alex Sample", body="Leaking tap"))
    assert result.action == "sent" and result.topic_created
    [topic] = client.live_topics()
    assert topic.name == "Alex Sample | 555-555-0101"
    assert "Leaking tap" in topic.messages[result.message_id]


def test_second_event_reuses_topic_whatever_the_phone_format(router, client, make_event):
    first = router.handle(make_event("call-1"))
    second = router.handle(make_event("text-1", kind="text", status="received", phone="+1 (555) 555-0101"))
    assert second.topic_id == first.topic_id and not second.topic_created
    assert client.count("createForumTopic") == 1
    assert len(client.live_topics()[0].messages) == 2


def test_different_customers_get_different_topics(router, client, make_event):
    a = router.handle(make_event("call-1", phone="555-555-0101"))
    b = router.handle(make_event("call-2", phone="555-555-0102"))
    c = router.handle(InboundEvent("form-1", "form", "new", email="sam@example.com"))
    assert len({a.topic_id, b.topic_id, c.topic_id}) == 3


def test_status_change_edits_the_same_message(router, client, make_event):
    sent = router.handle(make_event(status="ringing"))
    edited = router.handle(make_event(status="missed"))
    assert edited.action == "edited" and edited.message_id == sent.message_id
    assert client.count("sendMessage") == 1 and client.count("editMessageText") == 1
    text = client.live_topics()[0].messages[sent.message_id]
    assert text.startswith("<b>CALL</b> | missed")
    assert "History: ringing &gt; missed" in text


def test_duplicate_delivery_makes_no_api_call(router, client, make_event):
    router.handle(make_event(status="ringing"))
    before = len(client.calls)
    assert router.handle(make_event(status="ringing")).action == "unchanged"
    assert len(client.calls) == before


def test_status_only_callback_routes_by_event_id(router, client, make_event):
    sent = router.handle(make_event("call-7", body="Voicemail left"))
    update = router.handle(InboundEvent("call-7", "call", "completed"))
    assert update.action == "edited" and update.topic_id == sent.topic_id
    text = client.live_topics()[0].messages[sent.message_id]
    assert "Voicemail left" in text, "the body from the first event survives an update without one"


def test_unknown_event_without_contact_is_unroutable(router, client):
    with pytest.raises(UnroutableEvent):
        router.handle(InboundEvent("call-404", "call", "completed"))
    assert client.calls == []


def test_topic_is_renamed_once_the_name_is_known(router, client, make_event):
    router.handle(make_event("call-1"))
    assert client.live_topics()[0].name == "555-555-0101"
    result = router.handle(make_event("form-1", kind="form", status="new", name="Alex Sample"))
    assert result.topic_renamed
    assert client.live_topics()[0].name == "Alex Sample | 555-555-0101"
    router.handle(make_event("text-1", kind="text", status="received"))
    assert client.count("editForumTopic") == 1, "an event without a name must not rename it back"
    assert client.live_topics()[0].name == "Alex Sample | 555-555-0101"


def test_deleted_topic_is_recreated_on_next_event(router, client, store, make_event):
    first = router.handle(make_event("call-1"))
    client.delete_topic(first.topic_id)
    second = router.handle(make_event("text-1", kind="text", status="received"))
    assert second.action == "sent" and second.topic_created
    assert second.topic_id != first.topic_id
    assert store.get_customer("phone:5555550101").topic_id == second.topic_id
    assert len(client.live_topics()) == 1


def test_edit_after_topic_deleted_resends_into_new_topic(router, client, make_event):
    first = router.handle(make_event(status="ringing"))
    client.delete_topic(first.topic_id)
    again = router.handle(make_event(status="answered"))
    assert again.action == "resent" and again.topic_created
    [topic] = client.live_topics()
    assert list(topic.messages) == [again.message_id]
    assert router.handle(make_event(status="completed")).action == "edited"


def test_deleted_message_is_resent_in_same_topic(router, client, make_event):
    first = router.handle(make_event(status="ringing"))
    client.delete_message(first.message_id)
    again = router.handle(make_event(status="missed"))
    assert again.action == "resent"
    assert again.topic_id == first.topic_id and again.message_id != first.message_id
    assert client.count("createForumTopic") == 1


def test_not_modified_from_telegram_is_swallowed(router, client, store, make_event):
    sent = router.handle(make_event(status="ringing"))
    # Simulate a crash after the edit reached Telegram but before it was stored:
    # Telegram already holds the new text, the store still holds the old one.
    filed = store.get_message("call-1")
    topic = client.live_topics()[0]
    topic.messages[sent.message_id] = render_message(filed.with_update("missed", ""), None)
    result = router.handle(make_event(status="missed"))
    assert result.action == "unchanged"
    assert store.get_message("call-1").statuses == ("ringing", "missed")


def test_state_survives_a_restart(tmp_path, make_event):
    db = str(tmp_path / "bot.sqlite3")
    client = FakeTelegramClient()
    store = Store(db)
    first = TopicRouter(client, store, CHAT).handle(make_event(status="ringing"))
    store.close()

    restarted = TopicRouter(client, Store(db), CHAT)
    result = restarted.handle(make_event(status="completed"))
    assert result.action == "edited" and result.message_id == first.message_id
    assert client.count("createForumTopic") == 1


def test_concurrent_first_events_create_one_topic(router, client, make_event):
    threads = [
        threading.Thread(target=router.handle, args=(make_event(f"text-{i}", kind="text", status="received"),))
        for i in range(12)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert client.count("createForumTopic") == 1
    assert len(client.live_topics()[0].messages) == 12
