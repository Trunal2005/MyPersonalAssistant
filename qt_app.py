"""JUGNU's desktop window, built with PySide6 and themed with Qt Style Sheets (jugnu.qss).

All the logic (history, settings, local answers, the Ollama client) lives in jugnu_core.py;
this file only draws it. Run it with:  python qt_app.py
"""
import math
import os
import sys
import threading
from string import Template

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFontDatabase, QKeySequence, QPixmap, QShortcut, QTextOption
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QTextBrowser, QVBoxLayout, QWidget)

import jugnu_core as core
from history_lock import HistoryInUseError, HistoryLock
from markdown_render import plain_text, render_html
from strings import get_string, next_language
from tts import RATE_MAX, RATE_MIN, TTSManager

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE_FILE = os.path.join(HERE, "jugnu.qss")
BUBBLE_PT = 10        # chat text size, in points
COPY_TEXT = "⧉ Copy"
COPIED_TEXT = "✓ Copied!"


def build_stylesheet(colors):
    """jugnu.qss with every $name replaced by that colour from the palette."""
    with open(STYLE_FILE, encoding="utf-8") as f:
        return Template(f.read()).safe_substitute(colors)


def max_bubble_width(viewport_width):
    """Widest a bubble may be, keeping it inside the chat area with room to show who sent it."""
    return max(40, min(720, viewport_width - 100, int(viewport_width * 0.72)))


def repolish(widget):
    """Re-apply the style sheet after a property used by a selector (variant, state) changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Bridge(QObject):
    """Brings results from background threads back to the GUI thread.

    A signal emitted on another thread is queued and its slot runs on the GUI thread,
    so the worker never touches a widget.
    """
    answered = Signal(str, object, bool)  # chat id, answer (or None), is_error
    warmed = Signal(bool)


def run_in_background(target, *args):
    # A daemon thread, so closing the window never waits for (or crashes on) a slow request.
    threading.Thread(target=target, args=args, daemon=True).start()


class InputBox(QPlainTextEdit):
    """The message box. Enter sends; Shift+Enter starts a new line."""
    submitted = Signal()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class BubbleText(QTextBrowser):
    """A message's text: read-only, selectable, as tall as its content and never scrolling itself."""
    copy_all = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bubbleText")
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Long words and URLs wrap anywhere rather than running out of the bubble.
        self.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.document().setDocumentMargin(0)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def fit(self, max_width):
        """Size to the text: as narrow as it allows, at most `max_width`, and exactly as tall."""
        # Measure a copy: the widget lays out its own document at its current width, not ours.
        doc = self.document().clone(self)
        doc.setTextWidth(max_width)
        width = min(max_width, math.ceil(doc.idealWidth()) + 2)
        doc.setTextWidth(width)
        self.setFixedSize(width, math.ceil(doc.size().height()) + 2)
        doc.deleteLater()

    def wheelEvent(self, event):
        event.ignore()  # let the chat area scroll instead

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        menu.addAction("Copy All", self.copy_all.emit)
        menu.exec(event.globalPos())


