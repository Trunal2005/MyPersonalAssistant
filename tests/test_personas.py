"""Comprehensive automated tests for Customizable Assistant Personas (#47)."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import requests

import assistant
import jugnu_core as core
from personas import (
    BUILTIN_PERSONAS,
    DEFAULT_TEMPERATURE,
    Persona,
    PersonaManager,
    get_persona,
    list_personas,
)
from strings import build_system_prompt, get_string


# ============================================================================
# 1. Data Model & Built-in Presets
# ============================================================================

def test_builtin_personas_present():
    ids = [p.id for p in BUILTIN_PERSONAS]
    assert "default" in ids
    assert "code" in ids
    assert "creative" in ids
    assert "tutor" in ids
    assert "concise" in ids

    code = next(p for p in BUILTIN_PERSONAS if p.id == "code")
    assert code.temperature == 0.2
    assert "software engineer" in code.system_prompt.lower()
    assert code.is_builtin is True

    creative = next(p for p in BUILTIN_PERSONAS if p.id == "creative")
    assert creative.temperature == 0.85
    assert creative.is_builtin is True

    concise = next(p for p in BUILTIN_PERSONAS if p.id == "concise")
    assert concise.temperature == 0.3
    assert concise.is_builtin is True


def test_persona_temperature_clamping():
    p_low = Persona(id="low", name="Low", description="", system_prompt="test", temperature=-0.5)
    assert p_low.temperature == 0.0

    p_high = Persona(id="high", name="High", description="", system_prompt="test", temperature=3.5)
    assert p_high.temperature == 1.5

    p_invalid = Persona(id="nan", name="NaN", description="", system_prompt="test", temperature="not_a_num")
    assert p_invalid.temperature == DEFAULT_TEMPERATURE


def test_persona_serialization():
    p = Persona(
        id="custom_1",
        name="Tester",
        description="Testing role",
        system_prompt="You are a test assistant.",
        temperature=0.45,
        icon="🧪",
        is_builtin=False,
    )
    d = p.to_dict()
    assert d["id"] == "custom_1"
    assert d["name"] == "Tester"
    assert d["temperature"] == 0.45
    assert d["icon"] == "🧪"
    assert d["is_builtin"] is False

    reconstructed = Persona.from_dict(d)
    assert reconstructed.id == p.id
    assert reconstructed.name == p.name
    assert reconstructed.system_prompt == p.system_prompt
    assert reconstructed.temperature == p.temperature
    assert reconstructed.display_label == "🧪  Tester"


# ============================================================================
# 2. Persona Manager & Custom CRUD
# ============================================================================

def test_persona_manager_crud(tmp_path):
    personas_file = tmp_path / "personas.json"
    mgr = PersonaManager(str(personas_file))

    # Initial state has built-ins only
    assert len(mgr.custom()) == 0
    assert len(mgr.all()) == len(BUILTIN_PERSONAS)

    # Add custom persona
    custom_p = mgr.add_custom(
        name="Python Coach",
        description="Helps with Python idioms and testing",
        system_prompt="You are a helpful Python coach.",
        temperature=0.35,
        icon="🐍",
    )
    assert custom_p.id.startswith("custom_")
    assert len(mgr.custom()) == 1
    assert len(mgr.all()) == len(BUILTIN_PERSONAS) + 1
    assert os.path.exists(personas_file)

    # Persistence verification
    reloaded_mgr = PersonaManager(str(personas_file))
    assert len(reloaded_mgr.custom()) == 1
    persisted = reloaded_mgr.get(custom_p.id)
    assert persisted.name == "Python Coach"
    assert persisted.temperature == 0.35
    assert persisted.icon == "🐍"

    # Update custom persona
    updated = mgr.update_custom(custom_p.id, name="Advanced Python Coach", temperature=0.25)
    assert updated.name == "Advanced Python Coach"
    assert updated.temperature == 0.25

    # Delete custom persona
    assert mgr.delete_custom(custom_p.id) is True
    assert len(mgr.custom()) == 0
    assert len(mgr.all()) == len(BUILTIN_PERSONAS)


def test_persona_manager_validation(tmp_path):
    mgr = PersonaManager(str(tmp_path / "personas.json"))

    with pytest.raises(ValueError, match="cannot be empty"):
        mgr.add_custom(name="", description="", system_prompt="Valid prompt")

    with pytest.raises(ValueError, match="System prompt cannot be empty"):
        mgr.add_custom(name="Valid Name", description="", system_prompt="")

    with pytest.raises(ValueError, match="Built-in personas cannot be modified"):
        mgr.update_custom("default", name="Hacked")

    with pytest.raises(ValueError, match="Built-in personas cannot be deleted"):
        mgr.delete_custom("code")


def test_persona_manager_get_fallback():
    mgr = PersonaManager("non_existent_file.json")
    # Exact lookup
    assert mgr.get("code").id == "code"
    # Case-insensitive lookup
    assert mgr.get("CREATIVE").id == "creative"
    # By name
    assert mgr.get("Code Expert").id == "code"
    # Fallback to default
    assert mgr.get("unknown_xyz").id == "default"
    assert mgr.get(None).id == "default"


# ============================================================================
# 3. System Prompt & Core Integration
# ============================================================================

def test_build_system_prompt_with_persona():
    # Without persona
    default_prompt = build_system_prompt("en", "12:00 PM")
    assert "JUGNU" in default_prompt

    # With code persona
    code_p = get_persona("code")
    code_prompt = build_system_prompt("en", "12:00 PM", persona=code_p)
    assert "software engineer" in code_prompt
    assert "12:00 PM" in code_prompt


def test_model_messages_injects_persona():
    chat = {
        "persona": "creative",
        "messages": [{"role": "user", "content": "Write a poem"}]
    }
    msgs = core.model_messages(chat, "en")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "creative writer" in msgs[0]["content"].lower()
    assert msgs[1]["content"] == "Write a poem"


def test_ask_ollama_injects_persona_temperature():
    captured_payloads = []

    def mock_post(url, json=None, **kwargs):
        captured_payloads.append(json)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"message":{"content":"Hello from Ollama"}}'
        return resp

    chat = {
        "persona": "code",
        "messages": [{"role": "user", "content": "Hello"}]
    }
    with patch("requests.post", side_effect=mock_post):
        ans, is_error = core.ask_ollama(chat, "en")

    assert is_error is False
    assert ans == "Hello from Ollama"
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["options"]["temperature"] == 0.2


# ============================================================================
# 4. CLI Assistant Integration
# ============================================================================

def test_cli_ask_ai_with_persona():
    captured_payloads = []

    def mock_post(url, json=None, **kwargs):
        captured_payloads.append(json)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"message":{"content":"Code reply"}}'
        return resp

    with patch("requests.post", side_effect=mock_post):
        res = assistant.ask_ai("Write quicksort", persona="code")

    assert res == "Code reply"
    assert len(captured_payloads) == 1
    payload = captured_payloads[0]
    assert payload["options"]["temperature"] == 0.2
    assert "software engineer" in payload["messages"][0]["content"]


def test_cli_persona_interactive_commands(capsys):
    inputs = iter([
        "/personas",
        "/persona code",
        "/persona",
        "bye",
    ])

    with patch("builtins.input", side_effect=lambda _: next(inputs)):
        with patch("assistant.greet"):
            assistant.run_assistant()

    captured = capsys.readouterr().out
    assert "Code Expert" in captured
    assert "Switched persona to" in captured
    assert "Current persona is" in captured


# ============================================================================
# 5. Desktop PySide6 UI Integration
# ============================================================================

def test_desktop_persona_selector_and_switching(window):
    # Default persona initially
    assert window.current_persona().id == "default"
    assert window.persona_combo.currentData() == "default"

    # Switch to code persona
    window.set_chat_persona("code")
    assert window.current_persona().id == "code"
    assert window.persona_combo.currentData() == "code"
    assert window.current_chat().get("persona") == "code"

    # New chat inherits the active persona
    window.new_chat()
    assert window.current_chat().get("persona") == "code"


def test_desktop_ask_ollama_injects_persona(window, monkeypatch):
    window.set_chat_persona("creative")
    captured = []

    def mock_ask_ollama(chat, language, persona=None):
        captured.append(dict(chat))
        return "creative answer", False

    monkeypatch.setattr(core, "ask_ollama", mock_ask_ollama)
    window.ask_ollama(window.current_id)

    # Let task process
    window.wait_for_tasks(1000)
    assert len(captured) == 1
    assert captured[0].get("persona") == "creative"


def test_desktop_persona_manager_dialog(window):
    window.open_persona_manager()
    assert window.persona_dialog is not None
    dlg = window.persona_dialog

    # Builtin persona cannot be modified or deleted
    assert dlg.save_btn.isEnabled() is False
    assert dlg.delete_btn.isEnabled() is False

    # New persona creation
    dlg.on_new()
    assert dlg.save_btn.isEnabled() is True
    dlg.name_edit.setText("Science Whiz")
    dlg.desc_edit.setText("Physics & Chemistry")
    dlg.temp_slider.setValue(45)
    dlg.prompt_edit.setPlainText("You are a science mentor.")
    dlg.on_save()

    p = window.persona_manager.get("Science Whiz")
    assert p.name == "Science Whiz"
    assert p.temperature == 0.45

    # Check that it appeared in window's persona_combo
    idx = window.persona_combo.findData(p.id)
    assert idx >= 0

    # Delete custom persona
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=16384):  # QMessageBox.Yes = 0x4000 = 16384
        dlg.on_delete()

    assert window.persona_manager.get("Science Whiz").id == "default"

    dlg.close()
    assert window.persona_dialog is None
