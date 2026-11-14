"""Unit and integration tests for real-time token streaming and generation stop."""

import io
import json
import os
import sys
import threading
import tkinter as tk
from unittest.mock import Mock, patch

# Ensure Tcl/Tk can locate their runtime libraries on Windows when changing directories in tests
tcl_dir = os.path.join(sys.prefix, "tcl", "tcl8.6").replace("\\", "/")
tk_dir = os.path.join(sys.prefix, "tcl", "tk8.6").replace("\\", "/")
if os.path.isdir(tcl_dir):
    os.environ["TCL_LIBRARY"] = tcl_dir
if os.path.isdir(tk_dir):
    os.environ["TK_LIBRARY"] = tk_dir

import pytest
import requests

import assistant
import desktop_app as desktop
from strings import get_string


# ---------------- CHUNK PARSER & LINE ITERATOR TESTS ----------------

def test_ollama_stream_chunk_valid_token():
    chunk = {"message": {"role": "assistant", "content": "Hello world"}, "done": False}
    token, is_done = desktop.ollama_stream_chunk(chunk)
    assert token == "Hello world"
    assert is_done is False


def test_ollama_stream_chunk_done_with_final_token():
    chunk = {"message": {"role": "assistant", "content": "!"}, "done": True}
    token, is_done = desktop.ollama_stream_chunk(chunk)
    assert token == "!"
    assert is_done is True


def test_ollama_stream_chunk_done_without_message():
    chunk = {"done": True}
    token, is_done = desktop.ollama_stream_chunk(chunk)
    assert token == ""
    assert is_done is True


@pytest.mark.parametrize("invalid_chunk", [
    [],
    "not a dict",
    None,
    {},
    {"message": None},
    {"message": []},
    {"message": {}},
    {"message": {"content": None}},
    {"message": {"content": 42}},
    {"message": {"content": True}},
])
def test_ollama_stream_chunk_invalid_raises(invalid_chunk):
    with pytest.raises(desktop.InvalidOllamaResponse):
        desktop.ollama_stream_chunk(invalid_chunk)


def test_iter_response_lines_from_raw():
    resp = requests.Response()
    resp.raw = io.BytesIO(b'{"token":"a"}\n{"token":"b"}\n')
    lines = list(desktop.iter_response_lines(resp))
    assert lines == [b'{"token":"a"}', b'{"token":"b"}']


def test_iter_response_lines_from_content():
    resp = requests.Response()
    resp._content = b'line 1\nline 2'
    lines = list(desktop.iter_response_lines(resp))
    assert lines == [b'line 1', b'line 2']


# ---------------- CLI ASSISTANT STREAMING TESTS ----------------

def test_assistant_ask_ai_streaming(capsys):
    ndjson = (
        b'{"message":{"content":"Hello"},"done":false}\n'
        b'{"message":{"content":" from"},"done":false}\n'
        b'{"message":{"content":" CLI"},"done":true}\n'
    )
    mock_resp = requests.Response()
    mock_resp.status_code = 200
    mock_resp._content = ndjson

    with patch("assistant.requests.post", return_value=mock_resp):
        result = assistant.ask_ai("Say hello", stream=True)

    captured = capsys.readouterr().out
    assert "Hello from CLI" in captured
    assert result == "Hello from CLI"


def test_assistant_ask_ai_non_streaming():
    mock_resp = requests.Response()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"message": {"content": "Non streaming reply"}}

    with patch("assistant.requests.post", return_value=mock_resp):
        result = assistant.ask_ai("Say hello", stream=False)

    assert result == "Non streaming reply"


def test_assistant_ask_ai_connection_error(capsys):
    with patch("assistant.requests.post", side_effect=requests.exceptions.ConnectionError):
        result = assistant.ask_ai("Say hello", stream=True)

    captured = capsys.readouterr().out
    assert "cannot connect to Ollama" in captured
    assert "cannot connect to Ollama" in result


# ---------------- DESKTOP APP STREAMING FIXTURES & TESTS ----------------

