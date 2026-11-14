"""Request failures stay visible while model context contains conversation turns."""

from unittest.mock import Mock, patch

import pytest
import requests

import core
import desktop_app as desktop


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = body
    return result


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop, "HISTORY_FILE", tmp_path / "history.json")
    app = desktop.JugnuApp.__new__(desktop.JugnuApp)
    app.language = "en"
    app.current_id = "chat"
    app.draft_chat = None
    app.voice_enabled = False
    app.chats = [{"id": "chat", "title": "Chat", "messages": [
        {"role": "user", "content": "Project Cedar"},
        {"role": "assistant", "content": "Acknowledged Cedar"},
    ]}]
    for name in ("root", "add_bubble", "canvas", "send_btn", "set_status",
                 "refresh_history_list"):
        setattr(app, name, Mock())
    app.root.after.side_effect = lambda delay, callback: callback()
    return app


@pytest.mark.parametrize("failure", [
    requests.Timeout(),
    requests.ConnectionError(),
    response(b'{"error":"missing model"}', 404),
    response(b'{"error":"server error"}', 500),
    response(b'not json'),
    response(b'{"message":null}'),
    response(b'{"message":{"content":"  "}}'),
])
def test_failure_notice_survives_reload_without_consuming_context(app, failure):
    with patch.object(core.requests, "post", side_effect=[failure] * 5):
        for _ in range(5):
            app.chats[0]["messages"].append({"role": "user", "content": "Try again"})
            app.busy = True
            app.ask_ollama("chat")
            assert not app.busy
            app.send_btn.configure.assert_called_with(state="normal")
            assert app.chats[0]["messages"][-1].get("is_error") is True
    app.chats = app.load_history()
    notices = [m for m in app.chats[0]["messages"] if m.get("is_error")]
    assert len(notices) == 5
    assert app.add_bubble.call_count == 5
    app.chats[0]["messages"].append({"role": "user", "content": "Which project?"})
    with patch.object(core.requests, "post", return_value=response(
        b'{"message":{"content":"Project Cedar"}}'
    )) as post:
        app.ask_ollama("chat")
    context = post.call_args.kwargs["json"]["messages"][1:]
    assert len(context) == 8
    assert [m["content"] for m in context if m["role"] == "assistant"] == ["Acknowledged Cedar"]
    assert all(set(m) == {"role", "content"} for m in context)
    assert app.chats[0]["messages"][-1]["content"] == "Project Cedar"
    assert not app.chats[0]["messages"][-1].get("is_error", False)


def test_legacy_messages_are_retained_without_matching_error_wording(app):
    app.chats[0]["messages"] = [
        {"role": "assistant", "content": desktop.get_string("en", "error_timeout")},
        {"role": "user", "content": "Explain that message"},
    ]
    app.save_history()
    app.chats = app.load_history()
    with patch.object(core.requests, "post", return_value=response(
        b'{"message":{"content":"Explanation"}}'
    )) as post:
        app.ask_ollama("chat")
    assert post.call_args.kwargs["json"]["messages"][1]["content"] == desktop.get_string(
        "en", "error_timeout"
    )


def test_context_limit_applies_after_filtering(app):
    valid = [{"role": "user", "content": str(i)} for i in range(12)]
    app.chats[0]["messages"] = valid + [
        {"role": "assistant", "content": "notice", "is_error": True}
    ] * 10
    with patch.object(core.requests, "post", return_value=response(
        b'{"message":{"content":"OK"}}'
    )) as post:
        app.ask_ollama("chat")
    assert post.call_args.kwargs["json"]["messages"][1:] == valid[-10:]