"""Renaming and deleting individual chats (right-click menu on the history list)."""
import json

import pytest

import jugnu_core
from conftest import saved_history

pytest.importorskip("PySide6")


def test_rename_changes_only_that_title_and_saves(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: "  My   new   name ")
    app.rename_chat("a")
    assert [c["title"] for c in app.chats] == ["My new name", "Beta", "Gamma"]
    assert [c["title"] for c in saved_history(app)] == ["My new name", "Beta", "Gamma"]
    assert len(app.find_chat("a")["messages"]) == 2


def test_rename_does_not_open_the_chat(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: "Renamed")
    app.rename_chat("a")
    assert app.current_id == "c"


def test_rename_dialog_starts_with_the_current_title(with_chats, monkeypatch):
    app = with_chats
    asked = []
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: asked.append(initial))
    app.rename_chat("b")
    assert asked == ["Beta"]


@pytest.mark.parametrize("answer", [None, "", "     ", "Alpha"])
def test_rename_ignores_cancel_empty_and_unchanged(with_chats, monkeypatch, answer):
    app = with_chats
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: answer)
    app.rename_chat("a")
    assert app.find_chat("a")["title"] == "Alpha"


def test_rename_caps_very_long_titles(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: "x" * 200)
    app.rename_chat("a")
    assert len(app.find_chat("a")["title"]) == jugnu_core.MAX_TITLE_LENGTH


def test_long_titles_are_shortened_in_the_list(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: "y" * 50)
    app.rename_chat("a")
    row = app.history_list.item(2).text()  # the list shows the oldest chat last
    assert row.endswith("…") and len(row) == jugnu_core.MAX_LIST_TITLE


def test_delete_another_chat_keeps_everything_else(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "confirm", lambda title, message: True)
    before = {c["id"]: json.dumps(c) for c in app.chats}
    app.delete_chat("b")
    assert [c["id"] for c in app.chats] == ["a", "c"]
    assert all(json.dumps(c) == before[c["id"]] for c in app.chats)
    assert app.current_id == "c"
    assert [c["id"] for c in saved_history(app)] == ["a", "c"]


def test_delete_open_chat_shows_a_fresh_empty_chat(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "confirm", lambda title, message: True)
    app.delete_chat("c")
    assert app.find_chat("c") is None
    assert app.current_id != "c"
    assert app.current_chat()["messages"] == []
    assert [c["id"] for c in saved_history(app)] == ["a", "b"]
    assert [c["id"] for c in app.chats] == ["a", "b"]  # the empty draft is not saved as a chat


def test_delete_declined_changes_nothing(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "confirm", lambda title, message: False)
    app.delete_chat("a")
    assert [c["id"] for c in app.chats] == ["a", "b", "c"]
    assert len(saved_history(app)) == 3


def test_delete_asks_with_the_chat_title(with_chats, monkeypatch):
    app = with_chats
    asked = []
    monkeypatch.setattr(app, "confirm", lambda title, message: asked.append(message) or False)
    app.delete_chat("b")
    assert "Beta" in asked[0]


def test_delete_last_chat_leaves_empty_history(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "confirm", lambda title, message: True)
    for chat_id in ("a", "b", "c"):
        app.delete_chat(chat_id)
    assert app.chats == [] and saved_history(app) == []
    assert app.current_chat()["messages"] == []


def test_actions_on_a_missing_chat_do_nothing(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "confirm", lambda title, message: True)
    monkeypatch.setattr(app, "ask_chat_title", lambda initial: "x")
    app.rename_chat("nope")
    app.delete_chat("nope")
    assert [c["id"] for c in app.chats] == ["a", "b", "c"]


def test_renamed_title_survives_a_restart(with_chats, make_window, monkeypatch):
    monkeypatch.setattr(with_chats, "ask_chat_title", lambda initial: "Kept after restart")
    with_chats.rename_chat("b")
    restarted = make_window()
    assert [c["title"] for c in restarted.chats] == ["Alpha", "Kept after restart", "Gamma"]


def test_clear_chat_removes_only_the_open_chat(with_chats, monkeypatch):
    app = with_chats
    monkeypatch.setattr(app, "confirm", lambda title, message: True)
    app.clear_chat()
    assert [c["id"] for c in saved_history(app)] == ["a", "b"]
    assert app.current_chat()["messages"] == []


def test_history_list_is_newest_first_and_selects_a_chat(with_chats):
    app = with_chats
    titles = [app.history_list.item(i).text() for i in range(app.history_list.count())]
    assert titles == ["Gamma", "Beta", "Alpha"]
    app.select_chat(app.history_list.item(2))
    assert app.current_id == "a"
    assert app.bubbles[0].text == "question for Alpha"


def test_right_click_menu_acts_on_the_clicked_chat(with_chats, monkeypatch):
    app = with_chats
    renamed = []
    monkeypatch.setattr(app, "rename_chat", renamed.append)
    row = app.history_list.visualItemRect(app.history_list.item(1)).center()  # "Beta"
    menu = app.show_chat_menu(row)
    actions = [a for a in menu.actions() if not a.isSeparator()]
    export, rename, delete = actions
    assert (export.text(), rename.text(), delete.text()) == (
        app.t("chat_menu_export"),
        app.t("chat_menu_rename"),
        app.t("chat_menu_delete"),
    )
    rename.trigger()
    assert renamed == ["b"]
    menu.close()
    assert app.show_chat_menu(app.history_list.viewport().rect().bottomLeft()) is None  # empty space