class Bubble(QFrame):
    """One chat message: name, time, Copy (and Read aloud for replies) above the text."""

    def __init__(self, app, role, text, timestamp=None):
        super().__init__()
        self.app, self.text = app, text
        is_user = role == "user"
        self.setObjectName("bubble")
        self.setProperty("role", "user" if is_user else "assistant")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.codes = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 10)
        layout.setSpacing(4)
        header = QHBoxLayout()
        header.setSpacing(6)
        name = QLabel(app.t("you_label") if is_user else "🤖 JUGNU")
        name.setObjectName("bubbleName")
        header.addWidget(name)
        if timestamp:
            time_label = QLabel(timestamp)
            time_label.setObjectName("bubbleTime")
            header.addWidget(time_label)
        header.addStretch(1)
        self.copy_btn = self.small_button(COPY_TEXT, self.copy_message)
        header.addWidget(self.copy_btn)
        self.read_btn = None
        if not is_user:
            self.read_btn = self.small_button("🔊", lambda: app.read_aloud(text))
            self.read_btn.setEnabled(app.tts.available)
            header.addWidget(self.read_btn)
        layout.addLayout(header)

        self.body = BubbleText(self)
        self.body.setFont(app.bubble_font())
        if is_user:
            self.body.setPlainText(text)  # what you type is always shown exactly as typed
        else:
            html, self.codes = render_html(text, app.colors, mono=app.mono_family(), base_pt=BUBBLE_PT,
                                           copy_label=app.t("code_copy_btn"))
            self.body.setHtml(html)
        self.body.anchorClicked.connect(self.on_link)
        self.body.copy_all.connect(self.copy_message)
        layout.addWidget(self.body)

    def small_button(self, text, slot):
        button = QPushButton(text)
        button.setProperty("variant", "ghost")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    def fit(self, max_width):
        self.body.fit(max_width)

    def copy_message(self):
        QApplication.clipboard().setText(self.text)
        self.copy_btn.setText(COPIED_TEXT)
        self.copy_btn.setProperty("state", "copied")
        repolish(self.copy_btn)
        QTimer.singleShot(1500, self, self.reset_copy_button)

    def reset_copy_button(self):
        self.copy_btn.setText(COPY_TEXT)
        self.copy_btn.setProperty("state", "")
        repolish(self.copy_btn)

    def on_link(self, url):
        # Only the code blocks' own "Copy" links do anything; other links are just shown.
        target = url.toString()
        if target.startswith("copy:"):
            index = int(target[5:])
            if 0 <= index < len(self.codes):
                QApplication.clipboard().setText(self.codes[index])
                html, _ = render_html(self.text, self.app.colors, mono=self.app.mono_family(),
                                      base_pt=BUBBLE_PT, copy_label=self.app.t("code_copied_btn"))
                self.body.setHtml(html)
                QTimer.singleShot(1500, self, self.reset_code_links)

    def reset_code_links(self):
        html, _ = render_html(self.text, self.app.colors, mono=self.app.mono_family(),
                              base_pt=BUBBLE_PT, copy_label=self.app.t("code_copy_btn"))
        self.body.setHtml(html)


