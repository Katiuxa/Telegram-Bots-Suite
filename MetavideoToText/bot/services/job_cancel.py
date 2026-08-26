"""Registro de subprocesos para poder matarlos al pulsar Cancelar."""

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


def register_pid(pid: int | None) -> None:
    if pid and pid > 0:
        with _lock:
            _pids.add(int(pid))


def unregister_pid(pid: int | None) -> None:
    if pid:
        with _lock:
            _pids.discard(int(pid))


class TrackedPopen(subprocess.Popen):
    """Popen que se registra para terminate_all() al cancelar."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        register_pid(self.pid)

    def __del__(self):
        unregister_pid(self.pid)


def terminate_all(timeout: float = 0.4) -> None:
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
    from bot.services.transcribe import JobCancelled

    if cancel_event is not None and cancel_event.is_set():
        terminate_all()
        raise JobCancelled()
