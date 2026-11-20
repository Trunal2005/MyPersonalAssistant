"""UI and integration tests for Multi-Model Arena Comparison Mode."""
import tkinter as tk
import types
from unittest.mock import patch
import pytest

from desktop_app import JugnuApp
from arena import ArenaMetric, ArenaSession


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

    if getattr(app, "arena_win", None) and app.arena_win.winfo_exists():
        try:
            app.arena_win.destroy()
        except Exception:
            pass


def test_arena_button_presence(tk_app):
    """Verify that the Arena button exists in the sidebar."""
    app, root = tk_app
    assert hasattr(app, "arena_btn")
    assert app.arena_btn.winfo_exists()
    assert "Arena" in app.arena_btn["text"] or "⚔️" in app.arena_btn["text"]


def test_open_arena_dialog(tk_app):
    """Verify opening arena comparison modal and widget initialization."""
    app, root = tk_app
    win = app.open_arena_dialog()
    assert win is not None
    assert win.winfo_exists()
    assert hasattr(win, "prompt_box")
    assert hasattr(win, "btn_run")
    assert hasattr(win, "btn_stop")
    assert hasattr(win, "pane_a")
    assert hasattr(win, "pane_b")
    assert win.model_a_var.get() != ""


def test_arena_run_and_winner_selection(tk_app):
    """Verify running comparison and adopting winning response into chat."""
    app, root = tk_app
    win = app.open_arena_dialog()

    win.prompt_box.insert("1.0", "Which language has cleaner syntax?")

    # Setup mock session
    session = ArenaSession(win.model_a_var.get(), win.model_b_var.get())
    session.prompt = "Which language has cleaner syntax?"
    session.text_a = "Python has clean, readable syntax."
    session.text_b = "Ruby is expressive."
    session.metrics_a = ArenaMetric(model=win.model_a_var.get(), ttft=0.2, tps=35.0, total_latency=1.1, token_count=10, status="completed")
    session.metrics_b = ArenaMetric(model=win.model_b_var.get(), ttft=0.3, tps=28.0, total_latency=1.4, token_count=8, status="completed")
    app.arena_session = session

    initial_chat_count = len(app.chats)
    current_chat = app.current_chat()
    initial_msg_count = len(current_chat["messages"]) if current_chat else 0

    with patch("tkinter.messagebox.showinfo"):
        win.choose_winner("A")

    # Verify message was adopted into chat
    active_chat = app.current_chat()
    assert active_chat is not None
    assert len(active_chat["messages"]) == initial_msg_count + 2
    assert active_chat["messages"][-2]["role"] == "user"
    assert active_chat["messages"][-2]["content"] == "Which language has cleaner syntax?"
    assert active_chat["messages"][-1]["role"] == "assistant"
    assert active_chat["messages"][-1]["content"] == "Python has clean, readable syntax."


def test_arena_stop_action(tk_app):
    """Verify stop button invokes session cancellation."""
    app, root = tk_app
    win = app.open_arena_dialog()

    session = ArenaSession("m1", "m2")
    app.arena_session = session

    with patch.object(session, "cancel") as mock_cancel:
        win.do_stop()
        mock_cancel.assert_called_once()
