"""Full-text conversation history search engine for JUGNU.

Provides an in-memory inverted search index, phrase matching, role filtering,
relevance ranking, and snippet extraction with zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import re
from typing import Any, Sequence


_WORD_REGEX = re.compile(r"\b\w+\b", re.UNICODE)
_PHRASE_REGEX = re.compile(r'"([^"]+)"')
_ROLE_REGEX = re.compile(r"\brole:(user|assistant)\b", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric terms."""
    if not text:
        return []
    return _WORD_REGEX.findall(text.lower())


def find_term_spans(text: str, query_terms: Sequence[str]) -> list[tuple[int, int]]:
    """Return character start/end spans of all query terms in text (case-insensitive)."""
    if not text or not query_terms:
        return []
    spans: list[tuple[int, int]] = []
    for term in query_terms:
        if not term.strip():
            continue
        pattern = re.compile(re.escape(term.strip()), re.IGNORECASE)
        for match in pattern.finditer(text):
            spans.append(match.span())
    # Sort and merge overlapping spans
    if not spans:
        return []
    spans.sort(key=lambda s: s[0])
    merged: list[tuple[int, int]] = [spans[0]]
    for current in spans[1:]:
        prev_start, prev_end = merged[-1]
        if current[0] <= prev_end:
            merged[-1] = (prev_start, max(prev_end, current[1]))
        else:
            merged.append(current)
    return merged


def extract_snippet(text: str, query_terms: Sequence[str], max_len: int = 120) -> str:
    """Extract a contextual snippet around the first matching term."""
    if not text:
        return ""
    spans = find_term_spans(text, query_terms)
    if not spans:
        cleaned = " ".join(text.split())
        return cleaned[:max_len] + ("…" if len(cleaned) > max_len else "")

    first_start, first_end = spans[0]
    half_window = (max_len - (first_end - first_start)) // 2
    start = max(0, first_start - max(30, half_window))
    end = min(len(text), first_end + max(30, half_window))

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    snippet = text[start:end].strip()
    return f"{prefix}{snippet}{suffix}"


@dataclass
class ParsedQuery:
    raw: str
    phrases: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    role_filter: str | None = None

    @classmethod
    def parse(cls, query_str: str) -> ParsedQuery:
        raw = query_str.strip()
        if not raw:
            return cls(raw="")

        # Extract role filter e.g. role:user or role:assistant
        role_filter = None
        role_match = _ROLE_REGEX.search(raw)
        working_str = raw
        if role_match:
            role_filter = role_match.group(1).lower()
            working_str = _ROLE_REGEX.sub("", working_str)

        # Extract quoted phrases e.g. "binary search"
        phrases = _PHRASE_REGEX.findall(working_str)
        without_phrases = _PHRASE_REGEX.sub(" ", working_str)

        # Extract remaining terms
        terms = tokenize(without_phrases)

        # Remove duplicate terms/phrases
        phrases = [p.strip().lower() for p in phrases if p.strip()]
        terms = list(dict.fromkeys(terms))

        return cls(
            raw=raw,
            phrases=phrases,
            terms=terms,
            role_filter=role_filter,
        )

    @property
    def role(self) -> str | None:
        return self.role_filter


@dataclass
class SearchResult:
    chat_id: str
    chat_title: str
    message_index: int
    role: str
    content: str
    timestamp: str = ""
    matched_terms: list[str] = field(default_factory=list)
    snippet: str = ""
    score: float = 0.0

    @property
    def display_preview(self) -> str:
        tag = "👤" if self.role == "user" else "🤖"
        time_text = f" ({self.timestamp})" if self.timestamp else ""
        return f"{tag} {self.chat_title}{time_text}: {self.snippet}"


