"""Unit tests for the 100% Offline Local Speech-to-Text (STT) Engine."""
import struct
import time
import pytest

from stt import (
    STTManager, STTState,
    compute_rms, compute_waveform_bars,
    format_transcription,
    NoiseGate, SilenceDetector,
    MockAudioCapture, MockRecognizerBackend, FallbackRecognizerBackend,
    get_best_audio_capture, get_best_recognizer,
    DEFAULT_SAMPLE_RATE, DEFAULT_CHUNK_SIZE
)


# ---------------------------------------------------------------------------
# Audio DSP & Math Tests
# ---------------------------------------------------------------------------

def test_compute_rms_silence():
    # Pure zero PCM
    silence = b"\x00" * 2048
    assert compute_rms(silence) == 0.0


def test_compute_rms_empty_or_invalid():
    assert compute_rms(b"") == 0.0
    assert compute_rms(b"\x00") == 0.0  # Incomplete sample (< 2 bytes)


def test_compute_rms_full_scale():
    # Alternating maximum amplitude 16-bit PCM values (32767 and -32768)
    samples = [32767, -32767] * 512
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    rms = compute_rms(pcm)
    assert 0.99 <= rms <= 1.0


def test_compute_waveform_bars():
    # Empty bytes should return zero bars
    bars = compute_waveform_bars(b"", num_bars=24)
    assert len(bars) == 24
    assert all(b == 0.0 for b in bars)

    # 16-bit sine-like pulses
    samples = [int(16000 * ((i % 50) / 50.0)) for i in range(1024)]
    pcm = struct.pack(f"<{len(samples)}h", *samples)
    bars = compute_waveform_bars(pcm, num_bars=16)
    assert len(bars) == 16
    assert any(b > 0.0 for b in bars)
    assert all(0.0 <= b <= 1.0 for b in bars)


# ---------------------------------------------------------------------------
# Noise Gate & Silence Detection Tests
# ---------------------------------------------------------------------------

def test_noise_gate_calibration():
    gate = NoiseGate(initial_floor=0.01, margin=0.02)
    assert not gate.calibrated

    # Feed ambient noise chunks
    for _ in range(6):
        gate.feed_calibration(0.015)

    assert gate.calibrated
    assert gate.noise_floor > 0.01
    assert gate.is_speech(0.08)
    assert not gate.is_speech(0.015)


def test_noise_gate_pcm_suppression():
    gate = NoiseGate(initial_floor=0.03, margin=0.02)
    pcm = b"\x10\x00" * 100

    # Low level audio below floor should be zeroed out
    gated = gate.gate_pcm(pcm, level=0.02)
    assert gated == b"\x00" * len(pcm)

    # Audio above floor should be preserved
    preserved = gate.gate_pcm(pcm, level=0.06)
    assert preserved == pcm


def test_silence_detector_lifecycle():
    detector = SilenceDetector(silence_timeout=0.4, min_speech_duration=0.1)
    t = 1000.0

    # Initial silence
    active, timeout = detector.feed(False, t)
    assert not active and not timeout
    assert not detector.speech_detected

    # Short noise spike (< min_speech_duration)
    active, timeout = detector.feed(True, t + 0.05)
    assert active and not timeout
    assert not detector.speech_detected

    # Sustained speech (>= min_speech_duration)
    active, timeout = detector.feed(True, t + 0.15)
    assert active and not timeout
    assert detector.speech_detected

    # Pause begins
    active, timeout = detector.feed(False, t + 0.25)
    assert not active and not timeout

    # Pause reaches silence_timeout (0.4s since t + 0.15 -> t + 0.56)
    active, timeout = detector.feed(False, t + 0.56)
    assert not active
    assert timeout  # Silence timeout triggered!


def test_silence_detector_reset():
    detector = SilenceDetector(silence_timeout=0.3)
    detector.speech_detected = True
    detector.last_speech_time = 50.0
    detector.reset()
    assert not detector.speech_detected
    assert detector.speech_start_time is None
    assert detector.last_speech_time is None


# ---------------------------------------------------------------------------
# Auto-Punctuation & Text Formatting Tests
# ---------------------------------------------------------------------------

def test_format_transcription_empty():
    assert format_transcription("") == ""
    assert format_transcription("   ") == ""
    assert format_transcription(None) == ""


def test_format_transcription_spoken_punctuation():
    raw = "hello comma world period how are you question mark"
    formatted = format_transcription(raw)
    assert formatted == "Hello, world. How are you?"


def test_format_transcription_exclamation_and_newlines():
    raw = "great job exclamation mark next line let us continue"
    formatted = format_transcription(raw)
    assert formatted == "Great job!\nLet us continue."


def test_format_transcription_pronoun_i():
    raw = "what should i do because i am ready and i'll be there"
    formatted = format_transcription(raw)
    assert "What should I do" in formatted
    assert "I am ready" in formatted
    assert "I'll be there" in formatted


