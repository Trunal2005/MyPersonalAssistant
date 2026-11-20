"""Unit tests for arena.py: dual streaming worker, metrics evaluation, and session management."""
import time
from unittest.mock import patch
import pytest

from arena import ArenaMetric, ArenaSession, ArenaWorker


def test_arena_metric_defaults():
    metric = ArenaMetric(model="model-1")
    assert metric.model == "model-1"
    assert metric.ttft == 0.0
    assert metric.tps == 0.0
    assert metric.total_latency == 0.0
    assert metric.token_count == 0
    assert metric.error is None
    assert metric.status == "idle"


def test_arena_worker_streaming_success():
    fake_chunks = [
        {"delta": "Hello", "done": False},
        {"delta": " world", "done": False},
        {"delta": "!", "done": True, "eval_count": 3, "eval_duration": 150_000_000, "total_duration": 200_000_000},
    ]

    received_deltas = []
    finished_metrics = []

    def on_chunk(delta, m):
        received_deltas.append(delta)

    def on_finish(m, full_text):
        finished_metrics.append((m, full_text))

    with patch("arena.stream_chat", return_value=iter(fake_chunks)):
        worker = ArenaWorker(
            model="test-model",
            messages=[{"role": "user", "content": "hi"}],
            on_chunk=on_chunk,
            on_finish=on_finish,
        )
        worker.start()
        worker._thread.join(timeout=2.0)

    assert received_deltas == ["Hello", " world", "!"]
    assert len(finished_metrics) == 1
    m, full_text = finished_metrics[0]
    assert full_text == "Hello world!"
    assert m.status == "completed"
    assert m.token_count == 3
    assert m.ttft > 0.0
    assert m.tps > 0.0
    assert m.total_latency >= 0.0
    assert m.error is None


def test_arena_worker_error_resilience():
    fake_chunks = [
        {"delta": "Starting...", "done": False},
        {"error": "out_of_memory", "detail": "CUDA out of memory", "done": True},
    ]

    finished_metrics = []

    def on_finish(m, full_text):
        finished_metrics.append((m, full_text))

    with patch("arena.stream_chat", return_value=iter(fake_chunks)):
        worker = ArenaWorker(
            model="heavy-model",
            messages=[{"role": "user", "content": "hi"}],
            on_finish=on_finish,
        )
        worker.start()
        worker._thread.join(timeout=2.0)

    assert len(finished_metrics) == 1
    m, full_text = finished_metrics[0]
    assert m.status == "error"
    assert "CUDA out of memory" in m.error


def test_arena_session_dispatch_and_winner_selection():
    chunks_a = [
        {"delta": "Model A response", "done": True, "eval_count": 3, "eval_duration": 100_000_000},
    ]
    chunks_b = [
        {"delta": "Model B superior answer", "done": True, "eval_count": 4, "eval_duration": 100_000_000},
    ]

    def mock_stream(_messages, model=None, **_kwargs):
        if model == "model-a":
            return iter(chunks_a)
        return iter(chunks_b)

    completed = []

    session = ArenaSession(model_a="model-a", model_b="model-b")
    assert session.winner is None

    with patch("arena.stream_chat", side_effect=mock_stream):
        session.dispatch(
            prompt="Which model is better?",
            system_prompt="You are helpful.",
            on_complete=lambda: completed.append(True),
        )
        session.worker_a._thread.join(timeout=2.0)
        session.worker_b._thread.join(timeout=2.0)

    assert len(completed) == 1
    assert session.text_a == "Model A response"
    assert session.text_b == "Model B superior answer"

    # Select winner B
    win_b = session.select_winner("B")
    assert session.winner == "B"
    assert win_b["role"] == "assistant"
    assert win_b["content"] == "Model B superior answer"
    assert win_b["arena"]["model"] == "model-b"
    assert win_b["arena"]["tokens"] == 4

    # Select winner A
    win_a = session.select_winner("a")
    assert session.winner == "A"
    assert win_a["arena"]["model"] == "model-a"

    # Invalid choice raises
    with pytest.raises(ValueError):
        session.select_winner("C")


def test_arena_session_one_model_fails_other_succeeds():
    """Ensure that if Model B runs out of memory, Model A completes and can be chosen as winner."""
    chunks_a = [{"delta": "Reliable response", "done": True, "eval_count": 2, "eval_duration": 50_000_000}]
    chunks_b = [{"error": "out_of_memory", "detail": "VRAM allocation failed", "done": True}]

    def mock_stream(_messages, model=None, **_kwargs):
        if model == "good-model":
            return iter(chunks_a)
        return iter(chunks_b)

    completed = []
    session = ArenaSession(model_a="good-model", model_b="failing-model")

    with patch("arena.stream_chat", side_effect=mock_stream):
        session.dispatch(
            prompt="Test resilience",
            system_prompt="Test sys",
            on_complete=lambda: completed.append(True),
        )
        session.worker_a._thread.join(timeout=2.0)
        session.worker_b._thread.join(timeout=2.0)

    assert len(completed) == 1
    assert session.metrics_a.status == "completed"
    assert session.metrics_b.status == "error"
    assert "VRAM allocation failed" in session.metrics_b.error

    # Model A can still be selected as winner cleanly
    winner = session.select_winner("A")
    assert winner["content"] == "Reliable response"
    assert winner["arena"]["model"] == "good-model"
