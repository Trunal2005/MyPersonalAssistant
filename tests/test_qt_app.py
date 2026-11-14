"""The main window as a whole: startup, sending, theme, language and voice controls."""
import os
import re

import pytest

import jugnu_core
from conftest import saved_history, send
from strings import get_string

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_starts_with_welcome_and_an_unsaved_draft(window):
    assert window.current_chat()["messages"] == []
    assert window.chats == [] and window.bubbles == []
    assert not os.path.exists(window.history_file)


def test_reopens_the_most_recent_chat(make_window):
    app = make_window([
        {"id": "old", "title": "Old", "messages": [{"role": "user", "content": "first"}]},
        {"id": "new", "title": "New", "messages": [{"role": "user", "content": "second"}]},
    ])
    assert app.current_id == "new"
    assert [b.text for b in app.bubbles] == ["second"]


def test_local_answer_adds_bubbles_and_saves(qtbot, window):
    send(qtbot, window, "calculate 6*7")
    assert not window.busy
    assert [m["role"] for m in window.current_chat()["messages"]] == ["user", "assistant"]
    assert len(window.bubbles) == 2
    assert window.history_list.count() == 1
    assert saved_history(window)[0]["title"] == "calculate 6*7"


def test_empty_message_is_not_sent(qtbot, window):
    send(qtbot, window, "   \n ")
    assert window.chats == [] and window.bubbles == []


def test_enter_sends_and_shift_enter_adds_a_line(qtbot, window):
    from PySide6.QtCore import Qt

    window.input_box.setFocus()
    qtbot.keyClicks(window.input_box, "2+2")
    qtbot.keyClick(window.input_box, Qt.Key_Return, Qt.ShiftModifier)
    assert window.input_box.toPlainText() == "2+2\n"
    qtbot.keyClick(window.input_box, Qt.Key_Return)
    assert window.input_box.toPlainText() == ""
    assert window.current_chat()["messages"][0]["content"] == "2+2"


def test_new_chat_is_not_saved_until_a_message_is_sent(qtbot, window):
    send(qtbot, window, "1+1")
    window.new_chat()
    assert len(saved_history(window)) == 1
    assert window.current_chat()["messages"] == []


def test_theme_and_language_are_saved_and_applied(window):
    from PySide6.QtWidgets import QApplication

    window.toggle_theme()
    assert window.colors is jugnu_core.LIGHT
    assert jugnu_core.LIGHT["accent"] in QApplication.instance().styleSheet()
    window.toggle_language()
    assert window.send_btn.text() == get_string("hinglish", "send_btn")
    assert window.status.text().endswith(get_string("hinglish", "status_ready"))
    assert jugnu_core.load_dark_mode(window.settings_file) is False
    assert jugnu_core.load_language(window.settings_file) == "hinglish"


@pytest.mark.parametrize(("name", "palette"), [("light", jugnu_core.LIGHT), ("dark", jugnu_core.DARK)])
def test_each_stylesheet_uses_only_its_own_palette(name, palette):
    with open(os.path.join(HERE, f"{name}.qss"), encoding="utf-8") as f:
        qss = f.read()
    allowed = {value.upper() for value in palette.values()} | {"#D1FAE5", "#10B981"}  # status and "Copied" greens
    used = {value.upper() for value in re.findall(r"#[0-9A-Fa-f]{6}\b", qss)}
    assert used and used <= allowed


def test_light_and_dark_stylesheets_have_the_same_rules():
    def rules(name):
        with open(os.path.join(HERE, f"{name}.qss"), encoding="utf-8") as f:
            body = f.read().split("*/", 1)[1]  # skip the header comment, which names the theme
        return re.sub(r"#[0-9A-Fa-f]{6}\b", "#COLOUR", body)
    assert rules("light") == rules("dark")


def test_voice_buttons_are_disabled_without_tts(window):
    assert not window.voice_btn.isEnabled()
    assert not window.voice_settings_btn.isEnabled()
    assert not window.add_bubble("assistant", "Hi").read_btn.isEnabled()


def test_voice_toggle_is_saved(window):
    window.toggle_voice()
    assert window.voice_btn.text() == window.t("voice_on")
    assert jugnu_core.load_voice_enabled(window.settings_file) is True


def test_voice_settings_dialog_updates_and_saves_values(window):
    window.tts.available = True
    window.tts.voices = [("v1", "Alex"), ("v2", "Alex"), ("v3", "Samantha")]
    window.open_voice_settings()
    dialog = window.voice_dialog
    names = [dialog.voice.itemText(i) for i in range(dialog.voice.count())]
    assert names == [window.t("voice_default_name"), "Alex", "Alex (2)", "Samantha"]
    dialog.rate.setValue(200)
    dialog.volume.setValue(40)
    dialog.voice.setCurrentIndex(3)
    dialog.on_voice(3)
    dialog.close()
    assert jugnu_core.load_voice_prefs(window.settings_file) == (200, 0.4, "v3")
    assert dialog.rate_label.text() == window.t("voice_rate_label", value=200)


def test_stop_button_follows_speech(window):
    window.tts.speaking = True
    window.poll_speech()
    assert window.stop_btn.isVisibleTo(window)
    window.tts.speaking = False
    window.poll_speech()
    assert not window.stop_btn.isVisibleTo(window)
