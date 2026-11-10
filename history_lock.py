"""Exclusive ownership of a chat history file across desktop processes."""

import errno
import os


class HistoryInUseError(OSError):
    """Another process owns this history file."""


class HistoryLock:
    def __init__(self, history_path):
        directory, filename = os.path.split(os.path.abspath(history_path))
        # Resolve directory aliases while keeping the destination stable across os.replace().
        self.path = os.path.join(os.path.realpath(directory), filename + ".lock")
        self._file = None

    def acquire(self):
        lock_file = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            lock_file.close()
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise HistoryInUseError(self.path) from error
            raise
        self._file = lock_file

    def release(self):
        if self._file is not None:
            # Keep the sidecar in place so all launches lock the same file.
            self._file.close()
            self._file = None
