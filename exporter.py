"""Comprehensive Multi-Format Conversation Exporter for JUGNU.

Exports conversations into multiple standard formats:
- Markdown (.md): Full markdown preservation with YAML frontmatter metadata.
- PDF (.pdf): Clean styled PDF document with title, timestamps, model metadata,
  running headers/footers, and code block formatting (100% pure Python, zero extra dependencies).
- HTML (.html): Self-contained offline-ready styled HTML with embedded CSS,
  syntax-highlighted code blocks (via Pygments), dark/light theme toggle, and print support.
- Structured JSON (.json): Raw chat dump suitable for backups or LLM fine-tuning datasets.

Features:
- Customizable metadata inclusion (model used, export timestamp, word count, tokens).
- Graceful handling of empty or single-message conversations without file corruption.
- Code blocks, tables, lists, blockquotes, and formatting preservation.
"""
from __future__ import annotations

import datetime
import html
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from core import MODEL as DEFAULT_MODEL

try:
    import pygments
    from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
    from pygments.formatters import HtmlFormatter
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False


# ---------------------------------------------------------------------------
# Metadata Extraction & Utilities
# ---------------------------------------------------------------------------

def extract_chat_metadata(chat: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and calculate comprehensive metadata for a conversation."""
    messages = chat.get("messages", []) if isinstance(chat, dict) else []
    total_messages = len(messages)
    user_messages = sum(1 for m in messages if m.get("role") == "user")
    assistant_messages = sum(1 for m in messages if m.get("role") == "assistant")

    total_words = 0
    total_chars = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
            total_words += len(content.split())

    # Rough approximation of token count (average ~1.33 tokens per word)
    tokens_approx = int(total_words * 1.33)

    first_time = ""
    last_time = ""
    if messages:
        first_time = messages[0].get("time", "")
        last_time = messages[-1].get("time", "")

    now = datetime.datetime.now()
    now_str = now.strftime("%Y-%m-%d %I:%M %p")
    iso_now = now.isoformat()

    title = chat.get("title", "New Chat") if isinstance(chat, dict) else "New Chat"
    chat_id = chat.get("id", "") if isinstance(chat, dict) else ""

    return {
        "id": chat_id,
        "title": title,
        "exported_at": now_str,
        "exported_iso": iso_now,
        "model": DEFAULT_MODEL,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "assistant_messages": assistant_messages,
        "total_words": total_words,
        "total_chars": total_chars,
        "tokens_approx": tokens_approx,
        "first_message_time": first_time,
        "last_message_time": last_time,
        "exported_by": "JUGNU Personal AI Assistant",
    }


def sanitize_filename(name: str, max_length: int = 50) -> str:
    """Sanitize string for safe filenames."""
    if not name:
        return "conversation"
    # Replace invalid filename characters
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    clean = re.sub(r"\s+", "_", clean)
    return clean[:max_length] if clean else "conversation"


# ---------------------------------------------------------------------------
# 1. Markdown Exporter (.md)
# ---------------------------------------------------------------------------

def export_markdown(chat: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> str:
    """Export conversation to Markdown (.md) with YAML frontmatter."""
    opts = options or {}
    include_metadata = opts.get("include_metadata", True)
    include_timestamps = opts.get("include_timestamps", True)
    include_frontmatter = opts.get("include_frontmatter", True)

    meta = extract_chat_metadata(chat)
    messages = chat.get("messages", []) if isinstance(chat, dict) else []

    lines = []

    # YAML Frontmatter
    if include_frontmatter:
        lines.append("---")
        lines.append(f'title: "{meta["title"]}"')
        lines.append(f'exported_at: "{meta["exported_iso"]}"')
        lines.append(f'model: "{meta["model"]}"')
        lines.append(f'total_messages: {meta["total_messages"]}')
        lines.append(f'total_words: {meta["total_words"]}')
        lines.append(f'tokens_approx: {meta["tokens_approx"]}')
        lines.append('exported_by: "JUGNU"')
        lines.append("---")
        lines.append("")

    # Document Header
    lines.append(f'# {meta["title"]}')
    lines.append("")

    if include_metadata:
        lines.append("> 🤖 **Model**: `" + meta["model"] + "`  ")
        lines.append(f'> 📅 **Exported**: {meta["exported_at"]}  ')
        lines.append(f'> 💬 **Messages**: {meta["total_messages"]} ({meta["user_messages"]} user, {meta["assistant_messages"]} assistant)  ')
        lines.append(f'> 📊 **Word Count**: {meta["total_words"]} words (~{meta["tokens_approx"]} tokens)')
        lines.append("")
        lines.append("---")
        lines.append("")

    if not messages:
        lines.append("*(No messages in this conversation)*")
        lines.append("")
        return "\n".join(lines)

    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip()
        time_str = msg.get("time", "")

        # Header for message
        time_part = f" *({time_str})*" if (include_timestamps and time_str) else ""
        if role == "user":
            lines.append(f"### 👤 User{time_part}")
        else:
            lines.append(f"### 🤖 JUGNU{time_part}")

        lines.append("")
        lines.append(content)
        lines.append("")

        if i < len(messages) - 1:
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. HTML Exporter (.html) with Syntax Highlighting & Dark/Light Theme
# ---------------------------------------------------------------------------

def _render_code_block_html(lang: str, code: str, syntax_highlight: bool = True) -> str:
    """Render a code block with Pygments syntax highlighting or clean pre/code."""
    code_text = code.rstrip("\n")
    lang = lang.strip().lower() if lang else ""

    if syntax_highlight and HAS_PYGMENTS:
        try:
            lexer = get_lexer_by_name(lang) if lang else guess_lexer(code_text)
        except Exception:
            lexer = TextLexer()
        formatter = HtmlFormatter(nowrap=True)
        highlighted_code = pygments.highlight(code_text, lexer, formatter)
    else:
        highlighted_code = html.escape(code_text)

    disp_lang = lang if lang else "text"
    return f"""<div class="code-block-wrapper">
  <div class="code-header">
    <span class="code-lang">{html.escape(disp_lang)}</span>
    <button class="copy-btn" onclick="copyCode(this)">⧉ Copy</button>
  </div>
  <pre><code class="highlight language-{html.escape(disp_lang)}">{highlighted_code}</code></pre>
</div>"""


def _markdown_to_html_content(text: str, syntax_highlight: bool = True) -> str:
    """Lightweight markdown to HTML converter for chat bubbles."""
    if not text:
        return ""

    # 1. Extract and preserve code blocks
    code_blocks = []

    def _replace_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        idx = len(code_blocks)
        rendered = _render_code_block_html(lang, code, syntax_highlight=syntax_highlight)
        code_blocks.append(rendered)
        return f"\n\nXXCODEBLOCK{idx}XX\n\n"

    text = re.sub(r"```([a-zA-Z0-9_\-+]*)\n?(.*?)```", _replace_code_block, text, flags=re.DOTALL)

    # 2. Escape HTML outside code blocks
    text = html.escape(text)

    # 3. Inline code
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # 4. LaTeX Math: $$math$$ and $math$
    text = re.sub(r"\$\$(.+?)\$\$", r'<div class="math-display">\1</div>', text, flags=re.DOTALL)
    text = re.sub(r"\$([^$\n]+)\$", r'<span class="math-inline">\1</span>', text)

    # 5. Bold & Italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)

    # 6. Headings
    text = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)

    # 7. Blockquotes
    text = re.sub(r"^> (.*?)$", r"<blockquote>\1</blockquote>", text, flags=re.MULTILINE)

    # 8. Unordered list items
    text = re.sub(r"^[*-] (.*?)$", r"<li>\1</li>", text, flags=re.MULTILINE)
    text = re.sub(r"(<li>.*?</li>\n?)+", r"<ul>\g<0></ul>", text)

    # 9. Paragraphs and line breaks
    paragraphs = text.split("\n\n")
    processed = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if p.startswith("<h") or p.startswith("<ul") or p.startswith("<blockquote") or p.startswith("XXCODEBLOCK"):
            processed.append(p)
        else:
            p_lines = p.split("\n")
            processed.append("<p>" + "<br>".join(p_lines) + "</p>")

    result = "\n".join(processed)

    # Restore code blocks
    for idx, rendered in enumerate(code_blocks):
        token = f"XXCODEBLOCK{idx}XX"
        result = result.replace(f"<p>{token}</p>", rendered).replace(token, rendered)

    return result


def export_html(chat: Dict[str, Any], options: Optional[Dict[str, Any]] = None,
                theme: str = "dark") -> str:
    """Export conversation to a fully self-contained styled HTML file."""
    opts = options or {}
    include_metadata = opts.get("include_metadata", True)
    include_timestamps = opts.get("include_timestamps", True)
    syntax_highlight = opts.get("syntax_highlight", True)

    meta = extract_chat_metadata(chat)
    messages = chat.get("messages", []) if isinstance(chat, dict) else []

    pygments_css = ""
    if HAS_PYGMENTS and syntax_highlight:
        formatter = HtmlFormatter(style="monokai" if theme == "dark" else "friendly")
        pygments_css = formatter.get_style_defs(".highlight")

    # Render message bubbles
    rendered_messages = []
    for msg in messages:
        role = msg.get("role", "unknown")
        raw_content = msg.get("content", "")
        time_str = msg.get("time", "")

        body_html = _markdown_to_html_content(raw_content, syntax_highlight=syntax_highlight)

        is_user = (role == "user")
        badge = "User" if is_user else "JUGNU"
        avatar = "👤" if is_user else "🤖"
        bubble_class = "msg-user" if is_user else "msg-assistant"
        time_html = f'<span class="msg-time">{html.escape(time_str)}</span>' if (include_timestamps and time_str) else ""

        rendered_messages.append(f"""
    <div class="message {bubble_class}">
      <div class="msg-header">
        <span class="avatar">{avatar}</span>
        <span class="author">{badge}</span>
        {time_html}
      </div>
      <div class="msg-content">
        {body_html}
      </div>
    </div>""")

    messages_html = "\n".join(rendered_messages) if rendered_messages else '<p class="empty-notice">(No messages in this conversation)</p>'

    metadata_html = ""
    if include_metadata:
        metadata_html = f"""
    <div class="metadata-card">
      <div class="meta-row">
        <span class="meta-item"><strong>Model:</strong> <code>{html.escape(meta["model"])}</code></span>
        <span class="meta-item"><strong>Exported:</strong> {html.escape(meta["exported_at"])}</span>
        <span class="meta-item"><strong>Messages:</strong> {meta["total_messages"]}</span>
        <span class="meta-item"><strong>Words:</strong> {meta["total_words"]}</span>
        <span class="meta-item"><strong>Tokens (approx):</strong> ~{meta["tokens_approx"]}</span>
      </div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="{html.escape(theme)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(meta["title"])} - JUGNU Conversation</title>
  <style>
    :root {{
      --bg: #191728;
      --card-bg: #211D35;
      --bubble-user: #34365A;
      --bubble-assistant: #2A2440;
      --text: #F4EEFF;
      --muted: #B7A9D8;
      --accent: #8B6CF0;
      --accent2: #D946A6;
      --border: #463A66;
      --code-bg: #17142A;
      --code-border: #3A3157;
      --header-bg: linear-gradient(135deg, #8B5CF6, #EC4899);
    }}
    [data-theme="light"] {{
      --bg: #F7F4FF;
      --card-bg: #FFFFFF;
      --bubble-user: #E3DCFF;
      --bubble-assistant: #F0EAFB;
      --text: #27213B;
      --muted: #756B91;
      --accent: #8B5CF6;
      --accent2: #EC4899;
      --border: #D9CFF5;
      --code-bg: #F8F6FF;
      --code-border: #E2D9F7;
      --header-bg: linear-gradient(135deg, #8B5CF6, #EC4899);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 24px 16px;
      transition: background 0.3s, color 0.3s;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    .header-banner {{
      background: var(--header-bg);
      color: #FFFFFF;
      padding: 28px 24px;
      border-radius: 14px;
      margin-bottom: 24px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.15);
      position: relative;
    }}
    .header-banner h1 {{
      font-size: 26px;
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .header-banner .tagline {{
      font-size: 14px;
      opacity: 0.9;
    }}
    .theme-toggle {{
      position: absolute;
      top: 24px;
      right: 24px;
      background: rgba(255,255,255,0.25);
      border: none;
      color: white;
      padding: 6px 14px;
      border-radius: 20px;
      cursor: pointer;
      font-weight: 600;
      font-size: 13px;
      backdrop-filter: blur(4px);
    }}
    .theme-toggle:hover {{ background: rgba(255,255,255,0.4); }}
    .metadata-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 28px;
    }}
    .meta-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 18px;
      font-size: 13px;
      color: var(--muted);
    }}
    .meta-item strong {{ color: var(--text); }}
    .meta-item code {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: Consolas, monospace;
    }}
    .message {{
      margin-bottom: 20px;
      padding: 18px 22px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: var(--bubble-assistant);
    }}
    .msg-user {{
      background: var(--bubble-user);
      border-color: var(--border);
    }}
    .msg-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 10px;
      font-weight: 600;
      font-size: 14px;
    }}
    .msg-header .author {{ color: var(--accent); }}
    .msg-user .msg-header .author {{ color: var(--accent2); }}
    .msg-header .msg-time {{
      font-size: 12px;
      color: var(--muted);
      font-weight: 400;
      margin-left: auto;
    }}
    .msg-content {{ font-size: 15px; word-break: break-word; }}
    .msg-content p {{ margin-bottom: 10px; }}
    .msg-content p:last-child {{ margin-bottom: 0; }}
    .msg-content h1, .msg-content h2, .msg-content h3 {{
      margin: 14px 0 8px 0;
      color: var(--accent);
    }}
    .msg-content blockquote {{
      border-left: 4px solid var(--accent);
      padding-left: 12px;
      margin: 10px 0;
      color: var(--muted);
      font-style: italic;
    }}
    .msg-content ul {{
      margin: 8px 0 8px 24px;
    }}
    .msg-content code {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 2px 6px;
      border-radius: 4px;
      font-family: Consolas, "Fira Code", monospace;
      font-size: 13px;
    }}
    .code-block-wrapper {{
      background: var(--code-bg);
      border: 1px solid var(--code-border);
      border-radius: 8px;
      margin: 14px 0;
      overflow: hidden;
    }}
    .code-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 14px;
      background: rgba(0,0,0,0.12);
      border-bottom: 1px solid var(--code-border);
      font-size: 12px;
      color: var(--muted);
      font-weight: 600;
    }}
    .copy-btn {{
      background: var(--accent);
      color: white;
      border: none;
      padding: 3px 10px;
      border-radius: 4px;
      cursor: pointer;
      font-size: 11px;
    }}
    .copy-btn:hover {{ opacity: 0.85; }}
    pre {{
      padding: 14px;
      overflow-x: auto;
      font-family: Consolas, "Fira Code", monospace;
      font-size: 13px;
      line-height: 1.5;
    }}
    .math-display {{
      background: var(--code-bg);
      border: 1px solid var(--border);
      padding: 10px;
      border-radius: 6px;
      margin: 10px 0;
      text-align: center;
      font-family: "Cambria Math", serif;
    }}
    .math-inline {{
      font-family: "Cambria Math", serif;
      background: var(--code-bg);
      padding: 2px 4px;
      border-radius: 4px;
    }}
    .empty-notice {{
      text-align: center;
      color: var(--muted);
      padding: 40px;
    }}
    .footer {{
      text-align: center;
      margin-top: 40px;
      font-size: 12px;
      color: var(--muted);
    }}
    /* Print Stylesheet */
    @media print {{
      body {{ background: white; color: black; padding: 0; }}
      .header-banner {{ background: none; color: black; border-bottom: 2px solid #8B5CF6; padding: 0 0 16px 0; box-shadow: none; }}
      .theme-toggle, .copy-btn {{ display: none !important; }}
      .message {{ border: 1px solid #ccc; background: #fff !important; page-break-inside: avoid; }}
      .code-block-wrapper {{ border: 1px solid #ddd; background: #f9f9f9 !important; page-break-inside: avoid; }}
    }}
    {pygments_css}
  </style>
</head>
<body>
  <div class="container">
    <div class="header-banner">
      <h1>{html.escape(meta["title"])}</h1>
      <div class="tagline">JUGNU | Just an Unusually Genius Neural Utility</div>
      <button class="theme-toggle" onclick="toggleTheme()">🌓 Switch Theme</button>
    </div>

    {metadata_html}

    <div class="conversation-thread">
      {messages_html}
    </div>

    <div class="footer">
      Generated by JUGNU Personal Assistant • 100% Local & Offline
    </div>
  </div>

  <script>
    function toggleTheme() {{
      const htmlEl = document.documentElement;
      const current = htmlEl.getAttribute('data-theme');
      htmlEl.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
    }}
    function copyCode(btn) {{
      const codeEl = btn.closest('.code-block-wrapper').querySelector('code');
      if (codeEl) {{
        navigator.clipboard.writeText(codeEl.innerText).then(() => {{
          const orig = btn.innerText;
          btn.innerText = '✓ Copied!';
          setTimeout(() => btn.innerText = orig, 1800);
        }});
      }}
    }}
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# 3. Structured JSON Exporter (.json)
# ---------------------------------------------------------------------------

def export_json(chat: Dict[str, Any], options: Optional[Dict[str, Any]] = None,
                indent: int = 2) -> str:
    """Export conversation to structured JSON."""
    opts = options or {}
    schema = opts.get("schema", "full")  # "full" or "openai"
    include_metadata = opts.get("include_metadata", True)
    include_timestamps = opts.get("include_timestamps", True)

    meta = extract_chat_metadata(chat)
    messages = chat.get("messages", []) if isinstance(chat, dict) else []

    if schema == "openai":
        # Standard OpenAI / ChatML fine-tuning dataset format
        openai_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            item: Dict[str, Any] = {"role": role, "content": content}
            if include_timestamps and "time" in msg:
                item["timestamp"] = msg["time"]
            openai_messages.append(item)
        return json.dumps({"messages": openai_messages}, indent=indent, ensure_ascii=False)

    # Full structured format
    clean_messages = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        item = {
            "role": role,
            "content": content,
            "word_count": len(content.split()) if isinstance(content, str) else 0,
        }
        if include_timestamps:
            item["timestamp"] = msg.get("time", "")
        clean_messages.append(item)

    payload: Dict[str, Any] = {
        "version": "1.0",
        "exported_by": "JUGNU",
    }
    if include_metadata:
        payload["metadata"] = meta

    payload["chat"] = {
        "id": meta["id"],
        "title": meta["title"],
        "messages": clean_messages,
    }

    return json.dumps(payload, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 4. Pure Python PDF Exporter (.pdf) - 100% Offline & Native
# ---------------------------------------------------------------------------

class PurePdfWriter:
    """A self-contained pure-Python PDF 1.4 document builder.

    Supports multi-page documents, fonts, text wrapping, running headers and footers,
    background panels, borders, and code blocks with zero external C dependencies.
    """

    def __init__(self, page_width: float = 595.0, page_height: float = 842.0):
        # Default A4 page dimensions in points (72 points = 1 inch)
        self.width = page_width
        self.height = page_height
        self.margin_left = 50.0
        self.margin_right = 50.0
        self.margin_top = 60.0
        self.margin_bottom = 50.0
        self.content_width = self.width - self.margin_left - self.margin_right

        self.pages: List[List[str]] = [[]]
        self.current_y = self.height - self.margin_top

    def new_page(self):
        """Append a new page."""
        self.pages.append([])
        self.current_y = self.height - self.margin_top

    def _cur(self) -> List[str]:
        return self.pages[-1]

    def check_space(self, height_needed: float):
        """Ensure space on current page; create new page if needed."""
        if self.current_y - height_needed < self.margin_bottom:
            self.new_page()

    def add_rect(self, x: float, y: float, w: float, h: float,
                 fill_rgb: Optional[Tuple[float, float, float]] = None,
                 stroke_rgb: Optional[Tuple[float, float, float]] = None,
                 stroke_width: float = 1.0):
        """Draw a filled or stroked rectangle."""
        ops = ["q"]
        if fill_rgb:
            ops.append(f"{fill_rgb[0]:.3f} {fill_rgb[1]:.3f} {fill_rgb[2]:.3f} rg")
        if stroke_rgb:
            ops.append(f"{stroke_rgb[0]:.3f} {stroke_rgb[1]:.3f} {stroke_rgb[2]:.3f} RG")
            ops.append(f"{stroke_width:.2f} w")
        ops.append(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re")
        if fill_rgb and stroke_rgb:
            ops.append("B")
        elif fill_rgb:
            ops.append("f")
        elif stroke_rgb:
            ops.append("S")
        ops.append("Q")
        self._cur().append(" ".join(ops))

    def _escape_pdf_text(self, text: str) -> str:
        """Escape parentheses and backslashes for PDF string literals."""
        # Replace latin-1 unsupported characters with ASCII approximation
        sanitized = text.encode("latin-1", "replace").decode("latin-1")
        return sanitized.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def add_text_line(self, x: float, y: float, text: str, font: str = "F1",
                      size: float = 10.0, rgb: Tuple[float, float, float] = (0, 0, 0)):
        """Draw a single line of text."""
        escaped = self._escape_pdf_text(text)
        cmd = (f"BT /{font} {size:.2f} Tf "
               f"{rgb[0]:.3f} {rgb[1]:.3f} {rgb[2]:.3f} rg "
               f"{x:.2f} {y:.2f} Td ({escaped}) Tj ET")
        self._cur().append(cmd)

    def wrap_words(self, text: str, max_chars_per_line: int) -> List[str]:
        """Wrap text into lines fitting within character count."""
        lines = []
        for paragraph in text.split("\n"):
            if not paragraph:
                lines.append("")
                continue
            words = paragraph.split(" ")
            current_line = []
            current_len = 0
            for word in words:
                if current_len + len(word) + 1 <= max_chars_per_line:
                    current_line.append(word)
                    current_len += len(word) + 1
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                    # Handle single words longer than max_chars
                    while len(word) > max_chars_per_line:
                        lines.append(word[:max_chars_per_line])
                        word = word[max_chars_per_line:]
                    current_line = [word]
                    current_len = len(word)
            if current_line:
                lines.append(" ".join(current_line))
        return lines

    def build_pdf_bytes(self) -> bytes:
        """Compile the document and return raw PDF 1.4 bytes."""
        total_pages = len(self.pages)

        # Add running headers and footers to all pages
        for p_idx, page_cmds in enumerate(self.pages, 1):
            # Running header (pages 2+)
            if p_idx > 1:
                header_y = self.height - 35.0
                page_cmds.insert(0, (
                    f"BT /F2 8 Tf 0.5 0.5 0.5 rg {self.margin_left:.2f} {header_y:.2f} Td (JUGNU Conversation Export) Tj ET"
                ))
                page_cmds.insert(1, (
                    f"0.85 0.85 0.85 RG 0.5 w {self.margin_left:.2f} {header_y - 6:.2f} m {self.width - self.margin_right:.2f} {header_y - 6:.2f} l S"
                ))

            # Running footer
            footer_y = 30.0
            page_str = f"Page {p_idx} of {total_pages}"
            page_cmds.append(
                f"BT /F1 8 Tf 0.5 0.5 0.5 rg {self.width - self.margin_right - 60:.2f} {footer_y:.2f} Td ({page_str}) Tj ET"
            )
            page_cmds.append(
                f"BT /F1 8 Tf 0.5 0.5 0.5 rg {self.margin_left:.2f} {footer_y:.2f} Td (Generated by JUGNU - 100% Local & Offline) Tj ET"
            )

        objects: List[bytes] = []

        def add_obj(data: Union[str, bytes]) -> int:
            b = data.encode("latin-1") if isinstance(data, str) else data
            objects.append(b)
            return len(objects)

        # 1: Catalog
        catalog_id = add_obj("<< /Type /Catalog /Pages 2 0 R >>")

        # Fonts: F1 (Helvetica), F2 (Helvetica-Bold), F3 (Courier), F4 (Courier-Bold)
        f1_id = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        f2_id = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        f3_id = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
        f4_id = add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")

        # Reserve page object IDs
        page_ids = []
        content_ids = []
        base_id = len(objects) + 1  # Next available ID after Pages dict (which will be #2)
        # We need 2 0 obj for Pages dict, then page objs and content stream objs
        # Let's map out IDs cleanly:
        # 1: Catalog
        # 2: Pages dict
        # 3: F1, 4: F2, 5: F3, 6: F4
        # Then page_ids and content_ids
        pass

        # We can reconstruct cleanly:
        objects.clear()

        # 1: Catalog
        add_obj("<< /Type /Catalog /Pages 2 0 R >>")
        # 2: Pages (placeholder, updated below)
        add_obj("PAGES_PLACEHOLDER")
        # 3: F1, 4: F2, 5: F3, 6: F4
        add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
        add_obj("<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold >>")

        font_res = "<< /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R /F4 6 0 R >> >>"

        # Content streams and Pages
        page_ids = []
        next_id = 7
        for _ in range(total_pages):
            page_id = next_id
            content_id = next_id + 1
            next_id += 2
            page_ids.append(page_id)

        # Update Pages dict at index 1 (2 0 obj)
        kids_str = " ".join(f"{pid} 0 R" for pid in page_ids)
        objects[1] = f"<< /Type /Pages /Kids [{kids_str}] /Count {total_pages} >>".encode("latin-1")

        for p_idx, page_cmds in enumerate(self.pages):
            content_id = page_ids[p_idx] + 1
            # Add Page object
            page_body = (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {self.width:.2f} {self.height:.2f}] "
                f"/Resources {font_res} "
                f"/Contents {content_id} 0 R >>"
            )
            add_obj(page_body)

            # Add Content Stream
            stream_body = "\n".join(page_cmds).encode("latin-1")
            stream_obj = (
                f"<< /Length {len(stream_body)} >>\n"
                f"stream\n"
            ).encode("latin-1") + stream_body + b"\nendstream"
            add_obj(stream_obj)

        # Assemble PDF file
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for i, body in enumerate(objects, 1):
            offsets.append(len(out))
            out.extend(f"{i} 0 obj\n".encode("latin-1"))
            out.extend(body)
            out.extend(b"\nendobj\n")

        xref_offset = len(out)
        out.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
        for off in offsets:
            out.extend(f"{off:010d} 00000 n \n".encode("latin-1"))
        out.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n".encode("latin-1")
        )
        return bytes(out)


def export_pdf(chat: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> bytes:
    """Export conversation to a clean, styled PDF document (100% pure Python)."""
    opts = options or {}
    include_metadata = opts.get("include_metadata", True)
    include_timestamps = opts.get("include_timestamps", True)

    meta = extract_chat_metadata(chat)
    messages = chat.get("messages", []) if isinstance(chat, dict) else []

    pdf = PurePdfWriter()

    # 1. Title Banner
    pdf.add_text_line(pdf.margin_left, pdf.current_y, meta["title"][:50], font="F2", size=18, rgb=(0.15, 0.1, 0.35))
    pdf.current_y -= 22

    # App Tagline
    pdf.add_text_line(pdf.margin_left, pdf.current_y, "JUGNU Personal AI Assistant", font="F1", size=10, rgb=(0.55, 0.35, 0.85))
    pdf.current_y -= 18

    # 2. Metadata Box
    if include_metadata:
        box_h = 44.0
        pdf.add_rect(pdf.margin_left, pdf.current_y - box_h, pdf.content_width, box_h,
                     fill_rgb=(0.95, 0.94, 0.98), stroke_rgb=(0.85, 0.8, 0.95), stroke_width=1)

        row1 = f"Model: {meta['model']}   |   Exported: {meta['exported_at']}"
        row2 = f"Messages: {meta['total_messages']}   |   Words: {meta['total_words']}   |   Tokens: ~{meta['tokens_approx']}"

        pdf.add_text_line(pdf.margin_left + 12, pdf.current_y - 16, row1, font="F2", size=8.5, rgb=(0.25, 0.2, 0.4))
        pdf.add_text_line(pdf.margin_left + 12, pdf.current_y - 32, row2, font="F1", size=8.5, rgb=(0.4, 0.35, 0.55))
        pdf.current_y -= (box_h + 18)

    if not messages:
        pdf.add_text_line(pdf.margin_left, pdf.current_y - 20, "(No messages in this conversation)", font="F1", size=10, rgb=(0.5, 0.5, 0.5))
        return pdf.build_pdf_bytes()

    # 3. Messages List
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip()
        time_str = msg.get("time", "")

        is_user = (role == "user")
        role_label = "User" if is_user else "JUGNU"
        role_rgb = (0.85, 0.25, 0.65) if is_user else (0.45, 0.3, 0.85)

        # Message Header
        pdf.check_space(35)
        pdf.add_text_line(pdf.margin_left, pdf.current_y, role_label, font="F2", size=11, rgb=role_rgb)
        if include_timestamps and time_str:
            pdf.add_text_line(pdf.margin_left + 65, pdf.current_y, time_str, font="F1", size=8.5, rgb=(0.6, 0.6, 0.6))
        pdf.current_y -= 14

        # Render message content (split code blocks and text)
        segments = re.split(r"(```[a-zA-Z0-9_\-+]*\n?.*?```)", content, flags=re.DOTALL)
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue

            if seg.startswith("```") and seg.endswith("```"):
                # Code Block
                code_lines = seg.strip("`").split("\n")
                # Drop optional language tag line
                if code_lines and re.match(r"^[a-zA-Z0-9_\-+]+$", code_lines[0].strip()):
                    code_lines = code_lines[1:]

                code_text_lines = []
                for cl in code_lines:
                    code_text_lines.extend(pdf.wrap_words(cl, max_chars_per_line=72))

                line_h = 11.0
                pad = 8.0
                block_h = len(code_text_lines) * line_h + pad * 2
                pdf.check_space(min(block_h, 120))

                pdf.add_rect(pdf.margin_left, pdf.current_y - block_h, pdf.content_width, block_h,
                             fill_rgb=(0.94, 0.94, 0.96), stroke_rgb=(0.85, 0.85, 0.88), stroke_width=0.8)

                cy = pdf.current_y - pad - 8.0
                for c_line in code_text_lines:
                    pdf.add_text_line(pdf.margin_left + pad, cy, c_line, font="F3", size=8.5, rgb=(0.2, 0.2, 0.2))
                    cy -= line_h

                pdf.current_y -= (block_h + 10)
            else:
                # Regular text
                wrapped = pdf.wrap_words(seg, max_chars_per_line=82)
                for w_line in wrapped:
                    pdf.check_space(14)
                    if not w_line:
                        pdf.current_y -= 6
                        continue
                    pdf.add_text_line(pdf.margin_left + 4, pdf.current_y, w_line, font="F1", size=9.5, rgb=(0.15, 0.15, 0.2))
                    pdf.current_y -= 12.5

        # Horizontal separator rule between messages
        pdf.check_space(15)
        pdf.current_y -= 8
        pdf.add_rect(pdf.margin_left, pdf.current_y, pdf.content_width, 0.5, fill_rgb=(0.9, 0.9, 0.92))
        pdf.current_y -= 14

    return pdf.build_pdf_bytes()


# ---------------------------------------------------------------------------
# Unified ConversationExporter Class
# ---------------------------------------------------------------------------

class ConversationExporter:
    """Unified API for exporting chat conversations to MD, PDF, HTML, and JSON."""

    def __init__(self, chat: Dict[str, Any], options: Optional[Dict[str, Any]] = None):
        self.chat = chat or {}
        self.options = options or {}

    def to_markdown(self) -> str:
        return export_markdown(self.chat, self.options)

    def to_html(self, theme: str = "dark") -> str:
        return export_html(self.chat, self.options, theme=theme)

    def to_json(self, indent: int = 2) -> str:
        return export_json(self.chat, self.options, indent=indent)

    def to_pdf(self) -> bytes:
        return export_pdf(self.chat, self.options)

    def export_to_file(self, format_name: str, file_path: str) -> str:
        """Export conversation to a file based on format ('md', 'pdf', 'html', 'json')."""
        fmt = format_name.lower().strip(".").strip()
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

        if fmt in ("md", "markdown"):
            content = self.to_markdown()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        elif fmt in ("html", "htm"):
            content = self.to_html(theme=self.options.get("theme", "dark"))
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        elif fmt == "json":
            content = self.to_json()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        elif fmt == "pdf":
            pdf_bytes = self.to_pdf()
            with open(file_path, "wb") as f:
                f.write(pdf_bytes)
        else:
            raise ValueError(f"Unsupported export format: {format_name}. Choose from 'md', 'pdf', 'html', 'json'.")

        return file_path
