"""Tests for core.py, the code shared by the terminal assistant and the desktop app.

None of these need a display or a running Ollama: every network call is faked.
"""
import json
import re
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

import assistant
import core
import desktop_app

ROOT = Path(__file__).resolve().parent.parent


def reply(body, status=200):
    response = requests.Response()
    response.status_code = status
    response.url = core.OLLAMA_URL
    response._content = body
    return response


def good(text="Hello"):
    return reply(json.dumps({"message": {"content": text}}).encode())


# ---------- one place only ----------
def source_files():
    return [p for p in ROOT.glob("*.py")]


@pytest.mark.parametrize("needle", ["11434", "llama3.2", "requests.post("])
def test_model_url_and_request_code_exist_only_in_core(needle):
    found = {p.name for p in source_files() if needle in p.read_text(encoding="utf-8")}
    assert found == {"core.py"}


def test_front_ends_do_not_define_their_own_copies():
    for module in (assistant, desktop_app):
        assert not hasattr(module, "MODEL") and not hasattr(module, "OLLAMA_URL")
        assert not hasattr(module, "requests")


def test_calculator_and_time_detector_are_the_core_ones():
    assert assistant.calculate is core.calculate
    assert assistant.is_time_question is core.is_time_question
    assert desktop_app.local_datetime_text is core.local_datetime_text
    assert desktop_app.detect_time_question is core.is_time_question
    assert desktop_app.calculate is core.calculate


# ---------- clock ----------
def test_local_now_knows_its_time_zone():
    assert core.local_now().tzinfo is not None


def test_local_datetime_text_format():
    text = core.local_datetime_text()
    assert re.fullmatch(r"[A-Z][a-z]+day, \d{2} [A-Z][a-z]+ \d{4}, \d{2}:\d{2}:\d{2} [AP]M .+", text), text


# ---------- build_messages ----------
def test_build_messages_puts_system_prompt_first():
    messages = core.build_messages("RULES", [{"role": "user", "content": "hi"}])
    assert messages == [{"role": "system", "content": "RULES"}, {"role": "user", "content": "hi"}]


def test_build_messages_keeps_only_the_recent_messages():
    history = [{"role": "user", "content": str(n)} for n in range(25)]
    messages = core.build_messages("S", history)
    assert [m["content"] for m in messages[1:]] == [str(n) for n in range(15, 25)]
    assert len(core.build_messages("S", history, limit=3)) == 4


def test_build_messages_drops_failure_notices_before_counting():
    valid = [{"role": "user", "content": str(n)} for n in range(12)]
    history = valid + [{"role": "assistant", "content": "notice", "is_error": True}] * 10
    assert core.build_messages("S", history)[1:] == valid[-10:]


def test_build_messages_sends_only_role_and_content_and_leaves_input_alone():
    history = [{"role": "user", "content": "a", "time": "09:00 AM"},
               {"role": "assistant", "content": "b", "time": "09:01 AM", "is_error": False}]
    before = [dict(m) for m in history]
    messages = core.build_messages("S", history)
    assert all(set(m) == {"role", "content"} for m in messages)
    assert history == before


# ---------- chat() ----------
def test_chat_sends_the_expected_request():
    with patch("core.requests.post", return_value=good("Hi!")) as post:
        result = core.chat([{"role": "user", "content": "hello"}], timeout=42)
    assert post.call_args.args == (core.OLLAMA_URL,)
    assert post.call_args.kwargs == {
        "json": {"model": core.MODEL, "messages": [{"role": "user", "content": "hello"}], "stream": False},
        "timeout": 42,
    }
    assert result == core.ChatResult(answer="Hi!") and result.ok


def test_chat_passes_keep_alive_and_options_only_when_given():
    with patch("core.requests.post", return_value=good()) as post:
        core.chat([], keep_alive="10m", options={"num_predict": 5})
    assert post.call_args.kwargs["json"]["keep_alive"] == "10m"
    assert post.call_args.kwargs["json"]["options"] == {"num_predict": 5}
    with patch("core.requests.post", return_value=good()) as post:
        core.chat([])
    assert "keep_alive" not in post.call_args.kwargs["json"]
    assert "options" not in post.call_args.kwargs["json"]
    assert post.call_args.kwargs["timeout"] == 120


def test_chat_strips_the_answer_and_allows_an_empty_one():
    with patch("core.requests.post", return_value=good("  spaced  ")):
        assert core.chat([]).answer == "spaced"
    with patch("core.requests.post", return_value=good("   ")):
        result = core.chat([])
    assert result.ok and result.answer == ""  # each front end decides what to say about it


