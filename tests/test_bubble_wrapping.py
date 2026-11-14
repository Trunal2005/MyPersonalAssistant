"""Chat bubbles wrap inside the chat area and re-wrap when the window is resized."""
import pytest

pytest.importorskip("PySide6")

LONG_SENTENCE = ("A long sentence with **bold** words and a list below. " * 8) + "\n- item\n- item"


def limit(window):
    import desktop_app
    return desktop_app.max_bubble_width(window.scroll.viewport().width())


def settle(qtbot, window):
    """Wait until the debounced re-fit after a resize has run."""
    qtbot.waitUntil(lambda: not window.resize_timer.isActive(), timeout=2000)


@pytest.mark.parametrize(("viewport", "expected"), [(300, 200), (800, 576), (1200, 720), (3000, 720)])
def test_max_bubble_width_scales_and_caps_at_720(viewport, expected):
    import desktop_app
    assert desktop_app.max_bubble_width(viewport) == expected


def test_bubbles_do_not_overflow_at_minimum_window_size(qtbot, window):
    window.resize(window.minimumSize())
    settle(qtbot, window)
    for text in ("x" * 3000, "word " * 400, LONG_SENTENCE, "https://example.com/" + "a" * 500):
        window.add_bubble("user", text)
        window.add_bubble("assistant", text)
    for bubble in window.bubbles:
        assert bubble.body.width() <= limit(window)


def test_short_messages_get_small_bubbles(window):
    assert window.add_bubble("assistant", "Hi").body.width() < 100
    assert window.add_bubble("user", "Hello").body.width() < 100


def test_long_rich_messages_are_never_cut_off(window):
    long_code = "\n".join(f"    value_{n} = compute({n}) + 'a fairly long string literal here'" for n in range(40))
    for text in (LONG_SENTENCE, LONG_SENTENCE * 6, f"```python\n{long_code}\n```", "# H1\n## H2\n### H3\n**x**"):
        bubble = window.add_bubble("assistant", text)
        doc = bubble.body.document()
        doc.setTextWidth(bubble.body.viewport().width())
        assert doc.size().height() <= bubble.body.height()  # nothing scrolls inside the bubble


def test_resizing_window_rewraps_existing_messages(qtbot, window):
    bubble = window.add_bubble("assistant", LONG_SENTENCE)
    wide = (bubble.body.width(), bubble.body.height())
    window.resize(window.minimumSize())
    settle(qtbot, window)
    qtbot.waitUntil(lambda: bubble.body.width() < wide[0], timeout=2000)
    assert bubble.body.height() > wide[1]
    assert bubble.body.width() <= limit(window)


def test_theme_toggle_after_resize_keeps_wrapped_width(qtbot, window):
    chat = {"id": "x", "title": "t", "messages": [{"role": "assistant", "content": LONG_SENTENCE}]}
    window.chats, window.current_id, window.draft_chat = [chat], "x", None
    window.resize(window.minimumSize())
    settle(qtbot, window)
    window.toggle_theme()
    assert window.bubbles[0].body.width() <= limit(window)
