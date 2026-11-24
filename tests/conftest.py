import pytest

from topicbot import FakeTelegramClient, InboundEvent, Store, TopicRouter

CHAT = -1000000000001


@pytest.fixture
def client():
    return FakeTelegramClient()


@pytest.fixture
def store():
    return Store()


@pytest.fixture
def router(client, store):
    return TopicRouter(client, store, CHAT)


@pytest.fixture
def make_event():
    def _make(event_id="call-1", kind="call", status="ringing", phone="555-555-0101", **extra):
        return InboundEvent(event_id=event_id, kind=kind, status=status, phone=phone, **extra)

    return _make