@pytest.mark.parametrize("failure, kind", [
    (requests.ConnectionError("refused"), core.ERROR_CONNECTION),
    (requests.Timeout("slow"), core.ERROR_TIMEOUT),
    (requests.ConnectTimeout("slow connect"), core.ERROR_TIMEOUT),
    (reply(b'{"message":null}'), core.ERROR_INVALID),
    (reply(b"[]"), core.ERROR_INVALID),
    (reply(b'{"message":{"content":42}}'), core.ERROR_INVALID),
    (reply(b'{"error":"model missing"}', 404), core.ERROR_OTHER),
    (reply(b'{"error":"boom"}', 500), core.ERROR_OTHER),
    (reply(b"not json"), core.ERROR_OTHER),
    (requests.TooManyRedirects("loop"), core.ERROR_OTHER),
    (RuntimeError("unexpected"), core.ERROR_OTHER),
])
def test_chat_reports_every_failure_as_a_kind_and_never_raises(failure, kind):
    with patch("core.requests.post", side_effect=[failure] if isinstance(failure, Exception) else None,
               return_value=None if isinstance(failure, Exception) else failure):
        result = core.chat([])
    assert result.error == kind and not result.ok and result.answer == ""


def test_chat_other_errors_carry_the_technical_text():
    with patch("core.requests.post", return_value=reply(b'{"error":"boom"}', 500)):
        assert "500" in core.chat([]).detail
    with patch("core.requests.post", side_effect=RuntimeError("something odd")):
        assert core.chat([]).detail == "something odd"


def test_chat_result_cannot_be_changed():
    result = core.ChatResult(answer="x")
    with pytest.raises(Exception):
        result.answer = "y"


# ---------- the terminal assistant ----------
@pytest.mark.parametrize("failure, expected", [
    (requests.ConnectionError(), "I cannot connect to Ollama. Please make sure Ollama is running."),
    (requests.Timeout(), "The AI is taking too long to respond. Please try again."),
    (reply(b'{"error":"boom"}', 500), "An error occurred: 500 Server Error"),
    (reply(b'{"message":null}'), "An error occurred: Ollama returned an invalid response."),
])
def test_cli_keeps_its_own_error_wording(failure, expected):
    with patch("core.requests.post", side_effect=[failure] if isinstance(failure, Exception) else None,
               return_value=None if isinstance(failure, Exception) else failure):
        assert assistant.ask_ai("hello").startswith(expected)


def test_cli_request_has_its_own_prompt_and_no_extra_options():
    with patch("core.requests.post", return_value=good("  Answer  ")) as post:
        assert assistant.ask_ai("What is Python?") == "Answer"
    sent = post.call_args.kwargs
    assert sent["json"]["messages"] == [
        {"role": "system", "content": assistant.SYSTEM_PROMPT},
        {"role": "user", "content": "What is Python?"},
    ]
    assert set(sent["json"]) == {"model", "messages", "stream"} and sent["timeout"] == 120


def test_cli_session_end_to_end(monkeypatch, capsys):
    typed = iter(["help", "time", "date", "calculate 6 * 7", "tell me a joke", "bye"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(typed))
    with patch("core.requests.post", return_value=good("A joke")) as post:
        assistant.run_assistant()
    out = capsys.readouterr().out
    assert "Available commands" in out
    assert "The current time is" in out and "Today's date is" in out
    assert "The answer is 42." in out
    assert "Assistant: A joke" in out and "Goodbye" in out
    assert post.call_count == 1  # only the general question went to Ollama


# ---------- the desktop app's two uses of chat() ----------
def run_warm_up(failure=None, answer=None):
    """Call JugnuApp.warm_up on a stand-in object and return the status key it set."""
    done = threading.Event()
    statuses = []
    app = Mock()
    app.root.after.side_effect = lambda _delay, callback: callback()
    app.set_status.side_effect = lambda key, **_kw: (statuses.append(key), done.set())
    with patch("core.requests.post", side_effect=[failure] if failure is not None else None,
               return_value=answer):
        desktop_app.JugnuApp.warm_up(app)
        assert done.wait(3)
    return statuses[-1]


def test_warm_up_shows_ready_when_ollama_answers():
    assert run_warm_up(answer=good("OK")) == "status_ready"


@pytest.mark.parametrize("answer", [reply(b'{"error":"model missing"}', 404), reply(b"not json")])
def test_warm_up_shows_ready_when_ollama_is_up_but_unhappy(answer):
    assert run_warm_up(answer=answer) == "status_ready"


@pytest.mark.parametrize("failure", [requests.ConnectionError(), requests.Timeout()])
def test_warm_up_shows_offline_when_ollama_cannot_be_reached(failure):
    assert run_warm_up(failure=failure) == "status_offline"


def test_warm_up_asks_for_a_tiny_reply_and_keeps_the_model_loaded():
    done = threading.Event()
    app = Mock()
    app.root.after.side_effect = lambda _delay, callback: callback()
    app.set_status.side_effect = lambda *_a, **_k: done.set()
    with patch("core.requests.post", return_value=good("OK")) as post:
        desktop_app.JugnuApp.warm_up(app)
        assert done.wait(3)
    sent = post.call_args.kwargs
    assert sent["timeout"] == 90
    assert sent["json"]["keep_alive"] == "10m" and sent["json"]["options"] == {"num_predict": 3}