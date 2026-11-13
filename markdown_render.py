"""A small, dependency-free Markdown reader for JUGNU's chat bubbles.

It does not draw anything. It turns Markdown text into a flat list of `Seg`
pieces (text + style tag names) that desktop_app.py inserts into a tk.Text
widget, and render_html() turns those pieces into HTML for the Qt app (qt_app.py).
Keeping it free of any GUI code means it can be unit-tested without a window.

Supported: **bold**, *italic*, ***both***, ~~strike~~, `inline code`,
[links](url), # headings, - / * / + bullets, 1. numbered lists (nested by
indent), > quotes, --- rules and ``` fenced code blocks (the code text is kept
exactly as written). Anything else is shown as ordinary text.

render_markdown() never raises: on any problem it falls back to plain text.
"""
import re
from collections import namedtuple

# text: what to insert.  tags: style names for tk.Text.  copy: when not None, this
# piece is not text at all but a spot for a "Copy" button that copies this code.
Seg = namedtuple("Seg", ["text", "tags", "copy"])
Seg.__new__.__defaults__ = ((), None)

MAX_CHARS = 100_000   # longer messages are shown as plain text
MAX_DEPTH = 6         # how deeply bold/italic may nest
MAX_LIST_LEVEL = 4    # deepest bullet indent that gets its own indentation

_ESCAPABLE = set("\\`*_{}[]()#+-.!~|>")
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_RULE_RE = re.compile(r"^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+(.*)$")
_NUMBER_RE = re.compile(r"^([ \t]*)(\d{1,9})([.)])[ \t]+(.*)$")
_QUOTE_RE = re.compile(r"^ {0,3}>[ \t]?(.*)$")
_LINK_RE = re.compile(r"\[([^\[\]\n]+)\]\(([^()\s]+)\)")


def _add_tag(tags, name):
    """Add a style name. Bold + italic become one 'bolditalic' tag (Tk cannot merge two fonts)."""
    names = set(tags)
    names.add(name)
    if "bold" in names and "italic" in names:
        names -= {"bold", "italic"}
        names.add("bolditalic")
    if "bolditalic" in names:
        names -= {"bold", "italic"}
    return tuple(sorted(names))


def _find_code_close(text, start, run):
    """Index of the next backtick run that is exactly `run` long, or -1."""
    k, n = start, len(text)
    while k < n:
        if text[k] == "`":
            end = k
            while end < n and text[end] == "`":
                end += 1
            if end - k == run:
                return k
            k = end
        else:
            k += 1
    return -1


def _try_emphasis(text, i, tags, depth, dead):
    """Try to read **bold**, *italic*, ***both***, __x__, _x_ or ~~strike~~ at text[i].

    Returns (segments, next_index) or None when the marker is just a literal character.
    `dead` remembers markers that already failed to find any closing partner: a later
    marker of the same kind cannot find one either, so the search is not repeated
    (this keeps strange input such as thousands of lone stars fast).
    """
    ch, n = text[i], len(text)
    if text.startswith("~~", i):
        marker, name = "~~", "strike"
    elif ch in "*_" and text.startswith(ch * 3, i):
        marker, name = ch * 3, "bolditalic"
    elif ch in "*_" and text.startswith(ch * 2, i):
        marker, name = ch * 2, "bold"
    elif ch in "*_":
        marker, name = ch, "italic"
    else:
        return None
    size = len(marker)
    before = text[i - 1] if i else " "
    after = text[i + size] if i + size < n else " "
    # Not emphasis: "2*3*4", "snake_case_name", "x**2 + y**2", "5 * 3", or an empty "** **".
    if ch in "*_" and before.isalnum():
        return None
    if after.isspace():
        return None
    if i >= dead.get(marker, len(text) + 1):
        return None
    j = i + size
    while True:
        j = text.find(marker, j)
        if j == -1:
            dead[marker] = min(i, dead.get(marker, i))
            return None
        prev = text[j - 1]
        following = text[j + size] if j + size < n else " "
        good = j > i + size and not prev.isspace() and prev != "\\"
        if good and ch in "*_":
            good = not following.isalnum()
            if size == 1 and (prev == ch or following == ch):
                good = False  # part of a longer ** run, so not the closing marker
        if good:
            break
        j += 1
    inner = parse_inline(text[i + size:j], _add_tag(tags, name), depth + 1)
    return inner, j + size


