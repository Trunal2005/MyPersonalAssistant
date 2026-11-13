"""The PySide6 window (qt_app.py). Runs offscreen, so no display is needed.

Skipped when PySide6 or pytest-qt is not installed.
"""
import importlib.util
import json
import os
import threading
from unittest.mock import patch

import pytest
import requests

import jugnu_core
from strings import get_string

if not (importlib.util.find_spec("PySide6") and importlib.util.find_spec("pytestqt")):
    pytest.skip("PySide6 and pytest-qt are needed for the Qt tests", allow_module_level=True)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qt_app = Qt = QApplication = QUrl = None  # imported by the fixture below, see tests/conftest.py


@pytest.fixture(autouse=True)
def qt_imports():
    global qt_app, Qt, QApplication, QUrl
    import qt_app as module
    from PySide6.QtCore import Qt as qt_namespace, QUrl as url_class
    from PySide6.QtWidgets import QApplication as app_class
    qt_app, Qt, QApplication, QUrl = module, qt_namespace, app_class, url_class


class FakeTTS:
    available = False
    speaking = False
    voices = []

    def __init__(self, *args, **kwargs):
        self.spoken = []

    def stop(self):
        pass

    def speak(self, text):
        self.spoken.append(text)

    def apply_settings(self, *args):
        pass

    def shutdown(self):
        pass


def make_chat(chat_id, title):
    return {"id": chat_id, "title": title, "messages": [
        {"role": "user", "content": f"question for {title}"},
        {"role": "assistant", "content": f"answer for {title}"}]}


def ok_response(content):
    result = requests.Response()
    result.status_code = 200
    result._content = json.dumps({"message": {"content": content}}).encode()
    return result


