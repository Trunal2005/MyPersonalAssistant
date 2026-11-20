"""Unit tests for exporter.py covering all four export formats and edge cases."""
import json
import os
import tempfile
import pytest

from exporter import (
    ConversationExporter,
    PurePdfWriter,
    export_html,
    export_json,
    export_markdown,
    export_pdf,
    extract_chat_metadata,
    sanitize_filename,
)


@pytest.fixture
def sample_chat():
    return {
        "id": "test-chat-123",
        "title": "Python Asyncio Guide",
        "messages": [
            {
                "role": "user",
                "content": "Can you explain asyncio with a short Python example?",
                "time": "10:00 AM",
            },
            {
                "role": "assistant",
                "content": (
                    "Sure! Here is a simple example using `asyncio.sleep`:\n\n"
                    "```python\n"
                    "import asyncio\n\n"
                    "async def main():\n"
                    "    print('Hello')\n"
                    "    await asyncio.sleep(1)\n"
                    "    print('World')\n\n"
                    "asyncio.run(main())\n"
                    "```\n\n"
                    "This demonstrates cooperative multitasking."
                ),
                "time": "10:01 AM",
            },
        ],
    }


@pytest.fixture
def empty_chat():
    return {
        "id": "empty-chat-000",
        "title": "Empty Conversation",
        "messages": [],
    }