def parse_inline(text, tags=(), depth=0):
    """Turn one line of Markdown into Segs. `tags` are style names applied to everything."""
    segs, buf, i, n = [], [], 0, len(text)
    dead = {}  # markers and backtick runs that have no closing partner in this text

    def flush():
        if buf:
            segs.append(Seg("".join(buf), tags))
            buf.clear()

    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n and text[i + 1] in _ESCAPABLE:
            buf.append(text[i + 1])  # "\*" shows a plain star
            i += 2
        elif ch == "`":
            end = i
            while end < n and text[end] == "`":
                end += 1
            run = end - i
            close = -1 if ("`", run) in dead and i >= dead[("`", run)] else _find_code_close(text, end, run)
            if close == -1:
                dead[("`", run)] = min(i, dead.get(("`", run), i))
                buf.append(text[i:end])  # no closing backticks: show them as they are
                i = end
            else:
                flush()
                code = text[end:close]
                if len(code) > 1 and code[0] == " " and code[-1] == " " and code.strip():
                    code = code[1:-1]
                segs.append(Seg(code, _add_tag(tags, "icode")))
                i = close + run
        elif ch == "[" and (match := _LINK_RE.match(text, i)) and depth < MAX_DEPTH:
            flush()
            label, url = match.group(1), match.group(2)
            segs.extend(parse_inline(label, _add_tag(tags, "link"), depth + 1))
            if label != url:
                segs.append(Seg(f" ({url})", _add_tag(tags, "linkurl")))
            i = match.end()
        elif ch in "*_~" and depth < MAX_DEPTH:
            found = _try_emphasis(text, i, tags, depth, dead)
            if found:
                flush()
                segs.extend(found[0])
                i = found[1]
            else:
                buf.append(ch)
                i += 1
        else:
            buf.append(ch)
            i += 1
    flush()
    return segs


def _merge(segs):
    """Join neighbouring pieces that have the same style, so fewer inserts are needed."""
    merged = []
    for seg in segs:
        if (merged and seg.copy is None and merged[-1].copy is None
                and merged[-1].tags == seg.tags):
            merged[-1] = Seg(merged[-1].text + seg.text, seg.tags)
        else:
            merged.append(seg)
    return merged


def _blocks_to_rows(text):
    """Read Markdown line by line. Returns rows of (segments, tags for the line break)."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    rows = []

    def blank():
        return ([], ())

    def add_blank():
        if rows and rows[-1] != blank():
            rows.append(blank())

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1

        fence = _FENCE_RE.match(line)
        if fence and not (fence.group(1)[0] == "`" and "`" in fence.group(2)):
            mark, info = fence.group(1), fence.group(2).strip()
            language = info.split()[0] if info else ""
            closer = re.compile(r"^ {0,3}" + re.escape(mark[0]) + "{%d,}[ \t]*$" % len(mark))
            code_lines = []
            while i < len(lines) and not closer.match(lines[i]):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip the closing fence (a missing one just ends the block at the end)
            add_blank()
            rows.append(([Seg(" " + (language or "code") + " ", ("codehead",)),
                          Seg("", ("codehead",), "\n".join(code_lines))], ("codehead",)))
            for code_line in code_lines:
                rows.append(([Seg(code_line, ("code",))] if code_line else [], ("code",)))
            rows.append(blank())
            continue

        if not line.strip():
            if rows:
                add_blank()
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            level = min(len(heading.group(1)), 3)
            rows.append((parse_inline(heading.group(2), ("h%d" % level,)), ()))
            continue

        if _RULE_RE.match(line):
            rows.append(([Seg("─" * 28, ("rule",))], ()))
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            rows.append(([Seg("│ ", ("quote",))] + parse_inline(quote.group(1), ("quote",)), ()))
            continue

        bullet = _BULLET_RE.match(line)
        number = None if bullet else _NUMBER_RE.match(line)
        if bullet or number:
            indent = (bullet or number).group(1).expandtabs(4)
            level = min(len(indent) // 2, MAX_LIST_LEVEL)
            if bullet:
                marker, body = ("•" if level % 2 == 0 else "◦"), bullet.group(2)
            else:
                marker, body = number.group(2) + number.group(3), number.group(4)
            rows.append(([Seg(marker + " ", ("li%d" % level,))]
                         + parse_inline(body, ("li%d" % level,)), ()))
            continue

        rows.append((parse_inline(line), ()))

    while rows and rows[-1] == blank():
        rows.pop()
    return rows


def render_markdown(text):
    """Markdown text -> list of Seg. Never raises; falls back to one plain Seg."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    if len(text) > MAX_CHARS:
        return [Seg(text)]
    try:
        segs = []
        rows = _blocks_to_rows(text)
        for number, (row, newline_tags) in enumerate(rows):
            segs.extend(row)
            if number < len(rows) - 1:
                segs.append(Seg("\n", newline_tags))
        return _merge(segs) or [Seg(text)]
    except Exception:  # a parser bug must never break the chat
        return [Seg(text)]


