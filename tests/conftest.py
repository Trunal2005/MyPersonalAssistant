"""Shared fixtures for the tests that open JUGNU's Qt window.

The window runs offscreen, so no display is needed. Qt is imported only inside the
fixtures, so the logic tests still run where PySide6 is not installed.
"""
import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeTTS:
    """Stands in for TTSManager: records what would be spoken instead of speaking."""
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


def make_chat(chat_id, title, messages=None):
    return {"id": chat_id, "title": title, "messages": messages or [
        {"role": "user", "content": f"question for {title}"},
        {"role": "assistant", "content": f"answer for {title}"}]}


@pytest.fixture
def make_window(qtbot, tmp_path, monkeypatch):
    """Build a window whose history and settings live in tmp_path. Optionally start from saved `history`."""
    pytest.importorskip("PySide6")
    import jugnu_core
    import desktop_app

    monkeypatch.setattr(desktop_app, "TTSManager", FakeTTS)
    monkeypatch.setattr(jugnu_core, "warm_up", lambda: True)  # no Ollama call
    windows = []

    def build(history=None):
        history_file = tmp_path / "jugnu_history.json"
        if history is not None:
            history_file.write_text(json.dumps(history), encoding="utf-8")
        window = desktop_app.JugnuWindow(history_file=str(history_file),
                                    settings_file=str(tmp_path / "jugnu_settings.json"))
        qtbot.addWidget(window)
        window.resize(1100, 700)
        window.show()
        windows.append(window)
        return window

    yield build
    for window in windows:
        window.close()  # no new requests start after this
        assert window.wait_for_tasks(3000), "a background request was still running"


@pytest.fixture
def window(make_window):
    return make_window()


@pytest.fixture
def with_chats(window):
    """A window with three saved chats; the newest ("c") is open."""
    window.chats = [make_chat("a", "Alpha"), make_chat("b", "Beta"), make_chat("c", "Gamma")]
    window.current_id = "c"
    window.draft_chat = None
    window.save_history()
    window.display_chat()
    return window


def saved_history(window):
    with open(window.history_file, encoding="utf-8") as f:
        return json.load(f)


def send(qtbot, window, text):
    from PySide6.QtCore import Qt

    window.input_box.setPlainText(text)
    qtbot.mouseClick(window.send_btn, Qt.LeftButton)
