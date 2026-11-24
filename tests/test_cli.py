import json

from topicbot.__main__ import main


def test_replay_offline_files_events_and_reports(tmp_path, capsys):
    events = [
        {"event_id": "call-1", "kind": "call", "status": "ringing", "phone": "555-555-0101"},
        {"event_id": "call-1", "kind": "call", "status": "missed"},
        {"event_id": "call-2", "kind": "call", "status": "completed"},
    ]
    path = tmp_path / "events.json"
    path.write_text(json.dumps(events), encoding="utf-8")
    assert main(["replay", str(path)]) == 1  # one event could not be routed
    out = capsys.readouterr().out
    assert "sent      call-1" in out and "edited    call-1" in out and "skipped   call-2" in out
    assert "1 customer topics, 1 filed messages, 1 skipped" in out


def test_live_without_credentials_refuses(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "events.json"
    path.write_text("[]", encoding="utf-8")
    assert main(["replay", str(path), "--live"]) == 2
    assert "TELEGRAM_BOT_TOKEN" in capsys.readouterr().err