def plain_text(text):
    """What the message reads like without Markdown symbols (used for read-aloud)."""
    try:
        return "".join(seg.text for seg in render_markdown(text) if seg.copy is None)
    except Exception:
        return text if isinstance(text, str) else ""


# ---------- HTML for Qt rich text ----------
_INLINE_CSS = {
    "bold": "font-weight:600;",
    "italic": "font-style:italic;",
    "bolditalic": "font-weight:600; font-style:italic;",
    "strike": "text-decoration:line-through;",
    "link": "color:{accent}; text-decoration:underline;",
    "linkurl": "color:{muted};",
    "icode": "font-family:'{mono}'; background-color:{inline_code};",
    "quote": "color:{muted};",
    "rule": "color:{border};",
}
_HEADING_SCALE = {"h1": 1.4, "h2": 1.2, "h3": 1.1}


def _line_kind(tags):
    """Which kind of block a line is, from the style names used on it."""
    for kind in ("codehead", "code", "h1", "h2", "h3", "quote"):
        if kind in tags:
            return kind
    return next((name for name in sorted(tags) if name.startswith("li")), "text")


def _split_lines(segs):
    """Seg list -> lines of [segments, set of tags, code to copy or None]."""
    lines = [[[], set(), None]]
    for seg in segs:
        if seg.copy is not None:
            lines[-1][2] = seg.copy
            continue
        parts = seg.text.split("\n")
        for number, part in enumerate(parts):
            if number:
                lines[-1][1].update(seg.tags)  # the line break carries the style of the line it ends
                lines.append([[], set(), None])
            if part:
                lines[-1][0].append(Seg(part, seg.tags))
                lines[-1][1].update(seg.tags)
    return lines


def render_html(text, colors, mono="monospace", base_pt=10, copy_label="Copy"):
    """Markdown text -> (html, codes) for a Qt rich-text widget. Never raises.

    `colors` is a theme palette (LIGHT / DARK). Each code block gets a link "copy:N";
    codes[N] is the exact code it copies.
    """
    import html as _html

    def esc(value):
        return _html.escape(value, quote=False)

    try:
        css = {name: rule.format(mono=mono, **colors) for name, rule in _INLINE_CSS.items()}
        out, codes, code_lines = [], [], None

        def inline(segments):
            parts = []
            for seg in segments:
                text_html = esc(seg.text)
                if "icode" in seg.tags:
                    text_html = text_html.replace(" ", "&nbsp;")
                style = "".join(css[tag] for tag in seg.tags if tag in css)
                parts.append(f'<span style="{style}">{text_html}</span>' if style else text_html)
            return "".join(parts)

        def close_code():
            if code_lines is not None:
                out.append(f'<pre style="font-family:\'{mono}\'; color:{colors["text"]}; margin:0;">'
                           + "\n".join(code_lines) + "</pre></td></tr></table>")

        for segments, tags, copy in _split_lines(render_markdown(text)):
            kind = _line_kind(tags)
            if kind == "code" and code_lines is not None:
                code_lines.append(esc("".join(seg.text for seg in segments)))
                continue
            close_code()
            code_lines = None
            if kind == "codehead":
                label = esc("".join(seg.text for seg in segments).strip())
                link = ""
                if copy is not None:
                    link = (f' &nbsp; <a href="copy:{len(codes)}" style="color:{colors["accent"]};'
                            f' text-decoration:none;">{esc(copy_label)}</a>')
                    codes.append(copy)
                out.append(f'<table width="100%" cellspacing="0" cellpadding="8" bgcolor="{colors["code"]}"'
                           f' style="margin-top:4px; margin-bottom:4px;"><tr><td>'
                           f'<p style="margin:0 0 4px 0; color:{colors["muted"]};'
                           f' font-size:{base_pt - 1}pt; font-weight:600;">{label}{link}</p>')
                code_lines = []
            elif kind == "code":  # a code line without its header (should not happen); show it plainly
                out.append(f'<p style="margin:0; font-family:\'{mono}\';">{inline(segments)}</p>')
            elif kind in _HEADING_SCALE:
                size = round(base_pt * _HEADING_SCALE[kind], 1)
                out.append(f'<p style="margin:4px 0 2px 0; font-size:{size}pt; font-weight:600;'
                           f' color:{colors["accent"]};">{inline(segments)}</p>')
            elif kind.startswith("li"):
                indent = 4 + int(kind[2:]) * 18
                out.append(f'<p style="margin:0 0 0 {indent}px;">{inline(segments)}</p>')
            elif segments:
                out.append(f'<p style="margin:0;">{inline(segments)}</p>')
            else:
                out.append('<p style="margin:0;">&nbsp;</p>')
        close_code()
        return "".join(out), codes
    except Exception:  # a renderer bug must never break the chat
        return "<p>" + esc(text if isinstance(text, str) else "") + "</p>", []
