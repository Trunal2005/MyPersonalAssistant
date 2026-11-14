"""Multi-format conversation transcript exporter for JUGNU.

Exports conversations to:
- GitHub-Flavored Markdown (.md) with YAML frontmatter
- Standalone, self-contained, responsive HTML5 (.html) with dark/light themes
- Structured JSON (.json)
- Plain Text transcript (.txt)

100% offline, zero-dependency, pure Python standard library.
"""

from __future__ import annotations

from datetime import datetime
import html
import json
from pathlib import Path
import re
from typing import Any


EXPORT_FORMATS = ("md", "html", "json", "txt")


def export_to_markdown(chat: dict[str, Any], output_path: str | Path | None = None) -> str:
    """Export a conversation dictionary to GitHub-Flavored Markdown."""
    title = chat.get("title", "New Chat").strip()
    chat_id = chat.get("id", "")
    messages = chat.get("messages", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "---",
        f'title: "{title}"',
        f'chat_id: "{chat_id}"',
        f"turns: {len(messages)}",
        f'exported_at: "{now_str}"',
        'generator: "JUGNU | Just an Unusually Genius Neural Utility"',
        "---",
        "",
        f"# {title}",
        "",
        f"*Exported on {now_str} • {len(messages)} messages*",
        "",
        "---",
        "",
    ]

    for idx, msg in enumerate(messages, 1):
        role = msg.get("role", "user")
        content = msg.get("content", "").strip()
        time_text = msg.get("time", "")
        time_suffix = f" • *{time_text}*" if time_text else ""

        if role == "user":
            lines.append(f"### You{time_suffix}")
        else:
            err_tag = " ⚠️ [Error]" if msg.get("is_error") else ""
            lines.append(f"### JUGNU{err_tag}{time_suffix}")

        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    result = "\n".join(lines)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")
        return str(output_path)
    return result


def export_to_json(chat: dict[str, Any], output_path: str | Path | None = None) -> str:
    """Export a conversation dictionary to clean formatted JSON."""
    payload = dict(chat)
    payload["_export_metadata"] = {
        "version": "1.0",
        "generator": "JUGNU",
        "exported_at": datetime.now().isoformat(),
    }
    result = json.dumps(payload, indent=2, ensure_ascii=False)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")
        return str(output_path)
    return result


def export_to_text(chat: dict[str, Any], output_path: str | Path | None = None) -> str:
    """Export a conversation dictionary to plain text transcript."""
    title = chat.get("title", "New Chat").strip()
    messages = chat.get("messages", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "=" * 60,
        f" JUGNU CHAT TRANSCRIPT: {title}",
        f" Exported: {now_str}",
        "=" * 60,
        "",
    ]

    for msg in messages:
        role = "You" if msg.get("role") == "user" else "JUGNU"
        time_text = f" ({msg.get('time')})" if msg.get("time") else ""
        content = msg.get("content", "").strip()
        lines.append(f"[{role}]{time_text}:")
        lines.append(content)
        lines.append("-" * 40)
        lines.append("")

    result = "\n".join(lines)
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result, encoding="utf-8")
        return str(output_path)
    return result


