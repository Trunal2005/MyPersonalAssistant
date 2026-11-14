"""Request failures stay visible while model context contains conversation turns."""
from unittest.mock import patch

import pytest
import requests

import jugnu_core
from conftest import make_chat
from strings import get_string


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = body
    return result


@pytest.fixture
def app(window):
    window.chats = [make_chat("chat", "Chat", [
        {"role": "user", "content": "Project Cedar"},
        {"role": "assistant", "content": "Acknowledged Cedar"},
    ])]
    window.current_id = "chat"
    window.draft_chat = None
    window.display_chat()
    return window


def ask(qtbot, app):
    """Ask the model for a reply to the open chat and wait for it."""
    app.busy = True
    app.ask_ollama("chat")
    qtbot.waitUntil(lambda: not app.busy, timeout=3000)


@pytest.mark.parametrize("failure", [
    requests.Timeout(),
    requests.ConnectionError(),
    response(b'{"error":"missing model"}', 404),
    response(b'{"error":"server error"}', 500),
    response(b'not json'),
    response(b'{"message":null}'),
    response(b'{"message":{"content":"  "}}'),
])
def test_failure_notice_survives_reload_without_consuming_context(qtbot, app, failure):
    bubbles_before = len(app.bubbles)
    with patch.object(jugnu_core.requests, "post", side_effect=[failure] * 5):
        for _ in range(5):
            app.chats[0]["messages"].append({"role": "user", "content": "Try again"})
            ask(qtbot, app)
            assert app.send_btn.isEnabled()
            assert app.chats[0]["messages"][-1].get("is_error") is True
    app.chats = jugnu_core.load_history(app.history_file)
    notices = [m for m in app.chats[0]["messages"] if m.get("is_error")]
    assert len(notices) == 5
    assert len(app.bubbles) == bubbles_before + 5
    app.chats[0]["messages"].append({"role": "user", "content": "Which project?"})
    with patch.object(jugnu_core.requests, "post", return_value=response(
        b'{"message":{"content":"Project Cedar"}}'
    )) as post:
        ask(qtbot, app)
    context = post.call_args.kwargs["json"]["messages"][1:]
    assert len(context) == 8
    assert [m["content"] for m in context if m["role"] == "assistant"] == ["Acknowledged Cedar"]
    assert all(set(m) == {"role", "content"} for m in context)
    assert app.chats[0]["messages"][-1]["content"] == "Project Cedar"
    assert not app.chats[0]["messages"][-1].get("is_error", False)


def test_legacy_messages_are_retained_without_matching_error_wording(qtbot, app):
    app.chats[0]["messages"] = [
        {"role": "assistant", "content": get_string("en", "error_timeout")},
        {"role": "user", "content": "Explain that message"},
    ]
    app.save_history()
    app.chats = jugnu_core.load_history(app.history_file)
    with patch.object(jugnu_core.requests, "post", return_value=response(
        b'{"message":{"content":"Explanation"}}'
    )) as post:
        ask(qtbot, app)
    assert post.call_args.kwargs["json"]["messages"][1]["content"] == get_string("en", "error_timeout")


def test_context_limit_applies_after_filtering(qtbot, app):
    valid = [{"role": "user", "content": str(i)} for i in range(12)]
    app.chats[0]["messages"] = valid + [
        {"role": "assistant", "content": "notice", "is_error": True}
    ] * 10
    with patch.object(jugnu_core.requests, "post", return_value=response(
        b'{"message":{"content":"OK"}}'
    )) as post:
        ask(qtbot, app)
    assert post.call_args.kwargs["json"]["messages"][1:] == valid[-10:]
