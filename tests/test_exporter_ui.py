"""UI and integration tests for the Conversation Exporter dialog in JugnuApp."""
import os
import tempfile
import tkinter as tk
import types
import pytest

from desktop_app import JugnuApp
from exporter import extract_chat_metadata


_shared_root = None
_shared_app = None


@pytest.fixture(autouse=True)
def setup_app_mock(monkeypatch):
    """Ensure heavy subsystems (Ollama warmup, TTS, STT) are mocked."""
    monkeypatch.setattr(JugnuApp, "warm_up", lambda self: None)
    monkeypatch.setattr("desktop_app.TTSManager", lambda *a, **k: types.SimpleNamespace(
        available=False,
        speaking=False,
        voices=[],
        stop=lambda: None,
        speak=lambda _t: None,
        apply_settings=lambda *_a: None,
        shutdown=lambda: None,
    ))


@pytest.fixture
def tk_app():
    """Provide a reliable headless JugnuApp instance."""
    global _shared_root, _shared_app
    if _shared_root is None:
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
        except tk.TclError:
            pytest.skip("No display available for Tk")

        _shared_app = JugnuApp(_shared_root)

    app = _shared_app
    yield app, _shared_root


def test_export_button_in_header(tk_app):
    """Verify that the Export button is present in the header and labeled properly."""
    app, root = tk_app
    assert hasattr(app, "export_btn")
    assert app.export_btn.winfo_exists()
    assert app.export_btn["text"] == app.t("export_btn")


def test_open_export_dialog_creation(tk_app):
    """Verify the export dialog opens with format radio options and metadata."""
    app, root = tk_app
    app.chats = [
        {
            "id": "chat-ui-1",
            "title": "Quantum Computing 101",
            "messages": [
                {"role": "user", "content": "What is superposition?", "time": "09:00 AM"},
                {"role": "assistant", "content": "Superposition is a principle of quantum mechanics...", "time": "09:01 AM"},
            ],
        }
    ]
    app.current_id = "chat-ui-1"

    win = app.open_export_dialog()
    assert win is not None
    assert win.winfo_exists()
    assert win.title() == app.t("export_dialog_title")

    # Clean up window
    win.destroy()
    root.update_idletasks()


def test_open_export_dialog_empty_chat(tk_app):
    """Verify export dialog handles an empty conversation gracefully."""
    app, root = tk_app
    app.chats = [
        {
            "id": "empty-chat-ui",
            "title": "Blank Topic",
            "messages": [],
        }
    ]
    app.current_id = "empty-chat-ui"

    win = app.open_export_dialog()
    assert win is not None
    assert win.winfo_exists()

    # Clean up
    win.destroy()
    root.update_idletasks()


def test_export_dialog_execute_file_save(tk_app, monkeypatch):
    """Verify triggering export from the dialog writes the expected file."""
    app, root = tk_app
    app.chats = [
        {
            "id": "chat-save-test",
            "title": "Save Test Chat",
            "messages": [
                {"role": "user", "content": "Hello Export", "time": "10:00 AM"},
                {"role": "assistant", "content": "Export response", "time": "10:01 AM"},
            ],
        }
    ]
    app.current_id = "chat-save-test"

    shown_messages = []
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda title, msg, **kwargs: shown_messages.append((title, msg)))

    with tempfile.TemporaryDirectory() as tmpdir:
        out_target = os.path.join(tmpdir, "exported_chat.md")

        # Open dialog
        win = app.open_export_dialog()

        win.format_var.set("md")
        win.path_entry.delete(0, "end")
        win.path_entry.insert(0, out_target)

        # Trigger export
        win.do_export()
        root.update_idletasks()

        # Check that file was created
        assert os.path.isfile(out_target)
        with open(out_target, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Save Test Chat" in content
            assert "Hello Export" in content

        # Check that success message was displayed
        assert len(shown_messages) == 1
        assert shown_messages[0][0] == app.t("export_success_title")
