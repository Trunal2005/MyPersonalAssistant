"""The GUI-free logic in jugnu_core.py. No window is opened."""
import json
from unittest.mock import patch

import pytest
import requests

import jugnu_core as core
from markdown_render import render_html
from strings import get_string


def response(body, status=200):
    result = requests.Response()
    result.status_code = status
    result._content = body
    return result


def test_history_round_trip_drops_empty_chats_and_bad_messages(tmp_path):
    path = tmp_path / "history.json"
    chats = [
        {"id": "a", "title": "  Kept  ", "messages": [
            {"role": "user", "content": "hi", "time": "10:00 AM"},
            {"role": "system", "content": "dropped"},
            {"role": "assistant", "content": "oops", "is_error": True},
        ]},
        {"id": "b", "title": "Empty", "messages": []},
    ]
    core.save_history(chats, path)
    assert [c["id"] for c in json.loads(path.read_text(encoding="utf-8"))] == ["a"]
    loaded = core.load_history(path)
    assert loaded == [{"id": "a", "title": "Kept", "messages": [
        {"role": "user", "content": "hi", "time": "10:00 AM"},
        {"role": "assistant", "content": "oops", "is_error": True},
    ]}]


@pytest.mark.parametrize("content", ["", "{not json", "{}", "null", '[{"id": "a"}]'])
def test_damaged_history_loads_as_empty(tmp_path, content):
    path = tmp_path / "history.json"
    path.write_text(content, encoding="utf-8")
    assert core.load_history(path) == []


def test_save_history_raises_when_the_folder_is_missing(tmp_path):
    with pytest.raises(OSError):
        core.save_history([{"id": "a", "messages": [{"role": "user", "content": "x"}]}],
                          tmp_path / "missing" / "history.json")


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    core.save_settings(path, dark_mode=False, voice_enabled=True, language="hinglish",
                       voice_rate=999, voice_volume=0.5, voice_id="v1")
    assert core.load_dark_mode(path) is False
    assert core.load_voice_enabled(path) is True
    assert core.load_language(path) == "hinglish"
    assert core.load_voice_prefs(path) == (core.RATE_MAX, 0.5, "v1")  # out-of-range rate is clamped


@pytest.mark.parametrize("content", ["[]", "null", "{broken", '"text"'])
def test_damaged_settings_fall_back_to_defaults(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    assert core.load_dark_mode(path) is True
    assert core.load_voice_enabled(path) is False
    assert core.load_language(path) == "en"
    assert core.load_voice_prefs(path) == (core.DEFAULT_RATE, core.DEFAULT_VOLUME, None)


def test_titles():
    assert core.tidy_title("  a   b  ") == "a b"
    assert len(core.tidy_title("x" * 200)) == core.MAX_TITLE_LENGTH
    assert core.list_title("x" * 100).endswith("…")
    assert len(core.list_title("x" * 100)) == core.MAX_LIST_TITLE


def test_local_answers():
    assert core.local_answer("calculate 12*7", "en") == "The answer is 84."
    with patch.object(core, "local_datetime_text", return_value="NOW"):
        assert core.local_answer("what time is it?", "en") == get_string("en", "time_answer", when="NOW")
    assert core.local_answer("tell me a story", "en") is None


def test_ask_ollama_skips_failure_notices_and_keeps_ten_turns():
    chat = {"messages": [{"role": "user", "content": str(i)} for i in range(12)]
            + [{"role": "assistant", "content": "notice", "is_error": True}]}
    with patch.object(core.requests, "post", return_value=response(b'{"message":{"content":" OK "}}')) as post:
        assert core.ask_ollama(chat, "en") == ("OK", False)
    sent = post.call_args.kwargs["json"]["messages"]
    assert sent[0]["role"] == "system"
    assert [m["content"] for m in sent[1:]] == [str(i) for i in range(2, 12)]


@pytest.mark.parametrize(("failure", "key"), [
    (requests.Timeout(), "error_timeout"),
    (requests.ConnectionError(), "error_connection"),
    (response(b'{"message":null}'), "error_invalid_response"),
    (response(b'{"message":{"content":"  "}}'), "error_empty_reply"),
])
def test_ask_ollama_failures_become_error_notices(failure, key):
    with patch.object(core.requests, "post", side_effect=[failure]):
        assert core.ask_ollama({"messages": []}, "en") == (get_string("en", key), True)


def test_render_html_keeps_code_exact_and_escapes_text():
    html, codes = render_html("Hi <b>&\n\n```py\nx = '<1>'\n\n  y\n```", core.DARK)
    assert codes == ["x = '<1>'\n\n  y"]
    assert 'href="copy:0"' in html
    assert "&lt;b&gt;&amp;" in html and "<b>&" not in html
    assert core.DARK["code"] in html


def test_render_html_never_raises():
    html, codes = render_html(None, core.LIGHT)
    assert isinstance(html, str) and codes == []
