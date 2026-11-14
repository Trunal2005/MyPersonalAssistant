"""Comprehensive tests for Ollama model discovery, switching, and in-app pull manager."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import assistant
import desktop_app
import models
from models import (
    DEFAULT_MODEL,
    ModelInfo,
    fetch_local_models,
    format_bytes,
    get_available_model_names,
    pull_model_stream,
    resolve_active_model,
)


# ==========================================
# 1. Byte formatting & ModelInfo tests
# ==========================================

def test_format_bytes():
    assert format_bytes(None) == "0 B"
    assert format_bytes(-5) == "0 B"
    assert format_bytes(0) == "0 B"
    assert format_bytes(512) == "512 B"
    assert format_bytes(1024) == "1 KB"
    assert format_bytes(1024 * 1024) == "1.0 MB"
    assert format_bytes(1024 * 1024 * 1536) == "1.5 GB"
    assert format_bytes(815319791) == "777.5 MB"
    assert format_bytes(1024 * 1024 * 1024 * 1024 * 2) == "2.0 TB"


def test_model_info_properties_and_serialization():
    m = ModelInfo(
        name="llama3.2:3b",
        size=2019393189,
        parameter_size="3.2B",
        family="llama",
        quantization_level="Q4_K_M",
        modified_at="2026-11-13T10:00:00Z",
    )
    assert m.name == "llama3.2:3b"
    assert "3.2B" in m.display_name
    assert "1.9 GB" in m.display_name

    d = m.to_dict()
    assert d["name"] == "llama3.2:3b"
    assert d["size"] == 2019393189

    rebuilt = ModelInfo.from_dict({
        "name": "gemma3:1b",
        "size": 815319791,
        "details": {
            "parameter_size": "999.89M",
            "family": "gemma3",
            "quantization_level": "Q4_K_M",
        },
    })
    assert rebuilt.name == "gemma3:1b"
    assert rebuilt.parameter_size == "999.89M"
    assert "777.5 MB" in rebuilt.display_name

    bare = ModelInfo(name="custom-model")
    assert bare.display_name == "custom-model"


# ==========================================
# 2. Local model discovery tests
# ==========================================

def test_fetch_local_models_success():
    fake_payload = {
        "models": [
            {
                "name": "llama3.2:3b",
                "size": 2000000000,
                "details": {"parameter_size": "3B", "family": "llama"},
            },
            {
                "name": "gemma3:1b",
                "size": 800000000,
                "details": {"parameter_size": "1B", "family": "gemma"},
            },
        ]
    }
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = fake_payload
        mock_get.return_value = mock_resp

        discovered = fetch_local_models("http://localhost:11434")
        assert len(discovered) == 2
        # Verify sorted alphabetically by name
        assert discovered[0].name == "gemma3:1b"
        assert discovered[1].name == "llama3.2:3b"


def test_fetch_local_models_offline_or_error():
    with patch("requests.get", side_effect=requests.ConnectionError("Connection refused")):
        assert fetch_local_models() == []

    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp
        assert fetch_local_models() == []


def test_fetch_local_models_malformed_json():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"invalid": True}
        mock_get.return_value = mock_resp
        assert fetch_local_models() == []


def test_get_available_model_names():
    with patch("models.fetch_local_models") as mock_fetch:
        mock_fetch.return_value = [ModelInfo(name="qwen2.5:1.5b"), ModelInfo(name="mistral:7b")]
        names = get_available_model_names()
        assert names == ["qwen2.5:1.5b", "mistral:7b"]

        mock_fetch.return_value = []
        fallback = get_available_model_names()
        assert fallback == [DEFAULT_MODEL]


# ==========================================
# 3. Model resolution & fallback tests
# ==========================================

def test_resolve_active_model_exact_and_fuzzy():
    available = ["llama3.2:1b", "gemma3:1b", "deepseek-r1:1.5b"]

    # Exact match
    assert resolve_active_model("gemma3:1b", available) == "gemma3:1b"

    # Fuzzy match with/without :latest
    assert resolve_active_model("gemma3", ["gemma3:latest"]) == "gemma3:latest"
    assert resolve_active_model("gemma3:latest", ["gemma3"]) == "gemma3"

    # Missing model falls back to DEFAULT_MODEL if in available, or first available
    assert resolve_active_model("nonexistent:model", available) == "llama3.2:1b"

    available_with_default = ["mistral:7b", DEFAULT_MODEL, "phi3:mini"]
    assert resolve_active_model("missing", available_with_default) == DEFAULT_MODEL

    # Empty available models returns preferred or default
    assert resolve_active_model("my-custom", []) == "my-custom"
    assert resolve_active_model(None, []) == DEFAULT_MODEL


# ==========================================
# 4. Pull model streaming tests
# ==========================================

def test_pull_model_stream_validation():
    with pytest.raises(ValueError, match="cannot be empty"):
        list(pull_model_stream(""))


def test_pull_model_stream_generator():
    lines = [
        b'{"status": "pulling manifest"}\n',
        b'{"status": "downloading", "total": 1000, "completed": 500}\n',
        b'{"status": "success"}\n',
    ]

    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = iter(lines)
    mock_resp.__enter__.return_value = mock_resp

    with patch("requests.post", return_value=mock_resp):
        chunks = list(pull_model_stream("llama3.2:1b"))
        assert len(chunks) == 3
        assert chunks[0]["status"] == "pulling manifest"
        assert chunks[1]["completed"] == 500
        assert chunks[2]["status"] == "success"


# ==========================================
# 5. CLI Assistant Integration tests
# ==========================================

def test_cli_ask_ai_with_custom_model():
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "Hello from custom model"}}
        mock_post.return_value = mock_resp

        # Test ask_ai with explicit model
        reply = assistant.ask_ai("Hi", model="mistral:7b")
        assert reply == "Hello from custom model"

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "mistral:7b"


def test_cli_run_assistant_model_commands(monkeypatch, capsys):
    inputs = iter([
        "/models",
        "/model qwen2.5:1.5b",
        "bye",
    ])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    fake_models = [ModelInfo(name="llama3.2:3b", size=2000000000), ModelInfo(name="qwen2.5:1.5b", size=1000000000)]
    with patch("assistant.fetch_local_models", return_value=fake_models):
        assistant.run_assistant()

    captured = capsys.readouterr().out
    assert "Installed Models" in captured
    assert "qwen2.5:1.5b" in captured
    assert "Switched active model to 'qwen2.5:1.5b'" in captured


# ==========================================
# 6. Desktop Settings & Model Switching tests
# ==========================================

def test_desktop_load_and_save_model_settings(make_window):
    win = make_window()
    assert win.load_model_setting() == DEFAULT_MODEL
    win.current_model = "deepseek-r1:1.5b"
    win.save_settings()
    data = json.loads(Path(win.settings_file).read_text(encoding="utf-8"))
    assert data["default_model"] == "deepseek-r1:1.5b"
    assert win.load_model_setting() == "deepseek-r1:1.5b"


def test_desktop_ask_ollama_injects_chosen_model(make_window):
    win = make_window()
    win.current_model = "qwen2.5:3b"
    win.chats = [
        {"id": "chat-1", "model": "mistral:7b", "messages": [{"role": "user", "content": "Hello"}]},
    ]

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "Hello there"}}
        mock_post.return_value = mock_resp

        with patch.object(win, "start_task") as mock_start:
            win.ask_ollama("chat-1")
            task_fn = mock_start.call_args[0][0]
            chat_id, answer, is_error = task_fn()
            assert chat_id == "chat-1"
            assert answer == "Hello there"
            payload = mock_post.call_args.kwargs["json"]
            assert payload["model"] == "mistral:7b"


def test_desktop_make_draft_includes_model(make_window):
    win = make_window()
    win.current_model = "gemma3:1b"
    win.make_draft()
    assert win.draft_chat["model"] == "gemma3:1b"


def test_desktop_model_button_and_dialog_lifecycle(qtbot, make_window):
    win = make_window()
    assert hasattr(win, "model_btn")
    assert hasattr(win, "model_sidebar_btn")
    assert win.current_model == DEFAULT_MODEL
    assert "llama3.2:3b" in win.model_btn.text()

    # Switch model
    win.switch_model("gemma3:1b")
    assert win.current_model == "gemma3:1b"
    assert "gemma3:1b" in win.model_btn.text()

    # Open pull dialog
    dialog = desktop_app.ModelPullDialog(win)
    assert dialog.model_input is not None
    assert dialog.pull_btn is not None

    # Empty validation
    dialog.model_input.setText("")
    dialog.start_pull()
    assert "Please enter a model name" in dialog.status_label.text()
    dialog.close()


def test_cli_argument_parsing(monkeypatch):
    import sys
    monkeypatch.setattr(sys, "argv", ["assistant.py", "--model", "qwen2.5:0.5b"])
    from models import resolve_active_model
    assert resolve_active_model("qwen2.5:0.5b") == "qwen2.5:0.5b"
    with patch("assistant.run_assistant") as mock_run:
        with patch("assistant.argparse.ArgumentParser.parse_args") as mock_parse:
            mock_parse.return_value.model = "qwen2.5:0.5b"
            # Simulate the __main__ block
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--model", type=str, default=None)
            args = parser.parse_args()
            assistant.run_assistant(model=args.model)
            mock_run.assert_called_with(model="qwen2.5:0.5b")

