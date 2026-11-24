import pytest

from topicbot import (
    HttpTelegramClient,
    MessageNotFound,
    MessageNotModified,
    RateLimited,
    TelegramError,
    TopicNotFound,
    TopicNotModified,
)

CHAT = -1000000000001


class ScriptedTransport:
    """Stands in for the network: returns canned Bot API envelopes in order."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, url, payload):
        self.requests.append((url, payload))
        return self.responses.pop(0)


def ok(result):
    return {"ok": True, "result": result}


def err(code, description, **parameters):
    return {"ok": False, "error_code": code, "description": description, "parameters": parameters}


def make(*responses):
    transport = ScriptedTransport(*responses)
    sleeps = []
    client = HttpTelegramClient("TEST-TOKEN", transport=transport, sleep=sleeps.append)
    return client, transport, sleeps


def test_token_is_required():
    with pytest.raises(ValueError):
        HttpTelegramClient("")


def test_create_topic_builds_request_and_returns_thread_id():
    client, transport, _ = make(ok({"message_thread_id": 42, "name": "Alex Sample"}))
    assert client.create_forum_topic(CHAT, "Alex Sample") == 42
    url, payload = transport.requests[0]
    assert url == "https://api.telegram.org/botTEST-TOKEN/createForumTopic"
    assert payload == {"chat_id": CHAT, "name": "Alex Sample"}


def test_send_message_targets_the_thread_with_html():
    client, transport, _ = make(ok({"message_id": 77}))
    assert client.send_message(CHAT, 42, "<b>CALL</b>") == 77
    assert transport.requests[0][1] == {
        "chat_id": CHAT, "message_thread_id": 42, "text": "<b>CALL</b>", "parse_mode": "HTML",
    }


def test_edit_calls_use_the_right_methods():
    client, transport, _ = make(ok(True), ok({"message_id": 77}))
    client.edit_forum_topic(CHAT, 42, "New name")
    client.edit_message_text(CHAT, 77, "new text")
    assert [url.rsplit("/", 1)[1] for url, _ in transport.requests] == ["editForumTopic", "editMessageText"]
    assert transport.requests[0][1]["message_thread_id"] == 42
    assert transport.requests[1][1]["message_id"] == 77


@pytest.mark.parametrize(
    "description, expected",
    [
        ("Bad Request: message thread not found", TopicNotFound),
        ("Bad Request: TOPIC_DELETED", TopicNotFound),
        ("Bad Request: TOPIC_NOT_MODIFIED", TopicNotModified),
        ("Bad Request: message to edit not found", MessageNotFound),
        ("Bad Request: message is not modified: specified new message content is the same", MessageNotModified),
    ],
)
def test_error_descriptions_map_to_typed_exceptions(description, expected):
    client, _, _ = make(err(400, description))
    with pytest.raises(expected):
        client.send_message(CHAT, 42, "x")


def test_unrecognised_error_is_a_plain_telegram_error():
    client, _, _ = make(err(403, "Forbidden: bot was kicked from the supergroup chat"))
    with pytest.raises(TelegramError) as info:
        client.send_message(CHAT, 42, "x")
    assert type(info.value) is TelegramError and info.value.code == 403


def test_rate_limit_waits_retry_after_then_succeeds():
    client, transport, sleeps = make(
        err(429, "Too Many Requests: retry after 3", retry_after=3), ok({"message_id": 5})
    )
    assert client.send_message(CHAT, 42, "x") == 5
    assert sleeps == [3.0] and len(transport.requests) == 2


def test_rate_limit_gives_up_after_the_retry_budget():
    limited = err(429, "Too Many Requests: retry after 1", retry_after=1)
    client, transport, sleeps = make(limited, limited, limited)
    with pytest.raises(RateLimited):
        client.send_message(CHAT, 42, "x")
    assert len(transport.requests) == 3 and sleeps == [1.0, 1.0]