def export_to_html(
    chat: dict[str, Any],
    output_path: str | Path | None = None,
    dark_mode: bool = False,
) -> str:
    """
    Export a conversation dictionary to a self-contained, responsive,
    standalone HTML5 document.
    """
    title = chat.get("title", "New Chat").strip()
    messages = chat.get("messages", [])
    now_str = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")

    # Colors
    bg = "#191728" if dark_mode else "#F7F4FF"
    panel_bg = "#211D35" if dark_mode else "#FFFFFF"
    text_color = "#F4EEFF" if dark_mode else "#27213B"
    muted = "#B7A9D8" if dark_mode else "#756B91"
    accent = "#8B6CF0" if dark_mode else "#8B5CF6"
    user_bubble = "#34365A" if dark_mode else "#E3DCFF"
    assistant_bubble = "#28223D" if dark_mode else "#F0EAFB"
    code_bg = "#17142A" if dark_mode else "#F4F0FF"
    border = "#463A66" if dark_mode else "#E2D9F7"

    messages_html = []
    for msg in messages:
        role = msg.get("role", "user")
        raw_content = msg.get("content", "")
        time_text = msg.get("time", "")
        is_error = msg.get("is_error", False)

        is_user = role == "user"
        sender_name = "You" if is_user else "JUGNU"
        sender_icon = "👤" if is_user else "🤖"
        bubble_cls = "user" if is_user else "assistant"
        align_cls = "align-right" if is_user else "align-left"

        # Format code blocks and newlines safely
        formatted_body = _format_html_content(raw_content)

        error_badge = '<span class="badge error-badge">Error</span>' if is_error else ""
        time_html = f'<span class="time">{html.escape(time_text)}</span>' if time_text else ""

        bubble_html = f"""
        <div class="message-row {align_cls}">
            <div class="bubble {bubble_cls}">
                <div class="bubble-header">
                    <span class="sender-tag">{sender_icon} <strong>{html.escape(sender_name)}</strong></span>
                    {error_badge}
                    {time_html}
                </div>
                <div class="bubble-body">{formatted_body}</div>
            </div>
        </div>
        """
        messages_html.append(bubble_html)

    body_content = "\n".join(messages_html) if messages_html else "<p class='empty'>No messages in this chat.</p>"

    theme_name = "dark" if dark_mode else "light"
    html_document = f"""<!DOCTYPE html>
<html lang="en" data-theme="{theme_name}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} - JUGNU Transcript</title>
    <style>
        :root {{
            --bg: {bg};
            --panel: {panel_bg};
            --text: {text_color};
            --muted: {muted};
            --accent: {accent};
            --user-bubble: {user_bubble};
            --assistant-bubble: {assistant_bubble};
            --code-bg: {code_bg};
            --border: {border};
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 15px;
            line-height: 1.6;
            padding: 24px 16px;
        }}
        .container {{
            max-width: 860px;
            margin: 0 auto;
        }}
        header {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px 24px;
            margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        .brand {{
            font-size: 13px;
            font-weight: 700;
            color: var(--accent);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        h1 {{
            font-size: 22px;
            font-weight: 700;
            color: var(--text);
            margin-bottom: 8px;
        }}
        .meta {{
            font-size: 13px;
            color: var(--muted);
        }}
        .chat-stream {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .message-row {{
            display: flex;
            width: 100%;
        }}
        .align-right {{
            justify-content: flex-end;
        }}
        .align-left {{
            justify-content: flex-start;
        }}
        .bubble {{
            max-width: 82%;
            border-radius: 14px;
            padding: 14px 18px;
            border: 1px solid var(--border);
            box-shadow: 0 1px 4px rgba(0,0,0,0.03);
            word-wrap: break-word;
        }}
        .user-bubble, .bubble.user {{
            background: var(--user-bubble);
            border-bottom-right-radius: 4px;
        }}
        .assistant-bubble, .bubble.assistant {{
            background: var(--assistant-bubble);
            border-bottom-left-radius: 4px;
        }}
        .bubble-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--muted);
            margin-bottom: 6px;
            border-bottom: 1px solid rgba(0,0,0,0.06);
            padding-bottom: 4px;
        }}
        .sender-tag {{
            color: var(--accent);
        }}
        .time {{
            margin-left: auto;
        }}
        .badge {{
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .error-badge {{
            background: #FEE2E2;
            color: #DC2626;
        }}
        .bubble-body {{
            font-size: 14.5px;
        }}
        pre {{
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            overflow-x: auto;
            font-family: Consolas, Monaco, "Courier New", monospace;
            font-size: 13px;
            margin: 10px 0;
        }}
        code {{
            background: var(--code-bg);
            padding: 2px 5px;
            border-radius: 4px;
            font-family: Consolas, Monaco, monospace;
            font-size: 13px;
        }}
        pre code {{
            background: transparent;
            padding: 0;
        }}
        p {{ margin-bottom: 8px; }}
        p:last-child {{ margin-bottom: 0; }}
        footer {{
            margin-top: 36px;
            text-align: center;
            font-size: 12px;
            color: var(--muted);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">🤖 JUGNU Personal Assistant Transcript</div>
            <h1>{html.escape(title)}</h1>
            <div class="meta">Exported on {html.escape(now_str)} • {len(messages)} messages</div>
        </header>

        <main class="chat-stream">
            {body_content}
        </main>

        <footer>
            Generated locally by <strong>JUGNU</strong> • Just an Unusually Genius Neural Utility
        </footer>
    </div>
</body>
</html>"""

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_document, encoding="utf-8")
        return str(output_path)
    return html_document


def _format_html_content(raw: str) -> str:
    """Format markdown-style text, code blocks, and inline code into safe HTML."""
    if not raw:
        return ""

    # Split by code blocks ```...```
    code_block_pattern = re.compile(r"```([a-zA-Z0-9_\-\.\+]*)\n(.*?)```", re.DOTALL)
    parts = []
    last_idx = 0

    for match in code_block_pattern.finditer(raw):
        # Text before code block
        before = raw[last_idx:match.start()]
        if before:
            parts.append(_format_html_text(before))

        lang = match.group(1).strip()
        code = match.group(2)
        lang_class = f' class="language-{html.escape(lang)}"' if lang else ""
        parts.append(f"<pre><code{lang_class}>{html.escape(code)}</code></pre>")
        last_idx = match.end()

    # Remaining text after last code block
    remainder = raw[last_idx:]
    if remainder:
        parts.append(_format_html_text(remainder))

    return "".join(parts)


def _format_html_text(text: str) -> str:
    """Escape text, handle inline code, bold, italics, and paragraph breaks."""
    # First escape HTML
    escaped = html.escape(text)

    # Inline code `code`
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)

    # Bold **text**
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)

    # Italics *text*
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)

    # Convert double newlines to paragraphs
    paragraphs = [f"<p>{p.replace('\n', '<br>')}</p>" for p in escaped.split("\n\n") if p.strip()]
    return "".join(paragraphs) if paragraphs else f"<p>{escaped}</p>"


def export_chat(
    chat: dict[str, Any],
    format_name: str,
    output_path: str | Path | None = None,
    dark_mode: bool = False,
) -> str:
    """Unified dispatcher for exporting chat transcripts."""
    fmt = format_name.lower().lstrip(".")
    if fmt in ("md", "markdown"):
        return export_to_markdown(chat, output_path)
    if fmt == "html":
        return export_to_html(chat, output_path, dark_mode=dark_mode)
    if fmt == "json":
        return export_to_json(chat, output_path)
    if fmt in ("txt", "text"):
        return export_to_text(chat, output_path)
    raise ValueError(f"Unsupported export format: {format_name}. Supported: {EXPORT_FORMATS}")