class SearchEngine:
    """Fast, zero-dependency inverted index search engine for conversation history."""

    def __init__(self, chats: list[dict[str, Any]] | None = None):
        # term -> dict of (chat_id, msg_idx) -> list of token occurrences
        self._index: dict[str, dict[tuple[str, int], int]] = {}
        # (chat_id, msg_idx) -> {chat_title, role, content, timestamp}
        self._corpus: dict[tuple[str, int], dict[str, Any]] = {}
        # chat_id -> order rank (for recency score)
        self._chat_order: dict[str, int] = {}

        if chats:
            self.index_all(chats)

    def clear(self) -> None:
        self._index.clear( )
        self._corpus.clear()
        self._chat_order.clear()

    def index_all(self, chats: list[dict[str, Any]]) -> None:
        """Index an entire conversation history list."""
        self.clear()
        for chat_idx, chat in enumerate(chats):
            chat_id = chat.get("id")
            if not chat_id:
                continue
            self._chat_order[chat_id] = chat_idx
            chat_title = chat.get("title", "New Chat")
            messages = chat.get("messages", [])
            title_tokens = tokenize(chat_title)
            if not messages:
                key = (chat_id, -1)
                self._corpus[key] = {
                    "chat_id": chat_id,
                    "chat_title": chat_title,
                    "msg_idx": -1,
                    "role": "chat",
                    "content": chat_title,
                    "timestamp": "",
                }
                for t in title_tokens:
                    if t not in self._index:
                        self._index[t] = {}
                    self._index[t][key] = self._index[t].get(key, 0) + 5
            else:
                for msg_idx, msg in enumerate(messages):
                    self._index_message(chat_id, chat_title, msg_idx, msg)
                    for t in title_tokens:
                        if t not in self._index:
                            self._index[t] = {}
                        self._index[t][(chat_id, msg_idx)] = (
                            self._index[t].get((chat_id, msg_idx), 0) + 3
                        )

    def index_chat(self, chat: dict[str, Any]) -> None:
        """Dynamically add or re-index a single chat."""
        chat_id = chat.get("id")
        if not chat_id:
            return
        self.remove_chat(chat_id)
        self._chat_order[chat_id] = len(self._chat_order)
        chat_title = chat.get("title", "New Chat")
        messages = chat.get("messages", [])
        title_tokens = tokenize(chat_title)
        if not messages:
            key = (chat_id, -1)
            self._corpus[key] = {
                "chat_id": chat_id,
                "chat_title": chat_title,
                "msg_idx": -1,
                "role": "chat",
                "content": chat_title,
                "timestamp": "",
            }
            for t in title_tokens:
                if t not in self._index:
                    self._index[t] = {}
                self._index[t][key] = self._index[t].get(key, 0) + 5
        else:
            for msg_idx, msg in enumerate(messages):
                self._index_message(chat_id, chat_title, msg_idx, msg)
                for t in title_tokens:
                    if t not in self._index:
                        self._index[t] = {}
                    self._index[t][(chat_id, msg_idx)] = (
                        self._index[t].get((chat_id, msg_idx), 0) + 3
                    )

    def remove_chat(self, chat_id: str) -> None:
        """Remove all indexed entries for a chat ID."""
        self._chat_order.pop(chat_id, None)
        keys_to_remove = [k for k in self._corpus if k[0] == chat_id]
        for k in keys_to_remove:
            self._corpus.pop(k, None)
        for term, postings in list(self._index.items()):
            for k in keys_to_remove:
                postings.pop(k, None)
            if not postings:
                del self._index[term]

    def _index_message(
        self, chat_id: str, chat_title: str, msg_idx: int, message: dict[str, Any]
    ) -> None:
        role = message.get("role", "")
        content = message.get("content", "")
        if not content:
            return
        key = (chat_id, msg_idx)
        self._corpus[key] = {
            "chat_id": chat_id,
            "chat_title": chat_title,
            "msg_idx": msg_idx,
            "role": role,
            "content": content,
            "timestamp": message.get("time", ""),
        }
        tokens = tokenize(content)
        for token in tokens:
            if token not in self._index:
                self._index[token] = {}
            self._index[token][key] = self._index[token].get(key, 0) + 1

    def search(self, query_str: str, limit: int = 50) -> list[SearchResult]:
        """Search indexed conversations for the query string."""
        parsed = ParsedQuery.parse(query_str)
        all_query_items = parsed.phrases + parsed.terms
        if not all_query_items and not parsed.role_filter:
            return []

        # Find candidate messages
        candidate_keys: set[tuple[str, int]] | None = None

        if parsed.terms:
            for term in parsed.terms:
                postings = set(self._index.get(term, {}).keys())
                if candidate_keys is None:
                    candidate_keys = postings
                else:
                    candidate_keys = candidate_keys & postings

        if candidate_keys is None:
            candidate_keys = set(self._corpus.keys())
        elif not candidate_keys and parsed.terms:
            # Fallback to OR search if strict AND produced zero results
            candidate_keys = set()
            for term in parsed.terms:
                candidate_keys.update(self._index.get(term, {}).keys())

        results: list[SearchResult] = []
        for key in candidate_keys:
            entry = self._corpus.get(key)
            if not entry:
                continue

            # Role filter check
            if parsed.role_filter and entry["role"].lower() != parsed.role_filter:
                continue

            content = entry["content"]
            searchable_text = f"{entry['chat_title']} {content}".lower()

            # Exact phrase check
            if parsed.phrases:
                phrase_match = all(p in searchable_text for p in parsed.phrases)
                if not phrase_match:
                    continue

            # Term presence verification
            matched = [item for item in all_query_items if item in searchable_text]
            if not matched and all_query_items:
                continue

            # Compute relevance score
            match_count = sum(searchable_text.count(item) for item in all_query_items)
            recency = self._chat_order.get(entry["chat_id"], 0) * 0.05
            score = match_count * 1.0 + recency

            snippet = extract_snippet(content, all_query_items)
            if not snippet or snippet == "…":
                snippet = extract_snippet(entry["chat_title"], all_query_items)

            results.append(
                SearchResult(
                    chat_id=entry["chat_id"],
                    chat_title=entry["chat_title"],
                    message_index=entry["msg_idx"],
                    role=entry["role"],
                    content=content,
                    timestamp=entry["timestamp"],
                    matched_terms=matched,
                    snippet=snippet,
                    score=score,
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def matching_chat_ids(self, query_str: str) -> set[str]:
        """Return the set of unique chat IDs containing matches for query_str."""
        results = self.search(query_str, limit=500)
        return {r.chat_id for r in results}
