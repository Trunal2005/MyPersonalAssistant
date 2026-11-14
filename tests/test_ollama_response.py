"""Exercise the desktop request worker with real Tk widgets and local HTTP fakes."""

import json
import threading
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from desktop_app import JugnuApp
from strings import get_string


def make_response(body, status=200):
    response = requests.Response()
    response.url = "http://localhost:11434/api/chat"
    response.status_code = status
    response._content = body
    return response


def wait_for(root, condition, seconds=3):
    expired = []

    def check():
        if condition():
            root.quit()
        else:
            root.after(10, check)

    def timeout():
        expired.append(True)
        root.quit()

    timer = root.after(int(seconds * 1000), timeout)
    root.after(0, check)
    root.mainloop()
    root.after_cancel(timer)
    assert not expired, "Desktop request did not complete"


@pytest.fixture
def desktop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(JugnuApp, "warm_up", lambda self: None)
    with patch("desktop_app.TTSManager") as tts:
        tts.return_value.available = False
        root = tk.Tk()
        root.withdraw()
        callback_errors = []
        root.report_callback_exception = lambda _type, error, _traceback: callback_errors.append(error)
        app = JugnuApp(root)
        yield app, root, callback_errors
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            root.after_cancel(timer)
        app.welcome_photo = None
        root.destroy()


def send(app, text):
    app.input_box.insert("1.0", text)
    app.send_btn.invoke()


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
def test_invalid_response_recovers_and_accepts_follow_up(desktop, monkeypatch, body):
    app, root, callback_errors = desktop
    worker_errors = []
    monkeypatch.setattr(threading, "excepthook", lambda args: worker_errors.append(args.exc_value))
    valid = make_response(b'{"message":{"role":"assistant","content":"Recovered reply"}}')
    with patch("core.requests.post", side_effect=[make_response(body), valid]) as post:
        send(app, "First prompt")
        wait_for(root, lambda: worker_errors or not app.busy)
        assert not worker_errors
        assert not callback_errors
        assert not app.busy
        assert app.send_btn.cget("state") == "normal"
        assert "Thinking" not in app.status.cget("text")
        assert app.current_chat()["messages"][0]["content"] == "First prompt"
        assert len(app.current_chat()["messages"]) == 2
        assert app.current_chat()["messages"][-1]["content"] == get_string(
            app.language, "error_invalid_response"
        )

        send(app, "Second prompt")
        wait_for(root, lambda: worker_errors or not app.busy)
        assert not worker_errors and not callback_errors
        assert app.current_chat()["messages"][-1]["content"] == "Recovered reply"
        assert len(app.current_chat()["messages"]) == 4
        assert post.call_count == 2


def test_new_chat_can_send_after_invalid_response(desktop):
    app, root, callback_errors = desktop
    invalid = make_response(b'{"message":null}')
    valid = make_response(b'{"message":{"content":"New chat reply"}}')
    with patch("core.requests.post", side_effect=[invalid, valid]) as post:
        send(app, "Original prompt")
        wait_for(root, lambda: not app.busy)
        original_chat = app.current_chat()
        app.new_chat()
        send(app, "New chat prompt")
        wait_for(root, lambda: not app.busy)

    assert not callback_errors
    assert post.call_count == 2
    assert app.send_btn.cget("state") == "normal"
    assert original_chat["messages"][0]["content"] == "Original prompt"
    assert app.current_chat()["messages"][-1]["content"] == "New chat reply"


@pytest.mark.parametrize("failure", [
    requests.ConnectionError("connection refused"),
    requests.Timeout("request timed out"),
    make_response(b'not json'),
    make_response(b'{"error":"model missing"}', 404),
    make_response(b'{"error":"server failure"}', 500),
])
def test_existing_failures_complete(desktop, failure):
    app, root, callback_errors = desktop
    with patch("core.requests.post", side_effect=[failure]):
        send(app, "Prompt")
        wait_for(root, lambda: not app.busy)
    assert not callback_errors
    assert app.send_btn.cget("state") == "normal"
    assert len(app.current_chat()["messages"]) == 2


def test_delayed_response_stays_with_original_chat(desktop):
    app, root, callback_errors = desktop
    request_started = threading.Event()
    release = threading.Event()

    def delayed(*_args, **_kwargs):
        request_started.set()
        assert release.wait(3)
        return make_response(b'{"message":{"content":"Delayed reply"}}')

    with patch("core.requests.post", side_effect=delayed) as post:
        send(app, "Original prompt")
        wait_for(root, request_started.is_set)
        assert app.busy
        assert app.send_btn.cget("state") == "disabled"
        send(app, "Duplicate attempt")
        assert post.call_count == 1
        original_chat = app.current_chat()
        app.new_chat()
        release.set()
        wait_for(root, lambda: not app.busy)

    assert not callback_errors
    assert app.current_chat()["messages"] == []
    assert original_chat["messages"][-1]["content"] == "Delayed reply"
    saved = json.loads(Path("jugnu_history.json").read_text(encoding="utf-8"))
    assert saved[0]["messages"][-1]["content"] == "Delayed reply"