class VoiceSettingsDialog(QDialog):
    """Speed, volume and voice. Changes are heard from the next sentence and saved as you go."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setModal(False)
        self.setMinimumWidth(340)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 18)
        layout.setSpacing(6)

        self.rate_label = self.field_label()
        self.rate = QSlider(Qt.Horizontal)
        self.rate.setRange(RATE_MIN, RATE_MAX)
        self.rate.setSingleStep(5)
        self.rate.setPageStep(25)
        self.volume_label = self.field_label()
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setSingleStep(5)
        self.voice_label = self.field_label()
        self.voice = QComboBox()
        self.test_btn = QPushButton()
        self.close_btn = QPushButton()
        self.close_btn.setProperty("variant", "danger")
        for widget in (self.rate_label, self.rate, self.volume_label, self.volume,
                       self.voice_label, self.voice):
            layout.addWidget(widget)
        layout.addSpacing(12)
        layout.addWidget(self.test_btn)
        layout.addWidget(self.close_btn)

        # Set the starting positions first, then connect, so opening the window never rewrites the saved values.
        self.rate.setValue(app.voice_rate)
        self.volume.setValue(round(app.voice_volume * 100))
        self.rate.valueChanged.connect(self.on_rate)
        self.volume.valueChanged.connect(self.on_volume)
        self.rate.sliderReleased.connect(app.save_settings)
        self.volume.sliderReleased.connect(app.save_settings)
        self.voice.activated.connect(self.on_voice)
        self.test_btn.clicked.connect(app.test_voice)
        self.close_btn.clicked.connect(self.close)
        self.retranslate()

    @staticmethod
    def field_label():
        label = QLabel()
        label.setProperty("variant", "field")
        return label

    def voice_choices(self):
        """Dropdown entries: the default first, then every installed voice (names made unique)."""
        choices, seen = [(self.app.t("voice_default_name"), None)], {}
        for vid, name in self.app.tts.voices:
            seen[name] = seen.get(name, 0) + 1
            choices.append((name if seen[name] == 1 else f"{name} ({seen[name]})", vid))
        return choices

    def retranslate(self):
        app = self.app
        self.setWindowTitle(app.t("voice_settings_title"))
        self.update_value_labels()
        self.voice_label.setText(app.t("voice_choice_label"))
        self.test_btn.setText(app.t("voice_test_btn"))
        self.close_btn.setText(app.t("voice_close_btn"))
        # The default entry's name depends on the language, so rebuild the list.
        self.voice.clear()
        for label, vid in self.voice_choices():
            self.voice.addItem(label, vid)
        # A saved voice that is no longer installed shows (and plays) as the default.
        index = self.voice.findData(app.voice_id) if app.voice_id else 0
        self.voice.setCurrentIndex(max(index, 0))

    def update_value_labels(self):
        self.rate_label.setText(self.app.t("voice_rate_label", value=self.app.voice_rate))
        self.volume_label.setText(self.app.t("voice_volume_label", value=round(self.app.voice_volume * 100)))

    def on_rate(self, value):
        self.app.voice_rate = int(value)
        self.app.push_voice_settings()
        self.update_value_labels()

    def on_volume(self, value):
        self.app.voice_volume = int(value) / 100
        self.app.push_voice_settings()
        self.update_value_labels()

    def on_voice(self, index):
        self.app.voice_id = self.voice.itemData(index)
        self.app.push_voice_settings()
        self.app.save_settings()

    def closeEvent(self, event):
        self.app.save_settings()
        super().closeEvent(event)


class JugnuWindow(QMainWindow):
    def __init__(self, history_file=core.HISTORY_FILE, settings_file=core.SETTINGS_FILE):
        super().__init__()
        self.history_file, self.settings_file = history_file, settings_file
        self.setWindowTitle(core.APP_TITLE)
        self.resize(1200, 760)
        self.setMinimumSize(850, 570)

        self.chats = core.load_history(history_file)
        self.current_id = None
        self.draft_chat = None  # Unsaved empty chat; saved only after first message.
        self.busy = False
        self.dark_mode = core.load_dark_mode(settings_file)
        self.voice_enabled = core.load_voice_enabled(settings_file)
        self.language = core.load_language(settings_file)
        self.voice_rate, self.voice_volume, self.voice_id = core.load_voice_prefs(settings_file)
        self.tts = TTSManager(rate=self.voice_rate, volume=self.voice_volume,
                              voice_id=self.voice_id)  # Offline voice output; runs on its own thread.
        self.voice_dialog = None
        self._status = ("status_ready", {})  # Remembered so the status line can be re-translated.
        self._mono = None
        self.bubbles = []
        self._stick_to_bottom = False

        self.bridge = Bridge()
        self.bridge.answered.connect(self.finish_answer)
        self.bridge.warmed.connect(lambda ok: self.set_status("status_ready" if ok else "status_offline"))

        self.build_ui()
        if self.chats:
            self.current_id = self.chats[-1]["id"]  # Reopen most recent saved conversation.
        else:
            self.make_draft()
        self.apply_theme()
        self.apply_language()

        self.resize_timer = QTimer(self, singleShot=True, interval=60)
        self.resize_timer.timeout.connect(self.fit_bubbles)
        self.speech_timer = QTimer(self, interval=200)
        self.speech_timer.timeout.connect(self.poll_speech)
        self.speech_timer.start()
        QTimer.singleShot(250, self.warm_up)

    # ---------- Layout ----------
    def build_ui(self):
        # Visible text is filled in by apply_language(), so it can be switched at runtime.
        root = QWidget()
        self.setCentralWidget(root)
        main = QHBoxLayout(root)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        sidebar = QFrame(objectName="sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 18, 12, 12)
        side.setSpacing(8)
        side.addWidget(QLabel("🤖  JUGNU", objectName="brand"))
        side.addWidget(QLabel("Just an Unusually Genius\nNeural Utility", objectName="tagline"))
        side.addSpacing(10)
        self.new_btn = self.sidebar_button(side, self.new_chat)
        side.addSpacing(10)
        self.history_label = QLabel(objectName="historyLabel")
        side.addWidget(self.history_label)
        self.history_list = QListWidget(objectName="historyList")
        self.history_list.itemClicked.connect(self.select_chat)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_chat_menu)
        side.addWidget(self.history_list, 1)
        self.clear_btn = self.sidebar_button(side, self.clear_chat)
        self.clear_btn.setProperty("variant", "danger")
        self.voice_btn = self.sidebar_button(side, self.toggle_voice)
        self.voice_settings_btn = self.sidebar_button(side, self.open_voice_settings)
        self.language_btn = self.sidebar_button(side, self.toggle_language)
        self.theme_btn = self.sidebar_button(side, self.toggle_theme)
        if not self.tts.available:
            self.voice_btn.setEnabled(False)  # pyttsx3 not installed
            self.voice_settings_btn.setEnabled(False)
        main.addWidget(sidebar)

        content = QWidget(objectName="content")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        header = QFrame(objectName="header")
        header.setFixedHeight(64)
        head = QHBoxLayout(header)
        head.setContentsMargins(22, 0, 18, 0)
        self.header_title = QLabel(objectName="headerTitle")
        head.addWidget(self.header_title)
        head.addStretch(1)
        # Shown only while speech is playing (see poll_speech).
        self.stop_btn = QPushButton("⏹  Stop")
        self.stop_btn.setProperty("variant", "stop")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.stop_speaking)
        self.stop_btn.hide()
        head.addWidget(self.stop_btn)
        self.status = QLabel(objectName="status")
        head.addWidget(self.status)
        column.addWidget(header)

        self.scroll = QScrollArea(objectName="chatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.messages = QWidget(objectName="messages")
        self.messages_layout = QVBoxLayout(self.messages)
        self.messages_layout.setContentsMargins(20, 16, 20, 16)
        self.messages_layout.setSpacing(14)
        self.messages_layout.addStretch(1)
        self.scroll.setWidget(self.messages)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.verticalScrollBar().rangeChanged.connect(self.on_scroll_range)
        column.addWidget(self.scroll, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(12, 0, 12, 12)
        bottom.setSpacing(10)
        self.input_box = InputBox()
        self.input_box.setFixedHeight(64)
        self.input_box.submitted.connect(self.send_message)
        bottom.addWidget(self.input_box, 1)
        self.send_btn = QPushButton()
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setMinimumHeight(48)
        self.send_btn.clicked.connect(self.send_message)
        bottom.addWidget(self.send_btn)
        column.addLayout(bottom)
        main.addWidget(content, 1)

        QShortcut(QKeySequence("Ctrl+N"), self, self.new_chat)

    def sidebar_button(self, layout, slot):
        button = QPushButton()
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            self.resize_timer.start()  # re-fit bubbles once resizing settles
        return super().eventFilter(watched, event)

    def on_scroll_range(self, _minimum, maximum):
        if self._stick_to_bottom:
            self.scroll.verticalScrollBar().setValue(maximum)

    def scroll_to_bottom(self):
        # The new size is only known after the layout runs, so keep following it for a moment.
        self._stick_to_bottom = True
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
        QTimer.singleShot(300, self, self.stop_sticking)

    def stop_sticking(self):
        self._stick_to_bottom = False

    # ---------- Theme and language ----------
    def bubble_font(self):
        font = self.font()
        font.setPointSize(BUBBLE_PT)
        return font

    def mono_family(self):
        if self._mono is None:
            self._mono = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()
        return self._mono

    @property
    def colors(self):
        return core.DARK if self.dark_mode else core.LIGHT

    def apply_theme(self):
        self.setStyleSheet(build_stylesheet(self.colors))
        self.theme_btn.setText(self.theme_button_text())
        self.display_chat()  # reply bubbles carry theme colours in their rich text

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.save_settings()
        self.apply_theme()

    def t(self, key, **kwargs):
        """Look up a user-facing string in the currently selected language."""
        return get_string(self.language, key, **kwargs)

    def voice_button_text(self):
        return self.t("voice_on" if self.voice_enabled else "voice_off")

    def theme_button_text(self):
        return self.t("theme_to_light" if self.dark_mode else "theme_to_dark")

    def toggle_language(self):
        self.language = next_language(self.language)
        self.save_settings()
        self.apply_language()

    def apply_language(self):
        # Set every piece of visible text from the strings dictionary.
        self.new_btn.setText(self.t("new_chat_btn"))
        self.history_label.setText(self.t("history_label"))
        self.clear_btn.setText(self.t("clear_chat_btn"))
        self.voice_btn.setText(self.voice_button_text())
        self.voice_settings_btn.setText(self.t("voice_settings_btn"))
        self.language_btn.setText(self.t("language_btn", name=self.t("language_name")))
        self.theme_btn.setText(self.theme_button_text())
        self.header_title.setText(self.t("header_title"))
        self.send_btn.setText(self.t("send_btn"))
        if self.voice_dialog is not None:
            self.voice_dialog.retranslate()
        key, kwargs = self._status
        self.set_status(key, **kwargs)
        self.display_chat()  # Redraw so the welcome screen and "You" labels switch too.

    def set_status(self, key, **kwargs):
        # Store the key (not the text) so a language switch can re-translate the status line.
        self._status = (key, kwargs)
        self.status.setText("• " + self.t(key, **kwargs))

    def save_settings(self):
        core.save_settings(self.settings_file, dark_mode=self.dark_mode,
                           voice_enabled=self.voice_enabled, language=self.language,
                           voice_rate=self.voice_rate, voice_volume=self.voice_volume,
                           voice_id=self.voice_id)

    def save_history(self):
        try:
            core.save_history(self.chats, self.history_file)
        except (OSError, TypeError, ValueError) as error:
            self.set_status("status_save_error", error=error)

    # ---------- Voice ----------
    def toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        if not self.voice_enabled:
            self.tts.stop()  # Muting silences the current reply immediately.
        self.voice_btn.setText(self.voice_button_text())
        self.save_settings()

    def stop_speaking(self):
        self.tts.stop()
        self.poll_speech()  # hide the Stop button right away

    def read_aloud(self, text):
        # Reads exactly this message. Works even when the sidebar Voice toggle is off,
        # because the user asked for it explicitly. Replaces anything already being read.
        if not self.tts.available:
            return
        self.tts.stop()
        self.tts.speak(plain_text(text))  # without ** # ` and other Markdown symbols
        self.poll_speech()

    def test_voice(self):
        # Plays a short sample with the current settings, even if the Voice toggle is off.
        if not self.tts.available:
            return
        self.tts.stop()
        self.tts.speak(self.t("voice_test_sample"))
        self.poll_speech()

    def poll_speech(self):
        # Keep the Stop button and the Read aloud buttons in step with the speech engine.
        self.stop_btn.setVisible(bool(self.tts.speaking))
        available = bool(self.tts.available)
        self.voice_settings_btn.setEnabled(available)
        for bubble in self.bubbles:
            if bubble.read_btn is not None:
                bubble.read_btn.setEnabled(available)

    def push_voice_settings(self):
        # Hand the current values to the speech thread. Cheap, so it is safe on every slider tick.
        self.tts.apply_settings(self.voice_rate, self.voice_volume, self.voice_id)

    def open_voice_settings(self):
        if not self.tts.available:
            return
        if self.voice_dialog is None:
            self.voice_dialog = VoiceSettingsDialog(self)
        self.voice_dialog.show()
        self.voice_dialog.raise_()
        self.voice_dialog.activateWindow()

    # ---------- Chats ----------
    def make_draft(self):
        self.draft_chat = core.new_chat()
        self.current_id = self.draft_chat["id"]

    def current_chat(self):
        if self.draft_chat and self.draft_chat.get("id") == self.current_id:
            return self.draft_chat
        return self.find_chat(self.current_id)

    def find_chat(self, chat_id):
        return next((c for c in self.chats if c.get("id") == chat_id), None)

    def refresh_history_list(self):
        self.history_list.clear()
        for chat in reversed(self.chats):  # newest first
            item = QListWidgetItem(core.list_title(chat.get("title", core.NEW_CHAT_TITLE)))
            item.setData(Qt.UserRole, chat["id"])
            item.setToolTip(chat.get("title", ""))
            self.history_list.addItem(item)
            if chat["id"] == self.current_id:
                item.setSelected(True)
                self.history_list.setCurrentItem(item)

    def new_chat(self):
        # A blank chat is temporary. It must not create a history entry until a message is sent.
        self.tts.stop()
        self.make_draft()
        self.refresh_history_list()
        self.display_chat()
        self.input_box.setFocus()

    def select_chat(self, item):
        chat_id = item.data(Qt.UserRole)
        if self.find_chat(chat_id) is not None and chat_id != self.current_id:
            self.tts.stop()
            self.current_id = chat_id
            self.draft_chat = None
            self.display_chat()

    def show_chat_menu(self, pos):
        item = self.history_list.itemAt(pos)
        if item is None:
            return
        chat_id = item.data(Qt.UserRole)  # the menu acts on the chat that was clicked, not on its row
        menu = QMenu(self)
        menu.addAction(self.t("chat_menu_rename"), lambda: self.rename_chat(chat_id))
        menu.addAction(self.t("chat_menu_delete"), lambda: self.delete_chat(chat_id))
        menu.exec(self.history_list.viewport().mapToGlobal(pos))

    def ask_chat_title(self, initial):
        """Returns the text entered, or None if it was cancelled."""
        dialog = QInputDialog(self)
        dialog.setWindowTitle(self.t("rename_dialog_title"))
        dialog.setLabelText(self.t("rename_dialog_prompt"))
        dialog.setTextValue(initial)
        dialog.setOkButtonText(self.t("rename_save_btn"))
        dialog.setCancelButtonText(self.t("rename_cancel_btn"))
        return dialog.textValue() if dialog.exec() == QDialog.Accepted else None

    def confirm(self, title, message):
        return QMessageBox.question(self, title, message) == QMessageBox.Yes

    def rename_chat(self, chat_id):
        chat = self.find_chat(chat_id)
        if chat is None:
            return
        new_title = self.ask_chat_title(chat.get("title", ""))
        if new_title is None:
            return  # cancelled
        new_title = core.tidy_title(new_title)
        if not new_title or new_title == chat.get("title"):
            return  # an empty name is ignored: the old title stays
        chat["title"] = new_title
        self.save_history()
        self.refresh_history_list()

    def delete_chat(self, chat_id):
        chat = self.find_chat(chat_id)
        if chat is None:
            return
        if not self.confirm(self.t("delete_chat_title"),
                            self.t("delete_chat_message", title=chat.get("title", ""))):
            return
        was_open = chat_id == self.current_id
        self.chats = [saved for saved in self.chats if saved.get("id") != chat_id]  # only this chat goes
        if was_open:
            self.tts.stop()
            self.make_draft()  # deleting the open chat leaves a fresh empty one
        self.save_history()
        self.refresh_history_list()
        if was_open:
            self.display_chat()

    def clear_chat(self):
        chat = self.current_chat()
        if not chat or not chat.get("messages"):
            return  # Nothing saved to clear; leave the empty draft alone.
        if not self.confirm(self.t("clear_dialog_title"), self.t("clear_dialog_message")):
            return
        self.tts.stop()
        self.chats = [saved for saved in self.chats if saved.get("id") != chat.get("id")]
        self.make_draft()
        self.save_history()
        self.refresh_history_list()
        self.display_chat()

    # ---------- Messages ----------
    def clear_messages(self):
        self.bubbles = []
        while self.messages_layout.count() > 1:  # keep the stretch at the end
            widget = self.messages_layout.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()

    def display_chat(self):
        self.clear_messages()
        self.refresh_history_list()
        chat = self.current_chat()
        messages = chat.get("messages", []) if chat else []
        if not messages:
            self.show_welcome()
        for msg in messages:
            self.add_bubble(msg.get("role"), msg.get("content", ""), timestamp=msg.get("time"))
        self.scroll_to_bottom()

    def show_welcome(self):
        # Welcome splash shown on launch and for each empty New Chat.
        welcome = QWidget()
        layout = QVBoxLayout(welcome)
        layout.setContentsMargins(0, 24, 0, 0)
        layout.setSpacing(6)
        pixmap = QPixmap(os.path.join(HERE, "jugnu_bot.png"))
        if pixmap.isNull():
            # Friendly fallback if the companion image hasn't been copied beside the script.
            image = QLabel("🤖", objectName="welcomeEmoji")
        else:
            image = QLabel()
            image.setPixmap(pixmap.scaled(360, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        for widget in (image, QLabel(self.t("welcome_title"), objectName="welcomeTitle"),
                       QLabel("Just an Unusually Genius Neural Utility", objectName="welcomeTagline"),
                       QLabel(self.t("welcome_prompt"), objectName="welcomePrompt")):
            layout.addWidget(widget, 0, Qt.AlignHCenter)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, welcome)

    def add_bubble(self, role, text, timestamp=None):
        if not self.bubbles and self.messages_layout.count() > 1:
            self.clear_messages()  # the first message replaces the welcome splash
        bubble = Bubble(self, role, text, timestamp)
        bubble.fit(max_bubble_width(self.scroll.viewport().width()))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setLayout(row)
        if role == "user":
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, holder)
        self.bubbles.append(bubble)
        return bubble

    def fit_bubbles(self):
        width = max_bubble_width(self.scroll.viewport().width())
        for bubble in self.bubbles:
            bubble.fit(width)

    # ---------- Sending ----------
    def warm_up(self):
        run_in_background(lambda: self.bridge.warmed.emit(core.warm_up()))

    def send_message(self):
        if self.busy:
            return
        user_text = self.input_box.toPlainText().strip()
        if not user_text:
            return
        self.tts.stop()  # A new message interrupts any reply still being read aloud.
        chat = self.current_chat()
        if not chat:
            self.make_draft()
            chat = self.current_chat()
        if self.draft_chat and chat.get("id") == self.draft_chat.get("id"):
            self.chats.append(self.draft_chat)
            self.draft_chat = None
        if chat.get("title") == core.NEW_CHAT_TITLE:
            chat["title"] = user_text[:core.MAX_LIST_TITLE]
        time_now = core.message_time_text()
        chat["messages"].append({"role": "user", "content": user_text, "time": time_now})
        self.input_box.clear()
        self.add_bubble("user", user_text, timestamp=time_now)
        self.scroll_to_bottom()
        self.refresh_history_list()
        self.save_history()
        self.busy = True
        self.send_btn.setEnabled(False)
        self.set_status("status_thinking")

        # Clock/date and arithmetic questions are answered locally—no model call required.
        answer = core.local_answer(user_text, self.language)
        if answer is not None:
            self.finish_answer(chat["id"], answer, False)
            return
        # Send a copy, so the request never reads the list while the GUI changes it.
        snapshot = {"messages": [dict(m) for m in chat["messages"]]}
        run_in_background(self.ask_ollama, chat["id"], snapshot, self.language)

    def ask_ollama(self, chat_id, chat, language):
        # Background thread: no widgets here. The result goes back through a signal.
        answer, is_error = core.ask_ollama(chat, language)
        self.bridge.answered.emit(chat_id, answer, is_error)

    def finish_answer(self, chat_id, answer, is_error=False):
        chat = self.find_chat(chat_id)  # may be gone if it was deleted while the request ran
        time_now = core.message_time_text()
        if chat and isinstance(answer, str) and answer.strip():
            message = {"role": "assistant", "content": answer, "time": time_now}
            if is_error:
                message["is_error"] = True
            chat["messages"].append(message)
            self.save_history()
            # Only display if the user is still viewing the chat that received the answer.
            if chat_id == self.current_id:
                self.add_bubble("assistant", answer, timestamp=time_now)
                self.scroll_to_bottom()
                if self.voice_enabled:
                    self.tts.speak(plain_text(answer))
        self.busy = False
        self.send_btn.setEnabled(True)
        self.set_status("status_ready")
        self.refresh_history_list()

    def closeEvent(self, event):
        self.speech_timer.stop()
        self.tts.shutdown()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JUGNU")
    lock = HistoryLock(core.HISTORY_FILE)
    try:
        lock.acquire()
    except HistoryInUseError:
        QMessageBox.critical(None, "Chat history in use",
                             "Another JUGNU window is using this chat history. "
                             "Close that window before opening another.")
        return 1
    except OSError as error:
        QMessageBox.critical(None, "Chat history unavailable", f"Could not lock chat history.\n\n{error}")
        return 1
    try:
        window = JugnuWindow()
        window.show()
        return app.exec()
    finally:
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
