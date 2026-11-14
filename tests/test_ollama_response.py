"""The window's Ollama requests: run on a QThread, with local HTTP fakes instead of a server."""
import json
import threading
from unittest.mock import patch

import pytest
import requests

import jugnu_core
from conftest import send
from strings import get_string


def make_response(body, status=200):
    response = requests.Response()
    response.url = jugnu_core.OLLAMA_URL
    response.status_code = status
    response._content = body
    return response


def wait_until_idle(qtbot, app):
    qtbot.waitUntil(lambda: not app.busy, timeout=3000)


INVALID_BODIES = [
    b'{"message":null}',
    b'[]',
    b'"wrong root"',
    b'{}',
    b'{"message":[]}',
    b'{"message":{}}',
    b'{"message":{"content":null}}',
    b'{"message":{"content":42}}',
    b'{"message":{"content":true}}',
]


@pytest.mark.parametrize("body", INVALID_BODIES)
def test_invalid_response_recovers_and_accepts_follow_up(qtbot, window, body):
    valid = make_response(b'{"message":{"role":"assistant","content":"Recovered reply"}}')
    with patch.object(jugnu_core.requests, "post", side_effect=[make_response(body), valid]) as post:
        send(qtbot, window, "First prompt")
        wait_until_idle(qtbot, window)
        assert window.send_btn.isEnabled()
        assert "Thinking" not in window.status.text()
        messages = window.current_chat()["messages"]
        assert [m["content"] for m in messages] == [
            "First prompt", get_string(window.language, "error_invalid_response")]

        send(qtbot, window, "Second prompt")
        wait_until_idle(qtbot, window)
        assert window.current_chat()["messages"][-1]["content"] == "Recovered reply"
        assert len(window.current_chat()["messages"]) == 4
        assert post.call_count == 2


def test_new_chat_can_send_after_invalid_response(qtbot, window):
    invalid = make_response(b'{"message":null}')
    valid = make_response(b'{"message":{"content":"New chat reply"}}')
    with patch.object(jugnu_core.requests, "post", side_effect=[invalid, valid]) as post:
        send(qtbot, window, "Original prompt")
        wait_until_idle(qtbot, window)
        original_chat = window.current_chat()
        window.new_chat()
        send(qtbot, window, "New chat prompt")
        wait_until_idle(qtbot, window)
    assert post.call_count == 2
    assert window.send_btn.isEnabled()
    assert original_chat["messages"][0]["content"] == "Original prompt"
    assert window.current_chat()["messages"][-1]["content"] == "New chat reply"


@pytest.mark.parametrize("failure", [
    requests.ConnectionError("connection refused"),
    requests.Timeout("request timed out"),
    make_response(b'not json'),
    make_response(b'{"error":"model missing"}', 404),
    make_response(b'{"error":"server failure"}', 500),
])
def test_existing_failures_complete(qtbot, window, failure):
    with patch.object(jugnu_core.requests, "post", side_effect=[failure]):
        send(qtbot, window, "Prompt")
        wait_until_idle(qtbot, window)
    assert window.send_btn.isEnabled()
    assert len(window.current_chat()["messages"]) == 2
    assert window.current_chat()["messages"][-1]["is_error"] is True


def test_reply_arrives_on_the_gui_thread(qtbot, window, monkeypatch):
    threads = []
    original = window.finish_answer
    monkeypatch.setattr(window, "finish_answer", lambda *args: threads.append(
        threading.current_thread()) or original(*args))
    with patch.object(jugnu_core.requests, "post", return_value=make_response(b'{"message":{"content":"Hi"}}')):
        send(qtbot, window, "Hello")
        wait_until_idle(qtbot, window)
    assert threads == [threading.main_thread()]


def test_delayed_response_stays_with_original_chat(qtbot, window):
    request_started, release = threading.Event(), threading.Event()

    def delayed(*_args, **_kwargs):
        request_started.set()
        assert release.wait(3)
        return make_response(b'{"message":{"content":"Delayed reply"}}')

    with patch.object(jugnu_core.requests, "post", side_effect=delayed) as post:
        send(qtbot, window, "Original prompt")
        qtbot.waitUntil(request_started.is_set, timeout=3000)
        assert window.busy and not window.send_btn.isEnabled()
        send(qtbot, window, "Duplicate attempt")
        assert post.call_count == 1
        original_chat = window.current_chat()
        window.new_chat()
        release.set()
        wait_until_idle(qtbot, window)

    assert window.current_chat()["messages"] == []
    assert window.bubbles == []
    assert original_chat["messages"][-1]["content"] == "Delayed reply"
    with open(window.history_file, encoding="utf-8") as f:
        assert json.load(f)[0]["messages"][-1]["content"] == "Delayed reply"


def test_reply_for_a_deleted_chat_is_dropped(qtbot, window, monkeypatch):
    request_started, release = threading.Event(), threading.Event()

    def delayed(*_args, **_kwargs):
        request_started.set()
        assert release.wait(3)
        return make_response(b'{"message":{"content":"Too late"}}')

    monkeypatch.setattr(window, "confirm", lambda title, message: True)
    with patch.object(jugnu_core.requests, "post", side_effect=delayed):
        send(qtbot, window, "Prompt")
        qtbot.waitUntil(request_started.is_set, timeout=3000)
        window.delete_chat(window.current_id)
        release.set()
        wait_until_idle(qtbot, window)
    assert window.chats == []
    assert window.send_btn.isEnabled()
