"""Markdown in chat bubbles, in the offscreen Qt window."""
import pytest

import jugnu_core
from strings import get_string

pytest.importorskip("PySide6")

RICH = """# Title

Some **bold**, *italic* and `inline` text.

- first
- second
  - nested

```python
def add(a, b):
    return a + b
```

> a quote

Last line."""


def shown(bubble):
    return bubble.body.toPlainText()


def clipboard():
    from PySide6.QtWidgets import QApplication
    return QApplication.clipboard().text()


def click_code_copy(bubble, index):
    from PySide6.QtCore import QUrl
    bubble.on_link(QUrl(f"copy:{index}"))


def test_assistant_markdown_is_styled(window):
    bubble = window.add_bubble("assistant", "A **bold** word and `code` and *slant*.")
    assert shown(bubble) == "A bold word and code and slant."
    html = bubble.body.toHtml()
    assert "font-weight:600" in html and "font-style:italic" in html


def test_your_own_messages_are_shown_exactly_as_typed(window):
    bubble = window.add_bubble("user", "I typed **this** and `that` <b>tag</b>")
    assert shown(bubble) == "I typed **this** and `that` <b>tag</b>"
    assert bubble.codes == []


def test_all_block_styles_are_drawn(window):
    bubble = window.add_bubble("assistant", RICH)
    body = shown(bubble)
    assert "#" not in body and "**" not in body and "```" not in body and "`" not in body
    assert "def add(a, b):\n    return a + b" in body
    for text in ("Title", "• first", "◦ nested", "│ a quote", "Last line."):
        assert text in body


def test_code_block_link_copies_the_exact_code(window):
    code = "def add(a, b):\n    return a + b  # **keep**\n\n\nprint(add(1, 2))"
    bubble = window.add_bubble("assistant", f"Try this:\n```python\n{code}\n```\nDone.")
    assert window.t("code_copy_btn") in shown(bubble)
    click_code_copy(bubble, 0)
    assert clipboard() == code
    assert window.t("code_copied_btn") in shown(bubble)


def test_each_code_block_copies_its_own_code(window):
    bubble = window.add_bubble("assistant", "```\nfirst\n```\ntext\n```sh\nsecond\n```")
    click_code_copy(bubble, 1)
    assert clipboard() == "second"
    click_code_copy(bubble, 0)
    assert clipboard() == "first"


def test_message_copy_button_still_copies_the_original_markdown(qtbot, window):
    from PySide6.QtCore import Qt
    import qt_app

    bubble = window.add_bubble("assistant", "**bold** text")
    qtbot.mouseClick(bubble.copy_btn, Qt.LeftButton)
    assert clipboard() == "**bold** text"
    assert bubble.copy_btn.text() == qt_app.COPIED_TEXT
    qtbot.waitUntil(lambda: bubble.copy_btn.text() == qt_app.COPY_TEXT, timeout=3000)


def test_copy_link_text_follows_the_language(window):
    window.language = "hinglish"
    bubble = window.add_bubble("assistant", "```\nx\n```")
    assert window.t("code_copy_btn") in shown(bubble)
    assert window.t("code_copy_btn") != get_string("en", "code_copy_btn")


def test_styling_failure_falls_back_to_plain_text(window, monkeypatch):
    import qt_app

    def broken(*args, **kwargs):
        raise RuntimeError("boom")
    monkeypatch.setattr(qt_app, "render_html", broken)
    bubble = window.add_bubble("assistant", "**bold** and\n```\ncode\n```")
    assert shown(bubble) == "**bold** and\n```\ncode\n```"
    assert bubble.codes == []


def test_broken_markdown_never_crashes(window):
    for text in ("**", "```", "```\n", "[x](", "> ", "# ", "- ", "``` ``` ```", "\\", "*" * 500,
                 "```py\n" + "x = 1\n" * 300, "😀 **😀**", ""):
        window.add_bubble("assistant", text)
    assert len(window.bubbles) == 13


def test_switching_theme_redraws_markdown_in_the_new_colours(window):
    chat = {"id": "x", "title": "t", "messages": [{"role": "assistant", "content": RICH}]}
    window.chats, window.current_id, window.draft_chat = [chat], "x", None
    window.display_chat()
    for _ in range(2):
        palette = jugnu_core.DARK if window.dark_mode else jugnu_core.LIGHT
        html = window.bubbles[-1].body.toHtml().lower()
        assert palette["code"].lower() in html and palette["inline_code"].lower() in html
        window.toggle_theme()


def test_read_aloud_and_voice_skip_the_markdown_symbols(window):
    window.tts.available = True
    window.read_aloud("# Title\n\nSome **bold** and `code`.")
    assert window.tts.spoken == ["Title\n\nSome bold and code."]
    window.tts.spoken.clear()
    window.voice_enabled = True
    chat = {"id": "y", "title": "t", "messages": [{"role": "user", "content": "hi"}]}
    window.chats, window.current_id, window.draft_chat = [chat], "y", None
    window.finish_answer("y", "**Hello** there")
    assert window.tts.spoken == ["Hello there"]