@pytest.fixture
def window(qt_imports, qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(qt_app, "TTSManager", FakeTTS)
    monkeypatch.setattr(jugnu_core, "warm_up", lambda: True)  # no Ollama call
    win = qt_app.JugnuWindow(history_file=str(tmp_path / "history.json"),
                             settings_file=str(tmp_path / "settings.json"))
    qtbot.addWidget(win)
    win.resize(1100, 700)
    win.show()
    return win


@pytest.fixture
def with_chats(window):
    window.chats = [make_chat("a", "Alpha"), make_chat("b", "Beta"), make_chat("c", "Gamma")]
    window.current_id = "c"
    window.draft_chat = None
    window.save_history()
    window.display_chat()
    return window


def saved(window):
    with open(window.history_file, encoding="utf-8") as f:
        return json.load(f)


def send(qtbot, window, text):
    window.input_box.setPlainText(text)
    qtbot.mouseClick(window.send_btn, Qt.LeftButton)


def test_starts_with_welcome_and_an_unsaved_draft(window):
    assert window.current_chat()["messages"] == []
    assert window.chats == []
    assert window.bubbles == []
    assert not os.path.exists(window.history_file)


def test_local_answer_adds_bubbles_and_saves(qtbot, window):
    send(qtbot, window, "calculate 6*7")
    assert not window.busy
    assert [m["role"] for m in window.current_chat()["messages"]] == ["user", "assistant"]
    assert len(window.bubbles) == 2
    assert window.history_list.count() == 1
    assert saved(window)[0]["title"] == "calculate 6*7"


def test_enter_sends_and_shift_enter_adds_a_line(qtbot, window):
    window.input_box.setFocus()
    qtbot.keyClicks(window.input_box, "2+2")
    qtbot.keyClick(window.input_box, Qt.Key_Return, Qt.ShiftModifier)
    assert window.input_box.toPlainText() == "2+2\n"
    qtbot.keyClick(window.input_box, Qt.Key_Return)
    assert window.input_box.toPlainText() == ""
    assert window.current_chat()["messages"][0]["content"] == "2+2"


def test_model_reply_arrives_through_the_signal(qtbot, window):
    with patch.object(jugnu_core.requests, "post", return_value=ok_response("**Hello**")):
        send(qtbot, window, "Tell me something")
        assert window.busy and not window.send_btn.isEnabled()
        qtbot.waitUntil(lambda: not window.busy, timeout=3000)
    assert window.send_btn.isEnabled()
    assert window.current_chat()["messages"][-1]["content"] == "**Hello**"
    assert "Hello" in window.bubbles[-1].body.toPlainText()
    assert "**" not in window.bubbles[-1].body.toPlainText()


def test_failure_is_saved_as_an_error_notice(qtbot, window):
    with patch.object(jugnu_core.requests, "post", side_effect=requests.ConnectionError()):
        send(qtbot, window, "Hello?")
        qtbot.waitUntil(lambda: not window.busy, timeout=3000)
    last = window.current_chat()["messages"][-1]
    assert last["content"] == get_string("en", "error_connection")
    assert last["is_error"] is True


def test_reply_stays_with_the_chat_that_asked(qtbot, window):
    started, release = threading.Event(), threading.Event()

    def delayed(*_args, **_kwargs):
        started.set()
        assert release.wait(3)
        return ok_response("Delayed reply")

    with patch.object(jugnu_core.requests, "post", side_effect=delayed):
        send(qtbot, window, "Original prompt")
        qtbot.waitUntil(started.is_set, timeout=3000)
        original = window.current_chat()
        send(qtbot, window, "Ignored while busy")
        window.new_chat()
        release.set()
        qtbot.waitUntil(lambda: not window.busy, timeout=3000)
    assert window.current_chat()["messages"] == []
    assert [m["content"] for m in original["messages"]] == ["Original prompt", "Delayed reply"]
    assert window.bubbles == []


def test_history_list_is_newest_first_and_selects_a_chat(qtbot, with_chats):
    window = with_chats
    titles = [window.history_list.item(i).text() for i in range(window.history_list.count())]
    assert titles == ["Gamma", "Beta", "Alpha"]
    window.select_chat(window.history_list.item(2))
    assert window.current_id == "a"
    assert window.bubbles[0].text == "question for Alpha"


def test_rename_changes_only_that_title(with_chats, monkeypatch):
    window = with_chats
    monkeypatch.setattr(window, "ask_chat_title", lambda initial: "  My   new   name ")
    window.rename_chat("a")
    assert [c["title"] for c in saved(window)] == ["My new name", "Beta", "Gamma"]
    assert window.current_id == "c"


@pytest.mark.parametrize("answer", [None, "", "   ", "Alpha"])
def test_rename_ignores_cancel_empty_and_unchanged(with_chats, monkeypatch, answer):
    window = with_chats
    monkeypatch.setattr(window, "ask_chat_title", lambda initial: answer)
    window.rename_chat("a")
    assert window.find_chat("a")["title"] == "Alpha"


def test_delete_open_chat_leaves_a_fresh_draft(with_chats, monkeypatch):
    window = with_chats
    monkeypatch.setattr(window, "confirm", lambda title, message: True)
    window.delete_chat("c")
    assert [c["id"] for c in saved(window)] == ["a", "b"]
    assert window.current_chat()["messages"] == []


def test_delete_is_cancelled_when_not_confirmed(with_chats, monkeypatch):
    window = with_chats
    monkeypatch.setattr(window, "confirm", lambda title, message: False)
    window.delete_chat("a")
    assert len(window.chats) == 3


def test_copy_button_copies_the_original_markdown(qtbot, window):
    bubble = window.add_bubble("assistant", "**bold** text")
    qtbot.mouseClick(bubble.copy_btn, Qt.LeftButton)
    assert QApplication.clipboard().text() == "**bold** text"
    assert bubble.copy_btn.text() == qt_app.COPIED_TEXT


def test_code_block_link_copies_exact_code(window):
    bubble = window.add_bubble("assistant", "```py\nx = 1\n\n  y = 2\n```")
    bubble.on_link(QUrl("copy:0"))
    assert QApplication.clipboard().text() == "x = 1\n\n  y = 2"


def test_user_text_is_shown_exactly_as_typed(window):
    bubble = window.add_bubble("user", "**not bold** <b>tag</b>")
    assert bubble.body.toPlainText() == "**not bold** <b>tag</b>"


def test_bubbles_stay_inside_the_chat_area(qtbot, window):
    long_word = window.add_bubble("user", "x" * 2000)
    short = window.add_bubble("assistant", "Hi")
    limit = qt_app.max_bubble_width(window.scroll.viewport().width())
    assert long_word.body.width() <= limit
    assert short.body.width() < 100  # short messages get a small bubble
    window.resize(900, 700)
    qtbot.waitUntil(lambda: long_word.body.width() <= qt_app.max_bubble_width(
        window.scroll.viewport().width()), timeout=2000)


def test_theme_and_language_are_saved_and_applied(window):
    window.toggle_theme()
    assert window.colors is jugnu_core.LIGHT
    assert jugnu_core.LIGHT["accent"] in window.styleSheet()
    window.toggle_language()
    assert window.send_btn.text() == get_string("hinglish", "send_btn")
    assert jugnu_core.load_dark_mode(window.settings_file) is False
    assert jugnu_core.load_language(window.settings_file) == "hinglish"


def test_stylesheet_has_no_unfilled_colours(qt_imports):
    for palette in (jugnu_core.LIGHT, jugnu_core.DARK):
        assert "$" not in qt_app.build_stylesheet(palette)


def test_voice_buttons_are_disabled_without_tts(window):
    assert not window.voice_btn.isEnabled()
    assert not window.voice_settings_btn.isEnabled()
    bubble = window.add_bubble("assistant", "Hi")
    assert not bubble.read_btn.isEnabled()
