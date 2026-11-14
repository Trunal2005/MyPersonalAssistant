"""Offline text-to-speech for JUGNU.

All speech runs on one background worker thread, so the GUI never
freezes. The public methods (speak / stop / shutdown) are safe to call from the
GUI thread; the worker never touches any widget.

If pyttsx3 or a system voice is missing, `TTSManager.available` becomes False
and every method quietly does nothing, so the app keeps working without voice.
"""
import queue
import re
import threading

try:
    import pyttsx3
except ImportError:  # JUGNU must still run when pyttsx3 is not installed
    pyttsx3 = None


DEFAULT_RATE = 175      # words per minute
DEFAULT_VOLUME = 1.0    # 0.0 (silent) to 1.0 (full)
RATE_MIN, RATE_MAX = 80, 300


def clamp(value, low, high):
    return max(low, min(high, value))


def clean_for_speech(text):
    """Strip markdown, code and URLs so the voice doesn't read symbols aloud."""
    text = re.sub(r"```.*?```", " Code block omitted. ", text, flags=re.S)
    text = re.sub(r"`([^`]*)`", r"\1", text)                # inline code
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)    # [label](url) -> label
    text = re.sub(r"https?://\S+", "link", text)
    text = re.sub(r"[*_#>~|]+", " ", text)                  # markdown symbols
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


class TTSManager:
    def __init__(self, rate=DEFAULT_RATE, volume=DEFAULT_VOLUME, voice_id=None):
        self.available = pyttsx3 is not None
        self.rate = clamp(rate, RATE_MIN, RATE_MAX)
        self.volume = clamp(volume, 0.0, 1.0)
        self.voice_id = voice_id  # None means "the system's default voice"
        self.voices = []          # [(voice_id, name)], filled in by the worker once the engine is up
        self._settings_version = 0
        self._queue = queue.Queue()
        self._generation = 0
        self._pending = []  # generation of every item queued or being read, not yet finished
        self._lock = threading.Lock()
        self._engine = None
        if self.available:
            threading.Thread(target=self._worker, name="jugnu-tts", daemon=True).start()

    # ---------- public API (call from the GUI thread) ----------
    def speak(self, text):
        """Queue text to be read aloud. Does nothing if TTS is unavailable."""
        if not self.available:
            return
        text = clean_for_speech(text)
        if text:
            with self._lock:
                gen = self._generation
                self._pending.append(gen)
            self._queue.put((gen, text))

    @property
    def speaking(self):
        """True while text is queued or being read. Turns False as soon as stop() is called."""
        if not self.available:
            return False
        with self._lock:
            return self._generation in self._pending

    def apply_settings(self, rate, volume, voice_id):
        """Change speed, volume and voice. Takes effect from the next sentence spoken.

        Only remembers the new values; the worker thread, which owns the engine,
        applies them. Nothing here waits for the engine, so the GUI never freezes.
        """
        with self._lock:
            self.rate = clamp(rate, RATE_MIN, RATE_MAX)
            self.volume = clamp(volume, 0.0, 1.0)
            self.voice_id = voice_id
            self._settings_version += 1

    def stop(self):
        """Interrupt current speech and drop anything still queued."""
        if not self.available:
            return
        with self._lock:
            self._generation += 1
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is None:  # shutdown marker: keep it for the worker
                self._queue.put(None)
                break
            self._finished(item[0])

    def shutdown(self):
        """Stop speaking and let the worker thread exit."""
        self.stop()
        if self.available:
            self._queue.put(None)

    # ---------- worker thread ----------
    def _current_generation(self):
        with self._lock:
            return self._generation

    def _finished(self, gen):
        with self._lock:
            try:
                self._pending.remove(gen)
            except ValueError:
                pass

    def _apply_pending_settings(self, engine, state):
        """Worker thread only. Push changed settings into the engine."""
        with self._lock:
            version = self._settings_version
            rate, volume, voice_id = self.rate, self.volume, self.voice_id
        if version == state["version"]:
            return
        state["version"] = version
        # Each property is set on its own, so one failure can't block the others.
        for name, value in (("rate", rate), ("volume", volume)):
            try:
                engine.setProperty(name, value)
            except Exception:
                pass
        # A saved voice that is no longer installed quietly falls back to the default.
        known = {vid for vid, _ in self.voices}
        wanted = voice_id if voice_id in known else state["default_voice"]
        if wanted is not None:
            try:
                engine.setProperty("voice", wanted)
            except Exception:
                pass

    def _worker(self):
        try:
            engine = pyttsx3.init()
        except Exception:  # no usable speech driver / voice on this machine
            self.available = False
            return
        self._engine = engine

        state = {"version": -1, "default_voice": None}
        try:
            state["default_voice"] = engine.getProperty("voice")
        except Exception:
            pass
        try:
            self.voices = [(v.id, v.name) for v in engine.getProperty("voices")]
        except Exception:
            self.voices = []
        self._apply_pending_settings(engine, state)

        active = {"gen": None}

        def on_word(name, location, length):
            # Runs inside the engine loop on THIS thread, which is the safe place
            # to call engine.stop(). If stop() was requested, cut speech mid-sentence.
            if active["gen"] is not None and active["gen"] != self._current_generation():
                try:
                    engine.stop()
                except Exception:
                    pass

        try:
            engine.connect("started-word", on_word)
        except Exception:
            pass  # driver without word events: we still stop at the next sentence

        while True:
            item = self._queue.get()
            if item is None:
                return
            gen, text = item
            for sentence in split_sentences(text):
                if gen != self._current_generation():
                    break  # interrupted before this sentence started
                self._apply_pending_settings(engine, state)  # picks up slider/voice changes
                active["gen"] = gen
                try:
                    engine.say(sentence)
                    engine.runAndWait()
                except Exception:
                    break
            active["gen"] = None
            self._finished(gen)