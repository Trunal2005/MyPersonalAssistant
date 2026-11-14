"""Timestamps on chat messages: saved with each message and shown in its bubble."""
import re

from conftest import saved_history, send
from jugnu_core import message_time_text

TIME = r"^\d{2}:\d{2} (AM|PM)$"


def test_message_time_text_format():
    assert re.match(TIME, message_time_text())


def test_existing_history_files_load_without_errors(make_window):
    app = make_window([{"id": "chat-legacy-1", "title": "Old conversation", "messages": [
        {"role": "user", "content": "How does history work?"},
        {"role": "assistant", "content": "It saves chats in JSON."}]}])
    assert len(app.chats) == 1 and app.chats[0]["title"] == "Old conversation"
    assert all("time" not in msg for msg in app.chats[0]["messages"])
    assert all(bubble.time_label is None for bubble in app.bubbles)


def test_history_with_time_loads_and_shows_time(make_window):
    app = make_window([{"id": "chat-timed-1", "title": "Timed Chat", "messages": [
        {"role": "user", "content": "What is the time?", "time": "09:30 AM"},
        {"role": "assistant", "content": "It is morning.", "time": "09:31 AM"}]}])
    assert [m["time"] for m in app.chats[0]["messages"]] == ["09:30 AM", "09:31 AM"]
    assert [b.time_label.text() for b in app.bubbles] == ["09:30 AM", "09:31 AM"]


def test_malformed_time_in_history_is_handled_gracefully(make_window):
    app = make_window([{"id": "chat-malformed-time", "title": "Chat", "messages": [
        {"role": "user", "content": "hi", "time": ""},
        {"role": "assistant", "content": "hello", "time": 12345},
        {"role": "user", "content": "test", "time": None},
        {"role": "assistant", "content": "valid", "time": "05:12 PM"}]}])
    msgs = app.chats[0]["messages"]
    assert ["time" in m for m in msgs] == [False, False, False, True]
    assert [b.time_label.text() if b.time_label else None for b in app.bubbles] == [None, None, None, "05:12 PM"]


def test_new_messages_save_time_to_history(qtbot, window, monkeypatch):
    import jugnu_core
    monkeypatch.setattr(jugnu_core, "ask_ollama", lambda chat, language: ("Hello! How can I help you?", False))
    send(qtbot, window, "Hello Jugnu!")
    qtbot.waitUntil(lambda: not window.busy, timeout=3000)
    user_msg, assistant_msg = window.current_chat()["messages"]
    assert re.match(TIME, user_msg["time"]) and re.match(TIME, assistant_msg["time"])
    saved = saved_history(window)[0]["messages"]
    assert saved[0]["time"] == user_msg["time"]
    assert saved[-1]["time"] == assistant_msg["time"]


def test_bubble_shows_the_timestamp(window):
    bubble = window.add_bubble("user", "Hello world", timestamp="02:15 PM")
    assert bubble.time_label.text() == "02:15 PM"
    assert bubble.time_label.objectName() == "bubbleTime"  # muted colour comes from the stylesheet


def test_bubble_without_timestamp_has_no_time_label(window):
    bubble = window.add_bubble("user", "No timestamp message", timestamp=None)
    assert bubble.time_label is None
    assert bubble.name_label.text() == window.t("you_label")


def test_switching_between_old_and_new_chats_renders_correctly(window):
    window.chats = [
        {"id": "old-chat", "title": "Old Chat", "messages": [
            {"role": "user", "content": "Old question"},
            {"role": "assistant", "content": "Old answer"}]},
        {"id": "new-chat", "title": "New Chat", "messages": [
            {"role": "user", "content": "New question", "time": "11:20 AM"},
            {"role": "assistant", "content": "New answer", "time": "11:21 AM"}]},
    ]
    window.draft_chat = None
    window.current_id = "old-chat"
    window.display_chat()
    assert [b.time_label for b in window.bubbles] == [None, None]
    window.current_id = "new-chat"
    window.display_chat()
    assert [b.time_label.text() for b in window.bubbles] == ["11:20 AM", "11:21 AM"]


def test_calculator_local_reply_has_timestamp(qtbot, window):
    send(qtbot, window, "Calculate 15 + 25")
    user_msg, assistant_msg = window.current_chat()["messages"]
    assert re.match(TIME, user_msg["time"]) and re.match(TIME, assistant_msg["time"])
    assert "40" in assistant_msg["content"]
    assert window.bubbles[-1].time_label.text() == assistant_msg["time"]
