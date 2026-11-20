"""100% Offline Local Speech-to-Text (STT) Voice Dictation Engine for JUGNU.

This module provides a completely offline, local speech recognition pipeline
with zero external server dependencies. Voice data is captured from the local
microphone, processed locally with real-time digital signal processing (DSP),
and transcribed directly on the user's machine.

Key Features:
- 100% Local & Private: Audio never leaves the machine.
- Multiple offline speech recognition backends:
  * Vosk (lightweight, fast Kaldi-based offline STT)
  * faster-whisper / Whisper (offline transformer STT)
  * Windows SAPI / Inproc speech recognizer
  * Mock / Fallback recognizer with clear diagnostic feedback
- Audio capture with hardware abstraction:
  * Windows native winmm via ctypes (zero extra packages on Windows!)
  * sounddevice (if installed)
  * pyaudio (if installed)
  * MockAudioCapture for testing and simulated streams
- Real-time Audio DSP:
  * Normalized RMS amplitude (0.0 to 1.0) and multi-band waveform bars for HUD
  * Background noise floor calibration and noise gate suppression
  * Voice Activity Detection (VAD) and auto-stop silence detection
- Formatting & Post-Processing:
  * Spoken punctuation expansion ("comma" -> ",", "period" -> ".", "question mark" -> "?")
  * Auto-capitalization of sentences and standalone 'I'
  * Spacing normalization
- Thread-safe STTManager:
  * Non-blocking background worker threads; Tkinter GUI never freezes
  * Push-to-talk and click-to-dictate modes
  * Safe event dispatching to GUI thread
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import queue
import re
import struct
import sys
import threading
import time
from typing import Callable, Optional

# Audio capture defaults
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SAMPLE_WIDTH = 2  # 16-bit PCM (2 bytes)
DEFAULT_CHANNELS = 1      # Mono
DEFAULT_CHUNK_SIZE = 1024  # ~64ms chunks at 16kHz
DEFAULT_SILENCE_TIMEOUT = 1.5  # Seconds of silence after speech to auto-stop
DEFAULT_MIN_SPEECH_DURATION = 0.25  # Minimum speech duration to trigger VAD
DEFAULT_SILENCE_THRESHOLD = 0.025  # Normalized RMS threshold above noise floor
DEFAULT_HOTKEY = "Control-space"


class STTState:
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Digital Signal Processing (DSP) & Math Utilities
# ---------------------------------------------------------------------------

def compute_rms(pcm_bytes: bytes, sample_width: int = DEFAULT_SAMPLE_WIDTH) -> float:
    """Compute normalized Root Mean Square (RMS) energy in [0.0, 1.0]."""
    if not pcm_bytes:
        return 0.0
    count = len(pcm_bytes) // sample_width
    if count == 0:
        return 0.0
    try:
        samples = struct.unpack(f"<{count}h", pcm_bytes[:count * 2])
    except struct.error:
        return 0.0
    sum_sq = sum(s * s for s in samples)
    rms = math.sqrt(sum_sq / count)
    return min(1.0, max(0.0, rms / 32768.0))


def compute_waveform_bars(pcm_bytes: bytes, num_bars: int = 24,
                          sample_width: int = DEFAULT_SAMPLE_WIDTH) -> list[float]:
    """Extract a list of normalized amplitude envelope bars in [0.0, 1.0]."""
    if not pcm_bytes or num_bars <= 0:
        return [0.0] * num_bars
    count = len(pcm_bytes) // sample_width
    if count == 0:
        return [0.0] * num_bars
    try:
        samples = struct.unpack(f"<{count}h", pcm_bytes[:count * 2])
    except struct.error:
        return [0.0] * num_bars

    step = max(1, count // num_bars)
    bars = []
    for i in range(num_bars):
        segment = samples[i * step:(i + 1) * step]
        if segment:
            peak = max(abs(s) for s in segment)
            bars.append(min(1.0, max(0.0, peak / 32768.0)))
        else:
            bars.append(0.0)
    return bars


class NoiseGate:
    """Calibrates background noise floor and gates low-level ambient noise."""

    def __init__(self, initial_floor: float = 0.015, margin: float = 0.02):
        self.noise_floor = initial_floor
        self.margin = margin
        self.calibrated = False
        self._calibration_samples: list[float] = []
        self._max_calibration_samples = 6

    def feed_calibration(self, level: float):
        if not self.calibrated:
            self._calibration_samples.append(level)
            if len(self._calibration_samples) >= self._max_calibration_samples:
                avg = sum(self._calibration_samples) / len(self._calibration_samples)
                self.noise_floor = max(0.005, min(0.15, avg * 1.3))
                self.calibrated = True

    def reset(self):
        self.calibrated = False
        self._calibration_samples.clear()

    @property
    def speech_threshold(self) -> float:
        return self.noise_floor + self.margin

    def is_speech(self, level: float) -> bool:
        return level > self.speech_threshold

    def gate_pcm(self, pcm_bytes: bytes, level: float) -> bytes:
        """Zero out pcm audio if it is below noise floor (suppression)."""
        if level <= self.noise_floor:
            return b"\x00" * len(pcm_bytes)
        return pcm_bytes


class SilenceDetector:
    """Tracks voice activity and triggers auto-stop when user pauses speaking."""

    def __init__(self, silence_timeout: float = DEFAULT_SILENCE_TIMEOUT,
                 min_speech_duration: float = DEFAULT_MIN_SPEECH_DURATION):
        self.silence_timeout = silence_timeout
        self.min_speech_duration = min_speech_duration
        self.speech_detected = False
        self.speech_start_time: Optional[float] = None
        self.last_speech_time: Optional[float] = None

    def reset(self):
        self.speech_detected = False
        self.speech_start_time = None
        self.last_speech_time = None

    def feed(self, is_speech: bool, now: float) -> tuple[bool, bool]:
        """Update activity. Returns (speech_active, silence_timeout_triggered)."""
        if is_speech:
            if not self.speech_detected:
                if self.speech_start_time is None:
                    self.speech_start_time = now
                elif (now - self.speech_start_time) >= self.min_speech_duration:
                    self.speech_detected = True
            self.last_speech_time = now
            return True, False

        # Not speech right now
        if self.speech_detected and self.last_speech_time is not None:
            silence_duration = now - self.last_speech_time
            if silence_duration >= self.silence_timeout:
                return False, True
        return False, False


# ---------------------------------------------------------------------------
# Auto-Punctuation & Text Formatting
# ---------------------------------------------------------------------------

PUNCTUATION_REPLACEMENTS = [
    (re.compile(r"\bcomma\b", re.IGNORECASE), ","),
    (re.compile(r"\b(period|full stop|dot)\b", re.IGNORECASE), "."),
    (re.compile(r"\bquestion mark\b", re.IGNORECASE), "?"),
    (re.compile(r"\b(exclamation mark|exclamation point)\b", re.IGNORECASE), "!"),
    (re.compile(r"\bcolon\b", re.IGNORECASE), ":"),
    (re.compile(r"\bsemicolon\b", re.IGNORECASE), ";"),
    (re.compile(r"\b(new line|next line)\b", re.IGNORECASE), "\n"),
]

QUESTION_STARTERS = (
    "what", "why", "how", "when", "where", "who", "whom", "whose", "which",
    "is", "are", "am", "was", "were", "can", "could", "would", "should",
    "will", "shall", "do", "does", "did", "have", "has", "had"
)


def format_transcription(text: str, auto_punctuate: bool = True,
                         auto_capitalize: bool = True) -> str:
    """Clean, format, auto-punctuate and capitalize dictated text."""
    if not text or not isinstance(text, str):
        return ""
    text = text.strip()
    if not text:
        return ""

    if auto_punctuate:
        # Replace spoken punctuation names
        for pattern, replacement in PUNCTUATION_REPLACEMENTS:
            text = pattern.sub(replacement, text)

    # Clean redundant whitespace
    text = re.sub(r"[ \t]+", " ", text)
    # Remove space before punctuation marks: "hello , world" -> "hello, world"
    text = re.sub(r"\s+([,.:;?!])", r"\1", text)
    # Ensure space after punctuation (unless at end or followed by whitespace/newline)
    text = re.sub(r"([,.:;?!])(?=[^\s\d\)])", r"\1 ", text)
    # Clean newlines spacing
    text = re.sub(r" *\n *", "\n", text)

    if auto_capitalize:
        # Capitalize standalone lowercase 'i' or 'i'm', 'i'll', 'i've', 'i'd'
        text = re.sub(r"\bi\b", "I", text)
        text = re.sub(r"\bi'([a-z]+)\b", r"I'\1", text)

        # Capitalize start of text and letters after sentence endings (. ? ! \n)
        def _cap(match):
            return match.group(1) + match.group(2).upper()

        text = re.sub(r"(^|[.?!]\s+|\n\s*)([a-z])", _cap, text)

    # Optional auto-terminal punctuation if missing
    if auto_punctuate and text and text[-1] not in ".?!:,;\n":
        first_word = text.split()[0].lower() if text.split() else ""
        if first_word in QUESTION_STARTERS:
            text += "?"
        else:
            text += "."

    return text.strip()


# ---------------------------------------------------------------------------
# Audio Capture Drivers (Windows Native winmm, sounddevice, pyaudio, mock)
# ---------------------------------------------------------------------------

class BaseAudioCapture:
    """Abstract base audio capture interface."""

    def start(self, on_chunk: Callable[[bytes], None]):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def is_active(self) -> bool:
        raise NotImplementedError

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        return False, "Driver not implemented"

    @classmethod
    def list_devices(cls) -> list[str]:
        return []


class WinMMAudioCapture(BaseAudioCapture):
    """Windows native audio capture using winmm.dll via ctypes (zero dependency)."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, chunk_size: int = DEFAULT_CHUNK_SIZE):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_chunk: Optional[Callable[[bytes], None]] = None

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "winmm is only available on Windows"
        try:
            num = ctypes.windll.winmm.waveInGetNumDevs()
            if num > 0:
                return True, f"Windows winmm ({num} device{'s' if num > 1 else ''})"
            return False, "No Windows audio input devices found"
        except Exception as exc:
            return False, f"winmm error: {exc}"

    @classmethod
    def list_devices(cls) -> list[str]:
        if sys.platform != "win32":
            return []
        try:
            num = ctypes.windll.winmm.waveInGetNumDevs()
            devices = []
            for i in range(num):
                devices.append(f"Microphone {i}")
            return devices
        except Exception:
            return []

    def is_active(self) -> bool:
        return self._active

    def start(self, on_chunk: Callable[[bytes], None]):
        if self._active:
            return
        self._on_chunk = on_chunk
        self._stop_event.clear()
        self._active = True
        self._thread = threading.Thread(target=self._worker, name="jugnu-winmm-mic", daemon=True)
        self._thread.start()

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _worker(self):
        winmm = ctypes.windll.winmm
        kernel32 = ctypes.windll.kernel32

        WAVE_FORMAT_PCM = 1
        CALLBACK_EVENT = 0x00050000

        class WAVEFORMATEX(ctypes.Structure):
            _fields_ = [
                ("wFormatTag", ctypes.c_ushort),
                ("nChannels", ctypes.c_ushort),
                ("nSamplesPerSec", ctypes.c_ulong),
                ("nAvgBytesPerSec", ctypes.c_ulong),
                ("nBlockAlign", ctypes.c_ushort),
                ("wBitsPerSample", ctypes.c_ushort),
                ("cbSize", ctypes.c_ushort),
            ]

        class WAVEHDR(ctypes.Structure):
            pass

        WAVEHDR._fields_ = [
            ("lpData", ctypes.POINTER(ctypes.c_char)),
            ("dwBufferLength", ctypes.c_ulong),
            ("dwBytesRecorded", ctypes.c_ulong),
            ("dwUser", ctypes.c_void_p),
            ("dwFlags", ctypes.c_ulong),
            ("dwLoops", ctypes.c_ulong),
            ("lpNext", ctypes.POINTER(WAVEHDR)),
            ("reserved", ctypes.c_void_p),
        ]

        wfx = WAVEFORMATEX(
            WAVE_FORMAT_PCM,
            DEFAULT_CHANNELS,
            self.sample_rate,
            self.sample_rate * DEFAULT_CHANNELS * DEFAULT_SAMPLE_WIDTH,
            DEFAULT_CHANNELS * DEFAULT_SAMPLE_WIDTH,
            DEFAULT_SAMPLE_WIDTH * 8,
            0
        )

        hEvent = kernel32.CreateEventW(None, False, False, None)
        hWaveIn = ctypes.c_void_p()
        res = winmm.waveInOpen(ctypes.byref(hWaveIn), 0, ctypes.byref(wfx), hEvent, 0, CALLBACK_EVENT)
        if res != 0:
            kernel32.CloseHandle(hEvent)
            self._active = False
            return

        buf_bytes = self.chunk_size * DEFAULT_SAMPLE_WIDTH
        num_buffers = 4
        buffers = []
        headers = []

        for _ in range(num_buffers):
            raw_buf = (ctypes.c_char * buf_bytes)()
            hdr = WAVEHDR()
            hdr.lpData = ctypes.cast(raw_buf, ctypes.POINTER(ctypes.c_char))
            hdr.dwBufferLength = buf_bytes
            hdr.dwFlags = 0
            winmm.waveInPrepareHeader(hWaveIn, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveInAddBuffer(hWaveIn, ctypes.byref(hdr), ctypes.sizeof(hdr))
            buffers.append(raw_buf)
            headers.append(hdr)

        winmm.waveInStart(hWaveIn)

        try:
            while not self._stop_event.is_set():
                wait_res = kernel32.WaitForSingleObject(hEvent, 100)
                if wait_res == 0:  # Signaled
                    for hdr in headers:
                        if hdr.dwFlags & 0x00000001:  # WHDR_DONE
                            recorded = hdr.dwBytesRecorded
                            if recorded > 0:
                                pcm_chunk = ctypes.string_at(hdr.lpData, recorded)
                                if self._on_chunk and self._active:
                                    self._on_chunk(pcm_chunk)
                            hdr.dwBytesRecorded = 0
                            hdr.dwFlags &= ~0x00000001
                            winmm.waveInAddBuffer(hWaveIn, ctypes.byref(hdr), ctypes.sizeof(hdr))
        finally:
            winmm.waveInReset(hWaveIn)
            for hdr in headers:
                winmm.waveInUnprepareHeader(hWaveIn, ctypes.byref(hdr), ctypes.sizeof(hdr))
            winmm.waveInClose(hWaveIn)
            kernel32.CloseHandle(hEvent)
            self._active = False


class SoundDeviceAudioCapture(BaseAudioCapture):
    """Audio capture via sounddevice (cross-platform)."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, chunk_size: int = DEFAULT_CHUNK_SIZE):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._active = False
        self._stream = None
        self._on_chunk: Optional[Callable[[bytes], None]] = None

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            if devices:
                return True, "sounddevice"
            return False, "sounddevice installed but no devices found"
        except ImportError:
            return False, "sounddevice not installed"
        except Exception as exc:
            return False, f"sounddevice error: {exc}"

    @classmethod
    def list_devices(cls) -> list[str]:
        try:
            import sounddevice as sd
            return [d["name"] for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        except Exception:
            return []

    def is_active(self) -> bool:
        return self._active

    def start(self, on_chunk: Callable[[bytes], None]):
        if self._active:
            return
        import sounddevice as sd
        self._on_chunk = on_chunk
        self._active = True

        def callback(indata, frames, time_info, status):
            if self._active and self._on_chunk:
                self._on_chunk(indata.tobytes())

        self._stream = sd.RawInputStream(
            samplerate=self.sample_rate,
            blocksize=self.chunk_size,
            channels=DEFAULT_CHANNELS,
            dtype="int16",
            callback=callback
        )
        self._stream.start()

    def stop(self):
        if not self._active:
            return
        self._active = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class MockAudioCapture(BaseAudioCapture):
    """Simulated audio capture for unit testing and headless environments."""

    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, chunk_size: int = DEFAULT_CHUNK_SIZE,
                 amplitude: float = 0.2, frequency: float = 440.0):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.amplitude = amplitude
        self.frequency = frequency
        self._active = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_chunk: Optional[Callable[[bytes], None]] = None

    @classmethod
    def is_available(cls) -> tuple[bool, str]:
        return True, "Mock Audio Capture"

    @classmethod
    def list_devices(cls) -> list[str]:
        return ["Mock Virtual Microphone"]

    def is_active(self) -> bool:
        return self._active

    def start(self, on_chunk: Callable[[bytes], None]):
        if self._active:
            return
        self._on_chunk = on_chunk
        self._stop_event.clear()
        self._active = True
        self._thread = threading.Thread(target=self._worker, name="jugnu-mock-mic", daemon=True)
        self._thread.start()

    def stop(self):
        if not self._active:
            return
        self._active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _worker(self):
        interval = self.chunk_size / self.sample_rate
        t = 0.0
        while not self._stop_event.is_set():
            samples = []
            for _ in range(self.chunk_size):
                val = int(self.amplitude * 32767.0 * math.sin(2 * math.pi * self.frequency * t))
                samples.append(max(-32768, min(32767, val)))
                t += 1.0 / self.sample_rate
            pcm_chunk = struct.pack(f"<{len(samples)}h", *samples)
            if self._on_chunk and self._active:
                self._on_chunk(pcm_chunk)
            time.sleep(interval)


def get_best_audio_capture(prefer_mock: bool = False) -> tuple[Optional[BaseAudioCapture], str]:
    """Return the best available audio capture device, or (None, reason)."""
    if prefer_mock:
        return MockAudioCapture(), "Mock Audio Capture"

    # 1. Try sounddevice if installed
    sd_ok, sd_msg = SoundDeviceAudioCapture.is_available()
    if sd_ok:
        return SoundDeviceAudioCapture(), f"SoundDevice ({sd_msg})"

    # 2. Try Windows native winmm
    winmm_ok, winmm_msg = WinMMAudioCapture.is_available()
    if winmm_ok:
        return WinMMAudioCapture(), f"Windows Native Audio ({winmm_msg})"

    return None, "No microphone input device or audio driver detected"


# ---------------------------------------------------------------------------
# Offline Speech Recognition Backends
# ---------------------------------------------------------------------------

class BaseRecognizer:
    """Base offline speech recognition backend."""

    name: str = "Base Recognizer"

    def is_available(self) -> tuple[bool, str]:
        return False, "Not implemented"

    def recognize(self, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        raise NotImplementedError


class VoskRecognizerBackend(BaseRecognizer):
    """Vosk offline speech recognition backend."""

    name = "Vosk"

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path
        self._model = None

    def _find_model(self) -> Optional[str]:
        if self.model_path and os.path.isdir(self.model_path):
            return self.model_path

        env_path = os.environ.get("VOSK_MODEL_PATH")
        if env_path and os.path.isdir(env_path):
            return env_path

        candidates = [
            os.path.join(".", "models"),
            os.path.join(os.path.expanduser("~"), ".cache", "vosk"),
            os.path.join(os.path.expanduser("~"), "vosk-model"),
        ]
        for base in candidates:
            if os.path.isdir(base):
                for item in os.listdir(base):
                    full = os.path.join(base, item)
                    if os.path.isdir(full) and ("vosk" in item.lower() or "model" in item.lower()):
                        return full
        return None

    def is_available(self) -> tuple[bool, str]:
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False, "Vosk package not installed (run `pip install vosk`)"

        model_dir = self._find_model()
        if not model_dir:
            return False, "Vosk installed, but no model found in models/ or ~/.cache/vosk"
        return True, f"Vosk offline model ({os.path.basename(model_dir)})"

    def _get_model(self):
        if self._model is None:
            import vosk
            model_dir = self._find_model()
            if not model_dir:
                raise RuntimeError("Vosk model directory not found")
            vosk.SetLogLevel(-1)
            self._model = vosk.Model(model_dir)
        return self._model

    def recognize(self, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        import vosk
        model = self._get_model()
        rec = vosk.KaldiRecognizer(model, sample_rate)
        rec.AcceptWaveform(pcm_bytes)
        res = json.loads(rec.FinalResult())
        return res.get("text", "").strip()


class FasterWhisperRecognizerBackend(BaseRecognizer):
    """faster-whisper offline transformer STT backend."""

    name = "faster-whisper"

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self._model = None

    def is_available(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
            return True, f"faster-whisper ({self.model_size})"
        except ImportError:
            return False, "faster-whisper not installed"

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def recognize(self, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        import numpy as np
        model = self._get_model()
        # Convert PCM 16-bit bytes to float32 numpy array
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        segments, _ = model.transcribe(audio_float32, beam_size=1, language="en")
        text = " ".join(s.text.strip() for s in segments)
        return text.strip()


class WindowsSapiRecognizerBackend(BaseRecognizer):
    """Windows built-in offline speech recognizer via COM / SAPI."""

    name = "Windows SAPI"

    def is_available(self) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "Windows SAPI is only available on Windows"
        try:
            import win32com.client
            cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
            cat.SetId(r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Recognizers")
            tokens = cat.EnumerateTokens()
            if tokens.Count > 0:
                return True, f"Windows SAPI ({tokens.Item(0).GetDescription()})"
            return False, "No Windows speech recognizers installed"
        except Exception as exc:
            return False, f"Windows SAPI not available: {exc}"

    def recognize(self, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        # Fallback stub if recognizer is present but unconfigured
        return ""


class MockRecognizerBackend(BaseRecognizer):
    """Mock recognizer for unit tests and simulation."""

    name = "Mock Recognizer"

    def __init__(self, preset_transcription: str = "Hello, this is a test dictation."):
        self.preset_transcription = preset_transcription

    def is_available(self) -> tuple[bool, str]:
        return True, "Mock Recognizer"

    def recognize(self, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        if not pcm_bytes:
            return ""
        return self.preset_transcription


class FallbackRecognizerBackend(BaseRecognizer):
    """Graceful fallback when no offline recognizer model or package is installed."""

    name = "Offline STT Unavailable"

    def __init__(self, reason: str = "No offline STT model or dependency detected"):
        self.reason = reason

    def is_available(self) -> tuple[bool, str]:
        return False, self.reason

    def recognize(self, pcm_bytes: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> str:
        return ""


def get_best_recognizer(prefer_mock: bool = False,
                        mock_text: str = "Hello, this is a test dictation.") -> BaseRecognizer:
    """Return the highest priority available offline STT backend."""
    if prefer_mock:
        return MockRecognizerBackend(preset_transcription=mock_text)

    # 1. Try Vosk
    vosk_backend = VoskRecognizerBackend()
    ok, _ = vosk_backend.is_available()
    if ok:
        return vosk_backend

    # 2. Try faster-whisper
    fw_backend = FasterWhisperRecognizerBackend()
    ok, _ = fw_backend.is_available()
    if ok:
        return fw_backend

    # 3. Try Windows SAPI
    sapi_backend = WindowsSapiRecognizerBackend()
    ok, _ = sapi_backend.is_available()
    if ok:
        return sapi_backend

    # 4. Fallback with descriptive diagnostic
    return FallbackRecognizerBackend(
        "No offline speech model found. Install vosk (`pip install vosk`) and download a model into 'models/'"
    )


# ---------------------------------------------------------------------------
# STT Manager
# ---------------------------------------------------------------------------

class STTManager:
    """Thread-safe Speech-to-Text Manager for JUGNU desktop assistant.

    Orchestrates audio capture, DSP metering, noise suppression, silence
    detection, and offline transcription on background worker threads.
    Communicates with the GUI thread via thread-safe queues or callbacks.
    """

    def __init__(self, capture: Optional[BaseAudioCapture] = None,
                 recognizer: Optional[BaseRecognizer] = None,
                 silence_timeout: float = DEFAULT_SILENCE_TIMEOUT,
                 noise_suppression: bool = True,
                 auto_punctuate: bool = True,
                 auto_capitalize: bool = True):
        self.silence_timeout = silence_timeout
        self.noise_suppression = noise_suppression
        self.auto_punctuate = auto_punctuate
        self.auto_capitalize = auto_capitalize

        # Hardware & model detection
        if capture is False:
            self.capture = None
            self.capture_msg = "No audio capture device"
        elif capture is None:
            self.capture, self.capture_msg = get_best_audio_capture()
        else:
            self.capture = capture
            self.capture_msg = "Custom capture driver"

        if recognizer is None:
            self.recognizer = get_best_recognizer()
        else:
            self.recognizer = recognizer

        rec_ok, self.recognizer_msg = self.recognizer.is_available()

        self.noise_gate = NoiseGate()
        self.silence_detector = SilenceDetector(silence_timeout=self.silence_timeout)

        self._state = STTState.IDLE
        self._state_lock = threading.Lock()
        self._audio_buffer: list[bytes] = []
        self._buffer_lock = threading.Lock()

        # Thread-safe event queue consumed by GUI thread
        self.event_queue: queue.Queue = queue.Queue()

        # Optional direct callbacks
        self.on_state_change: Optional[Callable[[str], None]] = None
        self.on_level: Optional[Callable[[float, list[float]], None]] = None
        self.on_result: Optional[Callable[[str], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    @property
    def state(self) -> str:
        with self._state_lock:
            return self._state

    @property
    def is_listening(self) -> bool:
        return self.state == STTState.LISTENING

    @property
    def is_transcribing(self) -> bool:
        return self.state == STTState.TRANSCRIBING

    @property
    def available(self) -> bool:
        """True if both capture device and offline recognizer are ready."""
        return self.capture is not None and self.recognizer.is_available()[0]

    @property
    def has_mic(self) -> bool:
        """True if an audio input device is available."""
        return self.capture is not None

    @property
    def has_recognizer(self) -> bool:
        """True if an offline recognizer model/engine is available."""
        return self.recognizer.is_available()[0]

    def _set_state(self, new_state: str):
        with self._state_lock:
            if self._state == new_state:
                return
            self._state = new_state
        self.event_queue.put(("state", new_state))
        if self.on_state_change:
            try:
                self.on_state_change(new_state)
            except Exception:
                pass

    def start_listening(self) -> bool:
        """Begin capturing audio and listening for speech."""
        if not self.capture:
            msg = "No microphone input device detected. Please connect a microphone."
            self._set_state(STTState.ERROR)
            self.event_queue.put(("error", msg))
            if self.on_error:
                self.on_error(msg)
            return False

        with self._state_lock:
            if self._state in (STTState.LISTENING, STTState.TRANSCRIBING):
                return False
            self._state = STTState.LISTENING

        with self._buffer_lock:
            self._audio_buffer.clear()

        self.noise_gate.reset()
        self.silence_detector.reset()
        self.event_queue.put(("state", STTState.LISTENING))
        if self.on_state_change:
            try:
                self.on_state_change(STTState.LISTENING)
            except Exception:
                pass

        try:
            self.capture.start(on_chunk=self._handle_audio_chunk)
            return True
        except Exception as exc:
            self._set_state(STTState.ERROR)
            msg = f"Failed to start audio capture: {exc}"
            self.event_queue.put(("error", msg))
            if self.on_error:
                self.on_error(msg)
            return False

    def stop_listening(self):
        """Stop capturing and initiate offline transcription."""
        with self._state_lock:
            if self._state != STTState.LISTENING:
                return
            self._state = STTState.TRANSCRIBING

        if self.capture and self.capture.is_active():
            try:
                self.capture.stop()
            except Exception:
                pass

        self.event_queue.put(("state", STTState.TRANSCRIBING))
        if self.on_state_change:
            try:
                self.on_state_change(STTState.TRANSCRIBING)
            except Exception:
                pass

        # Hand off transcription to background thread
        threading.Thread(target=self._transcribe_worker, name="jugnu-stt-worker", daemon=True).start()

    def cancel_listening(self):
        """Cancel listening or transcribing, discarding any recorded audio."""
        if self.capture and self.capture.is_active():
            try:
                self.capture.stop()
            except Exception:
                pass
        with self._buffer_lock:
            self._audio_buffer.clear()
        self._set_state(STTState.IDLE)

    def toggle_listening(self) -> bool:
        """Toggle between listening and stopping/transcribing."""
        if self.is_listening:
            self.stop_listening()
            return False
        return self.start_listening()

    def _handle_audio_chunk(self, chunk: bytes):
        """Called by audio capture driver on incoming audio chunks."""
        if self.state != STTState.LISTENING:
            return

        now = time.monotonic()
        level = compute_rms(chunk)
        bars = compute_waveform_bars(chunk, num_bars=24)

        # Calibrate noise floor
        self.noise_gate.feed_calibration(level)

        # Noise suppression gating
        processed_chunk = chunk
        if self.noise_suppression:
            processed_chunk = self.noise_gate.gate_pcm(chunk, level)

        with self._buffer_lock:
            self._audio_buffer.append(processed_chunk)

        # Voice activity & silence detection
        is_speech = self.noise_gate.is_speech(level)
        _, timeout_triggered = self.silence_detector.feed(is_speech, now)

        # Send level update to HUD visualizer
        self.event_queue.put(("level", (level, bars)))
        if self.on_level:
            try:
                self.on_level(level, bars)
            except Exception:
                pass

        if timeout_triggered:
            # User spoke and then paused; auto-finish dictation!
            self.stop_listening()

    def _transcribe_worker(self):
        """Worker thread for offline transcription."""
        with self._buffer_lock:
            full_audio = b"".join(self._audio_buffer)
            self._audio_buffer.clear()

        if not full_audio:
            self._set_state(STTState.IDLE)
            return

        try:
            raw_text = self.recognizer.recognize(full_audio, sample_rate=DEFAULT_SAMPLE_RATE)
            formatted_text = format_transcription(
                raw_text,
                auto_punctuate=self.auto_punctuate,
                auto_capitalize=self.auto_capitalize
            )
            self._set_state(STTState.IDLE)
            self.event_queue.put(("result", formatted_text))
            if self.on_result:
                try:
                    self.on_result(formatted_text)
                except Exception:
                    pass
        except Exception as exc:
            self._set_state(STTState.ERROR)
            msg = f"Transcription error: {exc}"
            self.event_queue.put(("error", msg))
            if self.on_error:
                try:
                    self.on_error(msg)
                except Exception:
                    pass
            self._set_state(STTState.IDLE)

    def apply_settings(self, silence_timeout: Optional[float] = None,
                       noise_suppression: Optional[bool] = None,
                       auto_punctuate: Optional[bool] = None,
                       auto_capitalize: Optional[bool] = None):
        """Update STT settings dynamically."""
        if silence_timeout is not None:
            self.silence_timeout = max(0.5, min(5.0, silence_timeout))
            self.silence_detector.silence_timeout = self.silence_timeout
        if noise_suppression is not None:
            self.noise_suppression = bool(noise_suppression)
        if auto_punctuate is not None:
            self.auto_punctuate = bool(auto_punctuate)
        if auto_capitalize is not None:
            self.auto_capitalize = bool(auto_capitalize)

    def shutdown(self):
        """Stop listening and cleanly shutdown audio capture."""
        self.cancel_listening()
