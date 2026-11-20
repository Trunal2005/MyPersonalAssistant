"""Multi-Model Side-by-Side Arena Comparison Mode with Dual Streaming & Metric Evaluation.

Features:
- Concurrent prompt dispatching to two local models via asynchronous streaming workers.
- Real-time inference metric evaluation:
  * Time-to-First-Token (TTFT)
  * Tokens per second (TPS)
  * Total latency and token count
- Error resilience: isolated model execution ensuring one failing model does not crash the other.
- One-click winner selection adopting the preferred response into conversation history.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from core import stream_chat


@dataclass
class ArenaMetric:
    """Inference evaluation metrics for an arena model pane."""
    model: str
    ttft: float = 0.0
    tps: float = 0.0
    total_latency: float = 0.0
    token_count: int = 0
    error: Optional[str] = None
    status: str = "idle"  # "idle", "generating", "completed", "error"


class ArenaWorker:
    """Asynchronous worker for streaming model output and calculating inference metrics."""

    def __init__(self, model: str, messages: List[Dict[str, str]],
                 on_chunk: Optional[Callable[[str, ArenaMetric], None]] = None,
                 on_finish: Optional[Callable[[ArenaMetric, str], None]] = None):
        self.model = model
        self.messages = messages
        self.on_chunk = on_chunk
        self.on_finish = on_finish
        self.metrics = ArenaMetric(model=model, status="idle")
        self.full_text = ""
        self.is_cancelled = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancel(self):
        self.is_cancelled = True

    def _run(self):
        self.metrics.status = "generating"
        t_start = time.perf_counter()
        t_first = None
        tokens = 0

        try:
            for chunk in stream_chat(self.messages, model=self.model):
                if self.is_cancelled:
                    return

                if chunk.get("error"):
                    self.metrics.error = chunk.get("detail", chunk.get("error"))
                    self.metrics.status = "error"
                    break

                delta = chunk.get("delta", "")
                if delta:
                    if t_first is None:
                        t_first = time.perf_counter()
                        self.metrics.ttft = max(0.001, round(t_first - t_start, 3))

                    tokens += 1
                    self.full_text += delta
                    self.metrics.token_count = tokens

                    elapsed_gen = time.perf_counter() - t_first
                    if elapsed_gen > 0:
                        self.metrics.tps = round(tokens / elapsed_gen, 1)

                    if self.on_chunk:
                        self.on_chunk(delta, self.metrics)

                if chunk.get("done"):
                    # Use Ollama server-reported metrics if available
                    eval_count = chunk.get("eval_count")
                    eval_duration = chunk.get("eval_duration")
                    if eval_count and eval_duration and eval_duration > 0:
                        self.metrics.token_count = eval_count
                        self.metrics.tps = round(eval_count / (eval_duration / 1e9), 1)

                    if self.metrics.status != "error":
                        self.metrics.status = "completed"
                    break

        except Exception as ex:
            self.metrics.error = str(ex)
            self.metrics.status = "error"

        finally:
            t_end = time.perf_counter()
            self.metrics.total_latency = max(0.001, round(t_end - t_start, 3))
            if self.metrics.status != "error":
                self.metrics.status = "completed"
            if self.on_finish and not self.is_cancelled:
                self.on_finish(self.metrics, self.full_text)


class ArenaSession:
    """Manages concurrent dual-model dispatch and winner-selection state."""

    def __init__(self, model_a: str, model_b: str):
        self.model_a = model_a
        self.model_b = model_b
        self.worker_a: Optional[ArenaWorker] = None
        self.worker_b: Optional[ArenaWorker] = None
        self.text_a = ""
        self.text_b = ""
        self.metrics_a = ArenaMetric(model=model_a)
        self.metrics_b = ArenaMetric(model=model_b)
        self.prompt = ""
        self.winner: Optional[str] = None  # "A" or "B"

    def is_running(self) -> bool:
        return any(
            w is not None and w.metrics.status == "generating"
            for w in (self.worker_a, self.worker_b)
        )

    def dispatch(self, prompt: str, system_prompt: str,
                 on_chunk_a: Optional[Callable[[str, ArenaMetric], None]] = None,
                 on_chunk_b: Optional[Callable[[str, ArenaMetric], None]] = None,
                 on_complete: Optional[Callable[[], None]] = None):
        """Concurrently dispatch prompt to both models."""
        self.prompt = prompt
        self.winner = None
        self.text_a = ""
        self.text_b = ""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        completed = [0]
        lock = threading.Lock()

        def make_finish_handler(pane: str):
            def on_finish(m: ArenaMetric, full: str):
                if pane == "A":
                    self.text_a = full
                    self.metrics_a = m
                else:
                    self.text_b = full
                    self.metrics_b = m

                with lock:
                    completed[0] += 1
                    if completed[0] == 2 and on_complete:
                        on_complete()
            return on_finish

        self.worker_a = ArenaWorker(
            model=self.model_a,
            messages=messages,
            on_chunk=on_chunk_a,
            on_finish=make_finish_handler("A"),
        )
        self.worker_b = ArenaWorker(
            model=self.model_b,
            messages=messages,
            on_chunk=on_chunk_b,
            on_finish=make_finish_handler("B"),
        )

        self.worker_a.start()
        self.worker_b.start()

    def cancel(self):
        if self.worker_a:
            self.worker_a.cancel()
        if self.worker_b:
            self.worker_b.cancel()

    def select_winner(self, choice: str) -> Dict[str, any]:
        """Select preferred response and format as conversation assistant message."""
        choice = choice.upper()
        if choice not in ("A", "B"):
            raise ValueError(f"Invalid winner choice: {choice}. Must be 'A' or 'B'.")

        self.winner = choice
        is_a = choice == "A"
        winning_text = self.text_a if is_a else self.text_b
        winning_metric = self.metrics_a if is_a else self.metrics_b

        return {
            "role": "assistant",
            "content": winning_text,
            "arena": {
                "winner": choice,
                "model": winning_metric.model,
                "ttft": winning_metric.ttft,
                "tps": winning_metric.tps,
                "latency": winning_metric.total_latency,
                "tokens": winning_metric.token_count,
            },
        }
