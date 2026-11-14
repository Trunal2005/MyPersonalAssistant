import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from history_lock import HistoryLock


SOURCE = Path(__file__).resolve().parents[1]
LOCK_BUSY = 3


def run_child(history):
    code = """
import sys
from history_lock import HistoryInUseError, HistoryLock

lock = HistoryLock(sys.argv[1])
try:
    lock.acquire()
except HistoryInUseError:
    sys.exit(3)
lock.release()
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE)
    return subprocess.run(
        [sys.executable, "-B", "-c", code, str(history)],
        env=env, capture_output=True, text=True, timeout=10,
    )


def test_exclusive_access_and_independent_paths(tmp_path):
    history = tmp_path / "history.json"
    history.write_text('[{"title":"preserved"}]', encoding="utf-8")
    lock = HistoryLock(history)
    lock.acquire()
    try:
        assert run_child(history).returncode == LOCK_BUSY
        assert run_child(tmp_path / "other.json").returncode == 0
        assert history.read_text(encoding="utf-8") == '[{"title":"preserved"}]'
        replacement = tmp_path / "replacement.json"
        replacement.write_text("[]", encoding="utf-8")
        replacement.replace(history)
        assert run_child(history).returncode == LOCK_BUSY
    finally:
        lock.release()
    assert run_child(history).returncode == 0


def test_process_exit_releases_lock(tmp_path):
    history = tmp_path / "history.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE)
    ready = tmp_path / "ready"
    code = (
        "from history_lock import HistoryLock; from pathlib import Path; import sys; "
        "lock=HistoryLock(sys.argv[1]); lock.acquire(); "
        "Path(sys.argv[2]).touch(); sys.stdin.readline()"
    )
    with subprocess.Popen(
        [sys.executable, "-B", "-c", code, str(history), str(ready)],
        env=env, stdin=subprocess.PIPE,
    ) as proc:
        try:
            deadline = time.monotonic() + 10
            while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists(), "Child did not acquire the history lock"
            assert run_child(history).returncode == LOCK_BUSY
        finally:
            proc.kill()
            proc.wait(timeout=10)
    assert run_child(history).returncode == 0


def test_unwritable_lock_path_fails_without_touching_history(tmp_path):
    history = tmp_path / "missing" / "history.json"
    with pytest.raises(OSError):
        HistoryLock(history).acquire()
    assert not history.exists()


def test_second_desktop_launch_reports_conflict(tmp_path):
    lock = HistoryLock(tmp_path / "jugnu_history.json")
    lock.acquire()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE)
    env["QT_QPA_PLATFORM"] = "offscreen"
    code = """
import sys
from unittest.mock import patch

import desktop_app

with patch.object(desktop_app.QMessageBox, "critical") as critical, \\
        patch.object(desktop_app, "JugnuWindow") as window:
    assert desktop_app.main() == 1
    assert critical.call_args.args[1] == "Chat history in use"
    window.assert_not_called()
"""
    try:
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=tmp_path, env=env,
            capture_output=True, text=True, timeout=30,
        )
    finally:
        lock.release()
    assert result.returncode == 0, result.stderr


def test_failed_history_replace_preserves_existing_file(tmp_path, monkeypatch):
    import jugnu_core

    history = tmp_path / "history.json"
    original = '[{"title":"preserved"}]'
    history.write_text(original, encoding="utf-8")

    def fail_replace(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(jugnu_core.os, "replace", fail_replace)
    with pytest.raises(OSError):
        jugnu_core.save_history([], history)

    assert history.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [history]


def test_window_reports_a_failed_save_in_the_status_line(window, monkeypatch):
    import jugnu_core

    def fail_replace(*args):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(jugnu_core.os, "replace", fail_replace)
    window.chats = [{"id": "a", "title": "A", "messages": [{"role": "user", "content": "x"}]}]
    window.save_history()
    assert window._status[0] == "status_save_error"