@pytest.fixture
def desktop_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(desktop, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(desktop.JugnuApp, "warm_up", lambda self: None)

    with patch("desktop_app.TTSManager") as mock_tts:
        mock_tts.return_value.available = False
        root = tk.Tk()
        root.withdraw()
        app = desktop.JugnuApp(root)
        yield app, root
        for timer in root.tk.splitlist(root.tk.call("after", "info")):
            try:
                root.after_cancel(timer)
            except Exception:
                pass
        app.welcome_photo = None
        root.destroy()


def make_stream_response(chunks, status=200):
    lines = [json.dumps(c).encode("utf-8") for c in chunks]
    resp = requests.Response()
    resp.url = "http://localhost:11434/api/chat"
    resp.status_code = status
    resp._content = b"\n".join(lines) + b"\n"
    return resp


def wait_until(root, condition, max_seconds=3):
    expired = []

    def check():
        if condition():
            root.quit()
        else:
            root.after(10, check)

    def on_timeout():
        expired.append(True)
        root.quit()

    timer = root.after(int(max_seconds * 1000), on_timeout)
    root.after(0, check)
    root.mainloop()
    root.after_cancel(timer)
    assert not expired, "Condition timed out in wait_until"


def test_desktop_realtime_token_streaming(desktop_app):
    app, root = desktop_app
    chunks = [
        {"message": {"role": "assistant", "content": "JUGNU"}, "done": False},
        {"message": {"role": "assistant", "content": " is"}, "done": False},
        {"message": {"role": "assistant", "content": " streaming"}, "done": False},
        {"message": {"role": "assistant", "content": "!"}, "done": True},
    ]
    mock_resp = make_stream_response(chunks)

    with patch("desktop_app.requests.post", return_value=mock_resp):
        app.input_box.insert("1.0", "Test stream")
        app.send_btn.invoke()
        wait_until(root, lambda: not app.busy)

    assert not app.busy
    assert not app.is_streaming
    assert app.send_btn.cget("state") == "normal"
    assert app.stop_gen_btn.winfo_manager() == ""

    messages = app.current_chat()["messages"]
    assert len(messages) == 2
    assert messages[0]["content"] == "Test stream"
    assert messages[1]["content"] == "JUGNU is streaming!"
    assert not messages[1].get("is_error", False)


def test_desktop_stop_generation_aborts_and_preserves_partial_output(desktop_app):
    app, root = desktop_app
    started = threading.Event()
    release = threading.Event()

    def delayed_stream(*_args, **_kwargs):
        started.set()
        # Wait for test to call stop_generating before returning chunks
        release.wait(timeout=2)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = (
            b'{"message":{"role":"assistant","content":"Partial output"},"done":false}\n'
            b'{"message":{"role":"assistant","content":" should not arrive"},"done":true}\n'
        )
        return resp

    with patch("desktop_app.requests.post", side_effect=delayed_stream):
        app.input_box.insert("1.0", "Long question")
        app.send_btn.invoke()
        wait_until(root, started.is_set)

        assert app.busy
        assert app.is_streaming
        assert app.stop_gen_btn.winfo_manager() == "pack"

        # Simulate user clicking Stop
        app.stop_generating()
        assert app.stop_event.is_set()

        release.set()
        wait_until(root, lambda: not app.busy)

    assert not app.busy
    assert not app.is_streaming
    assert app.send_btn.cget("state") == "normal"
    assert app.stop_gen_btn.winfo_manager() == ""


def test_desktop_streaming_error_recovers_send_and_status(desktop_app):
    app, root = desktop_app
    with patch("desktop_app.requests.post", side_effect=requests.ConnectionError("Connection lost")):
        app.input_box.insert("1.0", "Hello when offline")
        app.send_btn.invoke()
        wait_until(root, lambda: not app.busy)

    assert not app.busy
    assert not app.is_streaming
    assert app.send_btn.cget("state") == "normal"
    assert app.stop_gen_btn.winfo_manager() == ""

    messages = app.current_chat()["messages"]
    assert len(messages) == 2
    assert messages[1].get("is_error") is True
    assert messages[1]["content"] == get_string(app.language, "error_connection")


def test_desktop_stop_button_text_localizes(desktop_app):
    app, _ = desktop_app
    app.language = "en"
    app.apply_language()
    assert app.stop_gen_btn.cget("text") == "⏹  Stop"

    app.language = "hinglish"
    app.apply_language()
    assert app.stop_gen_btn.cget("text") == "⏹  Roko"
