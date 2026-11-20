"""UI and Integration tests for Persona Studio and Per-Conversation Persona Switcher."""
import os
import tempfile
import tkinter as tk
import types
from unittest.mock import patch
import pytest

from desktop_app import JugnuApp
from personas import Persona, PersonaManager


_shared_root = None
_shared_app = None


@pytest.fixture(autouse=True)
def setup_app_mock(monkeypatch):
    """Mock heavy subsystems (Ollama warmup, TTS, STT)."""
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


def test_persona_buttons_in_ui(tk_app):
    """Verify that Persona buttons exist in header and sidebar."""
    app, root = tk_app
    assert hasattr(app, "persona_header_btn")
    assert hasattr(app, "persona_studio_btn")
    assert app.persona_header_btn.winfo_exists()
    assert app.persona_studio_btn.winfo_exists()
    assert "▾" in app.persona_header_btn["text"]


def test_per_conversation_persona_binding(tk_app):
    """Verify switching between conversations updates the active persona."""
    app, root = tk_app

    # Create two conversations with different bound personas
    app.chats = [
        {
            "id": "chat-coding",
            "title": "Python Architecture",
            "messages": [{"role": "user", "content": "How to structure modules?", "time": "10:00 AM"}],
            "persona_id": "python_architect",
        },
        {
            "id": "chat-writing",
            "title": "Essay Thesis",
            "messages": [{"role": "user", "content": "Review my intro.", "time": "11:00 AM"}],
            "persona_id": "writing_tutor",
        },
    ]

    # Select Chat 1
    app.current_id = "chat-coding"
    app.current_persona_id = "python_architect"
    app.update_persona_ui()
    assert "🐍" in app.persona_header_btn["text"]
    assert "Python Architect" in app.persona_header_btn["text"]

    # Select Chat 2
    app.current_id = "chat-writing"
    app.current_persona_id = "writing_tutor"
    app.update_persona_ui()
    assert "📚" in app.persona_header_btn["text"]
    assert "Academic Writing Tutor" in app.persona_header_btn["text"]


def test_open_persona_studio_dialog(tk_app):
    """Verify the Persona Studio dialog opens and populates preset personas."""
    app, root = tk_app
    win = app.open_persona_studio()
    assert win is not None
    assert win.winfo_exists()
    assert win.title() == app.t("persona_studio_title")

    # Check that listbox contains built-in presets
    size = win.persona_listbox.size()
    assert size >= 6

    # Test cloning a persona inside dialog
    initial_count = len(app.persona_manager.list_personas())
    win.clone_current_persona()
    root.update_idletasks()
    assert len(app.persona_manager.list_personas()) == initial_count + 1

    win.destroy()
    app.persona_win = None
    root.update_idletasks()


def test_ask_ollama_injects_bound_persona(tk_app, monkeypatch):
    """Verify ask_ollama uses the chat's bound persona system prompt and temperature."""
    app, root = tk_app

    app.chats = [
        {
            "id": "chat-debug",
            "title": "Memory Leak Bug",
            "messages": [{"role": "user", "content": "Why is memory increasing?", "time": "12:00 PM"}],
            "persona_id": "debugger",
        }
    ]
    app.current_id = "chat-debug"

    captured_messages = []
    captured_options = {}

    def mock_ollama_chat(messages, **kwargs):
        captured_messages.extend(messages)
        captured_options.update(kwargs.get("options", {}))
        return types.SimpleNamespace(ok=True, answer="Here is the root cause diagnosis.")

    monkeypatch.setattr("desktop_app.ollama_chat", mock_ollama_chat)

    app.ask_ollama("chat-debug")

    # Verify system prompt has debugging instructions
    assert len(captured_messages) >= 2
    system_msg = captured_messages[0]
    assert system_msg["role"] == "system"
    assert "Debugging Specialist" in system_msg["content"] or "Software Debugging" in system_msg["content"]

    # Verify model options received persona temperature and context window
    debugger_persona = app.persona_manager.get_persona("debugger")
    assert captured_options["temperature"] == debugger_persona.temperature
    assert captured_options["num_ctx"] == debugger_persona.num_ctx
