"""Cancelar descargas: mata yt-dlp/ffmpeg al pulsar el botón."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pids: set[int] = set()


class JobCancelled(Exception):
    """El usuario pulsó Cancelar."""


def register_pid(pid: int | None) -> None:
    if pid and pid > 0:
        with _lock:
            _pids.add(int(pid))


def unregister_pid(pid: int | None) -> None:
    if pid:
        with _lock:
            _pids.discard(int(pid))


class TrackedPopen(subprocess.Popen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        register_pid(self.pid)

    def __del__(self):
        unregister_pid(self.pid)


def terminate_all(timeout: float = 0.5) -> None:
    with _lock:
        pids = list(_pids)
    if not pids:
        return
    logger.info("Cancelar: terminando %s subproceso(s)", len(pids))
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    time.sleep(timeout)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    with _lock:
        for pid in pids:
            _pids.discard(pid)


def check_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        terminate_all()
        raise JobCancelled()