@pytest.fixture
def single_message_chat():
    return {
        "id": "single-msg-111",
        "title": "Just Hello",
        "messages": [
            {
                "role": "user",
                "content": "Hello world!",
                "time": "11:30 AM",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Metadata & Utility Tests
# ---------------------------------------------------------------------------

def test_extract_chat_metadata(sample_chat):
    meta = extract_chat_metadata(sample_chat)
    assert meta["id"] == "test-chat-123"
    assert meta["title"] == "Python Asyncio Guide"
    assert meta["total_messages"] == 2
    assert meta["user_messages"] == 1
    assert meta["assistant_messages"] == 1
    assert meta["total_words"] > 15
    assert meta["total_chars"] > 50
    assert meta["tokens_approx"] > 0
    assert meta["first_message_time"] == "10:00 AM"
    assert meta["last_message_time"] == "10:01 AM"
    assert "exported_at" in meta
    assert "model" in meta


def test_extract_metadata_empty(empty_chat):
    meta = extract_chat_metadata(empty_chat)
    assert meta["total_messages"] == 0
    assert meta["user_messages"] == 0
    assert meta["assistant_messages"] == 0
    assert meta["total_words"] == 0
    assert meta["tokens_approx"] == 0
    assert meta["first_message_time"] == ""
    assert meta["last_message_time"] == ""


def test_sanitize_filename():
    assert sanitize_filename("Simple Title") == "Simple_Title"
    assert sanitize_filename('Dangerous/\\:*?"<>|Name') == "DangerousName"
    assert sanitize_filename("   Spaces   Everywhere   ") == "Spaces_Everywhere"
    assert sanitize_filename("") == "conversation"
    long_name = "a" * 100
    assert len(sanitize_filename(long_name, max_length=40)) == 40


# ---------------------------------------------------------------------------
# Markdown Export Tests (.md)
# ---------------------------------------------------------------------------

def test_export_markdown_with_frontmatter(sample_chat):
    md = export_markdown(sample_chat, {"include_metadata": True, "include_timestamps": True})
    assert md.startswith("---")
    assert 'title: "Python Asyncio Guide"' in md
    assert "model:" in md
    assert "# Python Asyncio Guide" in md
    assert "### 👤 User" in md
    assert "### 🤖 JUGNU" in md
    assert "10:00 AM" in md
    assert "```python" in md
    assert "async def main():" in md


def test_export_markdown_without_frontmatter(sample_chat):
    md = export_markdown(sample_chat, {"include_frontmatter": False, "include_metadata": False})
    assert not md.startswith("---")
    assert "# Python Asyncio Guide" in md
    assert "### 👤 User" in md


def test_export_markdown_empty_chat(empty_chat):
    md = export_markdown(empty_chat)
    assert "# Empty Conversation" in md
    assert "*(No messages in this conversation)*" in md


def test_export_markdown_single_message(single_message_chat):
    md = export_markdown(single_message_chat)
    assert "# Just Hello" in md
    assert "Hello world!" in md
    assert "### 🤖 JUGNU" not in md


# ---------------------------------------------------------------------------
# HTML Export Tests (.html)
# ---------------------------------------------------------------------------

def test_export_html_structure(sample_chat):
    out = export_html(sample_chat, {"include_metadata": True, "syntax_highlight": True}, theme="dark")
    assert "<!DOCTYPE html>" in out
    assert "<title>Python Asyncio Guide - JUGNU Conversation</title>" in out
    assert 'data-theme="dark"' in out
    assert "@media print" in out
    assert "code-block" in out or "highlight" in out
    assert "async" in out and "main" in out and "asyncio" in out
    assert "copyCode" in out  # interactive copy button script


def test_export_html_light_theme(sample_chat):
    out = export_html(sample_chat, theme="light")
    assert 'data-theme="light"' in out
    assert "theme-toggle" in out


def test_export_html_empty_chat(empty_chat):
    out = export_html(empty_chat)
    assert "<!DOCTYPE html>" in out
    assert "No messages in this conversation" in out


# ---------------------------------------------------------------------------
# JSON Export Tests (.json)
# ---------------------------------------------------------------------------

def test_export_json_full(sample_chat):
    raw = export_json(sample_chat, {"include_metadata": True})
    data = json.loads(raw)
    assert data["chat"]["title"] == "Python Asyncio Guide"
    assert data["metadata"]["total_messages"] == 2
    assert len(data["chat"]["messages"]) == 2
    assert data["chat"]["messages"][0]["role"] == "user"
    assert data["chat"]["messages"][1]["role"] == "assistant"


def test_export_json_openai_format(sample_chat):
    raw = export_json(sample_chat, {"schema": "openai"})
    data = json.loads(raw)
    assert "messages" in data
    assert len(data["messages"]) == 2
    for msg in data["messages"]:
        assert "role" in msg
        assert "content" in msg


def test_export_json_empty_chat(empty_chat):
    raw = export_json(empty_chat)
    data = json.loads(raw)
    assert data["chat"]["title"] == "Empty Conversation"
    assert data["chat"]["messages"] == []


# ---------------------------------------------------------------------------
# PDF Export Tests (.pdf)
# ---------------------------------------------------------------------------

def test_export_pdf_validity(sample_chat):
    pdf_bytes = export_pdf(sample_chat, {"include_metadata": True, "include_timestamps": True})
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    assert b"/Root" in pdf_bytes
    assert b"/Pages" in pdf_bytes


def test_export_pdf_empty_chat(empty_chat):
    pdf_bytes = export_pdf(empty_chat)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes


def test_export_pdf_multipage():
    # Construct a long conversation to test pagination and header/footer
    long_chat = {
        "id": "long-chat",
        "title": "Long Test Conversation",
        "messages": []
    }
    for i in range(25):
        long_chat["messages"].append({
            "role": "user",
            "content": f"Question {i}: Explain topic {i} in detail.",
            "time": f"10:{i:02d} AM",
        })
        long_chat["messages"].append({
            "role": "assistant",
            "content": f"Answer {i}:\nHere is a code snippet:\n```python\nx = {i} * 10\nprint(x)\n```\nEnd of answer.",
            "time": f"10:{i:02d} AM",
        })
    pdf_bytes = export_pdf(long_chat)
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    # Check that multiple pages were generated
    assert pdf_bytes.count(b"/Type /Page ") > 1


# ---------------------------------------------------------------------------
# Unified ConversationExporter & File Writing Tests
# ---------------------------------------------------------------------------

def test_exporter_class_methods(sample_chat):
    exporter = ConversationExporter(sample_chat)
    assert isinstance(exporter.to_markdown(), str)
    assert isinstance(exporter.to_html(), str)
    assert isinstance(exporter.to_json(), str)
    assert isinstance(exporter.to_pdf(), bytes)


def test_export_to_file_all_formats(sample_chat):
    exporter = ConversationExporter(sample_chat)
    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = os.path.join(tmpdir, "test.md")
        pdf_path = os.path.join(tmpdir, "test.pdf")
        html_path = os.path.join(tmpdir, "test.html")
        json_path = os.path.join(tmpdir, "test.json")

        exporter.export_to_file("md", md_path)
        exporter.export_to_file("pdf", pdf_path)
        exporter.export_to_file("html", html_path)
        exporter.export_to_file("json", json_path)

        assert os.path.isfile(md_path) and os.path.getsize(md_path) > 0
        assert os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 0
        assert os.path.isfile(html_path) and os.path.getsize(html_path) > 0
        assert os.path.isfile(json_path) and os.path.getsize(json_path) > 0

        # Verify content
        with open(md_path, "r", encoding="utf-8") as f:
            assert "Python Asyncio Guide" in f.read()

        with open(html_path, "r", encoding="utf-8") as f:
            assert "<!DOCTYPE html>" in f.read()

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert data["chat"]["title"] == "Python Asyncio Guide"

        with open(pdf_path, "rb") as f:
            header = f.read(8)
            assert header.startswith(b"%PDF-1.4")


def test_export_to_file_invalid_format(sample_chat):
    exporter = ConversationExporter(sample_chat)
    with tempfile.TemporaryDirectory() as tmpdir:
        bad_path = os.path.join(tmpdir, "test.docx")
        with pytest.raises(ValueError, match="Unsupported export format"):
            exporter.export_to_file("docx", bad_path)
