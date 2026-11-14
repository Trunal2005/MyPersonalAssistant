"""Comprehensive tests for Full-Text Search and Multi-Format Chat Exporter (#52).

Tests:
1. search_engine: tokenize, spans, snippet extraction, query parser, inverted index,
   phrase searching, role filters, ranking, and fallback logic.
2. export_manager: markdown, standalone HTML5, JSON, and plain text exporters.
3. desktop_app UI: real-time search filtering, shortcut focus, and export context menu.
4. assistant CLI: /search, /export, and /chats commands.
"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from export_manager import (
    export_chat,
    export_to_html,
    export_to_json,
    export_to_markdown,
    export_to_text,
)
from search_engine import (
    ParsedQuery,
    SearchEngine,
    SearchResult,
    extract_snippet,
    find_term_spans,
    tokenize,
)


# ============================================================================
# 1. Search Engine Tests: Tokenization, Snippets, and Query Parsing
# ============================================================================

def test_tokenize_basic_and_edge_cases():
    assert tokenize("Hello, World!") == ["hello", "world"]
    assert tokenize("  Multiple   spaces \n\t and tabs  ") == ["multiple", "spaces", "and", "tabs"]
    assert tokenize("hyphen-separated and snake_case words") == ["hyphen", "separated", "and", "snake_case", "words"]
    assert tokenize("") == []
    assert tokenize("123 + 456 = 579") == ["123", "456", "579"]
    assert tokenize("   !@#$%^&*()   ") == []


def test_find_term_spans():
    text = "The quick brown fox jumps over the lazy dog. Quick foxes are fast."
    spans = find_term_spans(text, ["quick", "fox"])
    assert len(spans) == 4
    # "quick" at 4..9, "fox" at 16..19, "Quick" at 45..50, "fox" inside "foxes" at 51..54
    matched_substrings = [text[s[0]:s[1]].lower() for s in spans]
    assert matched_substrings == ["quick", "fox", "quick", "fox"]


def test_extract_snippet():
    text = "In computer science, a binary search tree is a rooted binary tree data structure."
    spans = find_term_spans(text, ["binary"])
    assert spans
    snippet = extract_snippet(text, ["binary"], max_len=40)
    assert "binary" in snippet.lower()
    # Check short text doesn't add ellipses
    short_text = "Hello world"
    short_spans = find_term_spans(short_text, ["world"])
    assert extract_snippet(short_text, ["world"], max_len=80) == "Hello world"


def test_parsed_query():
    pq = ParsedQuery.parse('role:user "machine learning" python tutorial')
    assert pq.role == "user"
    assert "machine learning" in pq.phrases
    assert "python" in pq.terms
    assert "tutorial" in pq.terms

    pq_assistant = ParsedQuery.parse('role:assistant "neural network"')
    assert pq_assistant.role == "assistant"
    assert pq_assistant.phrases == ["neural network"]
    assert pq_assistant.terms == []

    pq_empty = ParsedQuery.parse("   ")
    assert pq_empty.terms == []
    assert pq_empty.phrases == []
    assert pq_empty.role is None


# ============================================================================
# 2. Search Engine Tests: Indexing, Ranking, and Query Execution
# ============================================================================

@pytest.fixture
def sample_chats():
    return [
        {
            "id": "chat-1",
            "title": "Python Algorithms",
            "messages": [
                {"role": "user", "content": "How do I implement quicksort in Python?", "time": "10:00 AM"},
                {"role": "assistant", "content": "Here is an implementation of quicksort with recursion in Python.", "time": "10:01 AM"},
            ],
        },
        {
            "id": "chat-2",
            "title": "Machine Learning Notes",
            "messages": [
                {"role": "user", "content": "Explain gradient descent in neural networks.", "time": "11:00 AM"},
                {"role": "assistant", "content": "Gradient descent optimizes the loss function of deep neural networks.", "time": "11:02 AM"},
            ],
        },
        {
            "id": "chat-3",
            "title": "General Conversation",
            "messages": [
                {"role": "user", "content": "Hello Jugnu, what is the weather today?", "time": "12:00 PM"},
                {"role": "assistant", "content": "I am an offline assistant running locally.", "time": "12:01 PM"},
            ],
        },
    ]


def test_search_single_term(sample_chats):
    engine = SearchEngine(sample_chats)
    results = engine.search("quicksort")
    assert len(results) == 2  # Both user and assistant mention quicksort
    assert all(r.chat_id == "chat-1" for r in results)
    assert any(r.role == "user" for r in results)
    assert any(r.role == "assistant" for r in results)


def test_search_case_insensitive_and_punctuation(sample_chats):
    engine = SearchEngine(sample_chats)
    res_lower = engine.search("python")
    res_upper = engine.search("PYTHON")
    res_punct = engine.search("python?")
    assert len(res_lower) == len(res_upper) == len(res_punct) == 2


def test_search_phrase_query(sample_chats):
    engine = SearchEngine(sample_chats)
    # Exact phrase matching
    res_phrase = engine.search('"gradient descent"')
    assert len(res_phrase) == 2
    assert all(r.chat_id == "chat-2" for r in res_phrase)

    # Non-contiguous phrase should not match phrase query
    res_no_phrase = engine.search('"gradient networks"')
    assert len(res_no_phrase) == 0


def test_search_role_filter(sample_chats):
    engine = SearchEngine(sample_chats)
    res_user = engine.search("role:user python")
    assert len(res_user) == 1
    assert res_user[0].role == "user"
    assert res_user[0].chat_id == "chat-1"

    res_assistant = engine.search("role:assistant python")
    assert len(res_assistant) == 1
    assert res_assistant[0].role == "assistant"
    assert res_assistant[0].chat_id == "chat-1"


def test_search_empty_and_no_match(sample_chats):
    engine = SearchEngine(sample_chats)
    assert engine.search("") == []
    assert engine.search("nonexistentterm12345") == []


def test_search_ranking_relevance(sample_chats):
    engine = SearchEngine(sample_chats)
    results = engine.search("neural networks gradient")
    assert len(results) > 0
    # Top result should have highest score
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_search_incremental_updates(sample_chats):
    engine = SearchEngine(sample_chats[:2])
    assert len(engine.search("weather")) == 0

    # Index third chat dynamically
    engine.index_chat(sample_chats[2])
    assert len(engine.search("weather")) == 1

    # Remove third chat dynamically
    engine.remove_chat("chat-3")
    assert len(engine.search("weather")) == 0


# ============================================================================
# 3. Chat Exporter Tests: Markdown, HTML, JSON, and Text
# ============================================================================

@pytest.fixture
def sample_chat():
    return {
        "id": "export-test-1",
        "title": "Sorting Algorithms Guide",
        "created_at": "2026-11-14T10:00:00",
        "messages": [
            {
                "role": "user",
                "content": "Can you give me a Python quicksort example?",
                "time": "10:00 AM",
            },
            {
                "role": "assistant",
                "content": "Sure! Here is the code:\n\n```python\ndef quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return quicksort(left) + middle + quicksort(right)\n```\nEnjoy coding!",
                "time": "10:01 AM",
            },
        ],
    }


def test_export_to_markdown(sample_chat):
    md = export_to_markdown(sample_chat)
    assert "title: \"Sorting Algorithms Guide\"" in md
    assert "# Sorting Algorithms Guide" in md
    assert "### You" in md
    assert "### JUGNU" in md
    assert "```python" in md
    assert "def quicksort(arr):" in md
    assert "Enjoy coding!" in md


def test_export_to_html(sample_chat):
    # Test Dark Mode HTML export
    html_dark = export_to_html(sample_chat, dark_mode=True)
    assert "<!DOCTYPE html>" in html_dark
    assert "<title>Sorting Algorithms Guide - JUGNU Transcript</title>" in html_dark
    assert "data-theme=\"dark\"" in html_dark
    assert "class=\"bubble user\"" in html_dark
    assert "class=\"bubble assistant\"" in html_dark
    assert "<pre><code" in html_dark
    assert "language-python" in html_dark
    assert "def quicksort(arr):" in html_dark
    # Zero external CDN links
    assert "http://" not in html_dark and "https://" not in html_dark

    # Test Light Mode HTML export
    html_light = export_to_html(sample_chat, dark_mode=False)
    assert "data-theme=\"light\"" in html_light


def test_export_to_json(sample_chat):
    json_str = export_to_json(sample_chat)
    data = json.loads(json_str)
    assert data["id"] == "export-test-1"
    assert data["title"] == "Sorting Algorithms Guide"
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert "quicksort" in data["messages"][1]["content"]


def test_export_to_text(sample_chat):
    txt = export_to_text(sample_chat)
    assert "============================================================" in txt
    assert "Sorting Algorithms Guide" in txt
    assert "[You] (10:00 AM):" in txt
    assert "[JUGNU] (10:01 AM):" in txt
    assert "def quicksort(arr):" in txt


def test_export_chat_dispatcher(sample_chat, tmp_path):
    # Test exporting to each format to disk
    for ext in ["md", "html", "json", "txt"]:
        out_file = str(tmp_path / f"transcript.{ext}")
        result_path = export_chat(sample_chat, ext, out_file)
        assert os.path.exists(result_path)
        with open(result_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert len(content) > 50

    # Test invalid format
    with pytest.raises(ValueError, match="Unsupported export format"):
        export_chat(sample_chat, "docx", str(tmp_path / "transcript.docx"))


# ============================================================================
# 4. CLI Assistant Search & Export Command Tests
# ============================================================================

def test_assistant_cli_search_and_export(capsys, monkeypatch, tmp_path):
    import assistant

    fake_chats = [
        {
            "id": "chat-cli-1",
            "title": "Rust vs Python",
            "messages": [
                {"role": "user", "content": "Compare memory safety in Rust vs Python.", "time": "2:00 PM"},
                {"role": "assistant", "content": "Rust guarantees memory safety at compile-time via ownership.", "time": "2:01 PM"},
            ],
        }
    ]

    monkeypatch.setattr(assistant, "_load_history", lambda: fake_chats)

    # Test show_help mentions search, export, and chats
    assistant.show_help()
    out = capsys.readouterr().out
    assert "/search" in out
    assert "/export" in out
    assert "/chats" in out


def test_assistant_cli_search_and_export_commands(capsys, monkeypatch, tmp_path):
    import assistant

    fake_chats = [
        {
            "id": "c-algo",
            "title": "Algorithms in Python",
            "messages": [
                {"role": "user", "content": "How does merge sort work?", "time": "12:00 PM"},
                {"role": "assistant", "content": "Merge sort is a divide and conquer algorithm.", "time": "12:01 PM"},
            ],
        }
    ]
    monkeypatch.setattr(assistant, "_load_history", lambda: fake_chats)

    # Run CLI interactive loop with /search, /export, /chats, and bye
    monkeypatch.chdir(tmp_path)
    inputs = iter([
        "/search",
        "/search merge",
        "/search nonexistent_xyz",
        "/export json",
        "/chats",
        "bye",
    ])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))

    assistant.run_assistant()
    out = capsys.readouterr().out
    assert "Please provide a search query" in out
    assert "Found 2 match(es)" in out
    assert "No matches found" in out
    assert "Successfully exported" in out
    assert "Saved Chats (1)" in out


# ============================================================================
# 5. Desktop PySide6 UI Search & Export Tests
# ============================================================================

def test_ui_sidebar_search_filtering(make_window):
    chats = [
        {
            "id": "c1",
            "title": "Python Basics",
            "messages": [
                {"role": "user", "content": "How do lists work?"},
                {"role": "assistant", "content": "Lists are mutable sequences in Python."},
            ],
        },
        {
            "id": "c2",
            "title": "Rust Concurrency",
            "messages": [
                {"role": "user", "content": "Tell me about channels."},
                {"role": "assistant", "content": "Channels allow thread-safe message passing."},
            ],
        },
        {
            "id": "c3",
            "title": "Web Development",
            "messages": [
                {"role": "user", "content": "What is CSS Flexbox?"},
                {"role": "assistant", "content": "Flexbox is a 1D layout model."},
            ],
        },
    ]
    app = make_window(chats)
    assert app.history_list.count() == 3

    # Type search query "Rust"
    app.search_entry.setText("Rust")
    assert app.history_list.count() == 1
    assert "Rust Concurrency" in app.history_list.item(0).text()
    assert "1" in app.history_label.text()

    # Search for term in content "sequences"
    app.search_entry.setText("sequences")
    assert app.history_list.count() == 1
    assert "Python Basics" in app.history_list.item(0).text()

    # Search for non-existent term
    app.search_entry.setText("nonexistentquery999")
    assert app.history_list.count() == 0
    assert app.history_label.text() == app.t("search_no_matches")

    # Clear search
    app.search_entry.clear()
    assert app.history_list.count() == 3
    assert app.history_label.text() == app.t("history_label")


def test_ui_focus_search_shortcut(make_window, monkeypatch):
    app = make_window([{"id": "c1", "title": "Test Chat", "messages": []}])
    focused = []
    monkeypatch.setattr(app.search_entry, "setFocus", lambda: focused.append(True))
    app.focus_search()
    assert focused == [True]


def test_ui_export_chat_dialog(make_window, monkeypatch, tmp_path):
    chat = {
        "id": "export-gui-1",
        "title": "Export GUI Test",
        "messages": [
            {"role": "user", "content": "Hello for export"},
            {"role": "assistant", "content": "World exported successfully"},
        ],
    }
    app = make_window([chat])
    out_file = str(tmp_path / "gui_export.md")

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (out_file, "Markdown (*.md)"))
    mock_info = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", mock_info)

    app.export_chat_dialog("export-gui-1")

    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "Export GUI Test" in content
        assert "Hello for export" in content
    assert mock_info.called
