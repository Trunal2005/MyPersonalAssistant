"""UI and Integration tests for Voice Dictation Engine and Waveform HUD in JugnuApp."""
import os
import tkinter as tk
import time
import types
import pytest

from desktop_app import JugnuApp, WaveformHUD
from stt import (
    STTManager, STTState, MockAudioCapture, MockRecognizerBackend
)

_shared_root = None
_shared_app = None


@pytest.fixture(autouse=True)
def setup_stt_mock(monkeypatch):
    """Ensure mock audio capture and recognizer are used."""
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
    """Provide a reliable headless JugnuApp instance with mock STT."""
    global _shared_root, _shared_app
    if _shared_root is None:
        try:
            _shared_root = tk.Tk()
            _shared_root.withdraw()
        except tk.TclError:
            pytest.skip("No display available for Tk")

        mock_cap = MockAudioCapture(amplitude=0.3)
        mock_rec = MockRecognizerBackend("dictated test message comma works offline")
        _shared_app = JugnuApp(_shared_root)
        _shared_app.stt = STTManager(capture=mock_cap, recognizer=mock_rec)

    app = _shared_app
    # Reset app state before each test
    app.stt.cancel_listening()
    app.input_box.delete("1.0", "end")
    app.poll_stt()

    yield app, _shared_root

    # Cancel listening and clear timers after test
    app.stt.cancel_listening()
    app.poll_stt()


def test_waveform_hud_widget(tk_app):
    """Test WaveformHUD widget initialization, levels update and states."""
    app, root = tk_app
    hud = app.waveform_hud
    assert hud is not None
    assert not hud.is_listening
    assert not hud.is_transcribing

    # Start listening
    hud.start_listening()
    assert hud.is_listening
    assert not hud.is_transcribing

    # Update levels
    hud.update_levels(0.5, [0.2] * 28)
    assert hud.current_rms == 0.5
    assert hud.levels[0] == 0.2

    # Switch to transcribing
    hud.start_transcribing()
    assert not hud.is_listening
    assert hud.is_transcribing

    # Stop
    hud.stop()
    assert not hud.is_listening
    assert not hud.is_transcribing


def test_mic_button_present(tk_app):
    """Test mic button is created and placed in the input area."""
    app, root = tk_app
    assert hasattr(app, "mic_btn")
    assert app.mic_btn is not None
    text = app.mic_btn.cget("text")
    assert "Dictate" in text or "Bol" in text


def test_dictation_toggle_lifecycle(tk_app):
    """Test click-to-dictate toggles listening and transcribing."""
    app, root = tk_app

    assert not app.stt.is_listening
    assert not app.hud_shown

    # Toggle to start dictating
    app.toggle_dictation()
    assert app.stt.is_listening

    # Allow audio chunks to be captured
    time.sleep(0.12)

    # Process events in poll_stt
    app.poll_stt()
    assert app.hud_shown
    assert "Stop" in app.mic_btn.cget("text") or "Roko" in app.mic_btn.cget("text")

    # Toggle to stop and transcribe
    app.toggle_dictation()
    assert not app.stt.is_listening

    # Allow background mock transcription to complete
    time.sleep(0.2)
    app.poll_stt()
    assert not app.stt.is_listening
    assert not app.stt.is_transcribing
    assert not app.hud_shown

    # Verify dictated text was inserted into input_box
    input_text = app.input_box.get("1.0", "end-1c").strip()
    assert "Dictated test message, works offline." in input_text


def test_push_to_talk_hotkey_lifecycle(tk_app):
    """Test push-to-talk key press and release behavior."""
    app, root = tk_app
    app.input_box.delete("1.0", "end")

    # Simulate Ctrl+Space press
    res = app.on_hotkey_press()
    assert res == "break"
    assert app.stt.is_listening

    time.sleep(0.12)

    # Simulate holding for > 0.4s and releasing
    app._hotkey_pressed_time = time.monotonic() - 0.5
    res = app.on_hotkey_release()
    assert res == "break"
    assert not app.stt.is_listening

    # Wait for transcription
    time.sleep(0.2)
    app.poll_stt()
    input_text = app.input_box.get("1.0", "end-1c").strip()
    assert "Dictated test message, works offline." in input_text


def test_cancel_dictation(tk_app):
    """Test canceling dictation discards audio and hides HUD."""
    app, root = tk_app
    app.input_box.delete("1.0", "end")

    app.start_dictation()
    app.poll_stt()
    assert app.stt.is_listening
    assert app.hud_shown

    app.cancel_dictation()
    app.poll_stt()
    assert not app.stt.is_listening
    assert not app.hud_shown

    # Nothing should be inserted into input_box
    input_text = app.input_box.get("1.0", "end-1c").strip()
    assert input_text == ""


def test_send_message_cancels_active_listening(tk_app):
    """Sending a message while dictating should cancel active recording cleanly."""
    app, root = tk_app
    app.start_dictation()
    assert app.stt.is_listening

    app.input_box.insert("1.0", "User typed message")
    app.send_message()
    assert not app.stt.is_listening


def test_voice_settings_stt_options(tk_app):
    """Voice Settings window should render STT options and persist changes."""
    app, root = tk_app
    app.open_voice_settings()
    assert app.voice_win is not None
    assert "stt_section_label" in app.vw
    assert "stt_punct" in app.vw
    assert "stt_silence" in app.vw
    assert "stt_noise" in app.vw

    # Toggle a setting
    app.vw["stt_punct_var"].set(False)
    app.on_stt_setting_change()
    assert not app.stt_auto_punctuate
    assert not app.stt.auto_punctuate

    app.close_voice_settings()
    assert app.voice_win is None