def test_format_transcription_spacing():
    raw = "testing , spacing .   multiple   spaces  colon here"
    formatted = format_transcription(raw)
    assert ", " in formatted
    assert "Testing, spacing." in formatted
    assert "Multiple spaces:" in formatted


def test_format_transcription_question_detection():
    # Question word starters should end with '?'
    assert format_transcription("what is the weather today") == "What is the weather today?"
    assert format_transcription("why did this happen") == "Why did this happen?"
    assert format_transcription("can you help me") == "Can you help me?"
    assert format_transcription("is this offline") == "Is this offline?"

    # Declarative sentences should end with '.'
    assert format_transcription("this is a local offline assistant") == "This is a local offline assistant."


# ---------------------------------------------------------------------------
# Audio Driver & Recognizer Backend Tests
# ---------------------------------------------------------------------------

def test_mock_audio_capture_streaming():
    chunks = []
    capture = MockAudioCapture(amplitude=0.25)
    assert capture.is_available()[0]
    assert "Mock Virtual Microphone" in capture.list_devices()

    capture.start(on_chunk=lambda c: chunks.append(c))
    assert capture.is_active()
    time.sleep(0.18)
    capture.stop()
    assert not capture.is_active()
    assert len(chunks) >= 2
    # Verify PCM bytes integrity
    assert all(len(c) == DEFAULT_CHUNK_SIZE * 2 for c in chunks)


def test_mock_recognizer_backend():
    rec = MockRecognizerBackend("Test transcription text")
    assert rec.is_available()[0]
    assert rec.recognize(b"\x01\x00" * 100) == "Test transcription text"
    assert rec.recognize(b"") == ""


def test_fallback_recognizer_backend():
    rec = FallbackRecognizerBackend("Model missing")
    ok, reason = rec.is_available()
    assert not ok
    assert "Model missing" in reason
    assert rec.recognize(b"\x01\x00" * 100) == ""


def test_get_best_recognizer_mock():
    rec = get_best_recognizer(prefer_mock=True, mock_text="Offline dictation works")
    assert rec.is_available()[0]
    assert rec.recognize(b"\x01\x00" * 100) == "Offline dictation works"


# ---------------------------------------------------------------------------
# STTManager Lifecycle & Handler Tests
# ---------------------------------------------------------------------------

def test_stt_manager_lifecycle():
    cap = MockAudioCapture(amplitude=0.3)
    rec = MockRecognizerBackend("hello comma this is jugnu question mark")
    manager = STTManager(capture=cap, recognizer=rec, auto_punctuate=True)

    assert manager.state == STTState.IDLE
    assert manager.available
    assert manager.has_mic
    assert manager.has_recognizer

    state_changes = []
    levels = []
    results = []

    manager.on_state_change = lambda s: state_changes.append(s)
    manager.on_level = lambda lvl, bars: levels.append(lvl)
    manager.on_result = lambda res: results.append(res)

    # Start listening
    started = manager.start_listening()
    assert started
    assert manager.is_listening

    time.sleep(0.15)
    assert len(levels) >= 2

    # Stop listening and transcribe
    manager.stop_listening()
    assert not manager.is_listening

    # Wait for background worker transcription to finish
    time.sleep(0.15)
    assert manager.state == STTState.IDLE
    assert "listening" in state_changes
    assert "transcribing" in state_changes
    assert len(results) == 1
    assert results[0] == "Hello, this is jugnu?"


def test_stt_manager_toggle_and_cancel():
    cap = MockAudioCapture(amplitude=0.2)
    rec = MockRecognizerBackend("Should not transcribe on cancel")
    manager = STTManager(capture=cap, recognizer=rec)

    # Toggle from idle to listening
    active = manager.toggle_listening()
    assert active
    assert manager.is_listening

    # Cancel listening
    manager.cancel_listening()
    assert manager.state == STTState.IDLE
    assert not manager.is_listening


def test_stt_manager_missing_mic_graceful():
    # Manager initialized with explicitly disabled audio capture device
    rec = MockRecognizerBackend("No mic")
    manager = STTManager(capture=False, recognizer=rec)

    assert not manager.has_mic
    assert not manager.available

    errors = []
    manager.on_error = lambda err: errors.append(err)

    started = manager.start_listening()
    assert not started
    assert manager.state == STTState.ERROR
    assert len(errors) == 1
    assert "microphone" in errors[0].lower()


def test_stt_manager_apply_settings():
    cap = MockAudioCapture()
    rec = MockRecognizerBackend()
    manager = STTManager(capture=cap, recognizer=rec, silence_timeout=1.5, noise_suppression=True)

    manager.apply_settings(silence_timeout=2.5, noise_suppression=False, auto_punctuate=False)
    assert manager.silence_timeout == 2.5
    assert not manager.noise_suppression
    assert not manager.auto_punctuate
    assert manager.silence_detector.silence_timeout == 2.5
