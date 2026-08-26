"""Trabajo en hilo secundario con cancelación (el event loop sigue libre)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import TypeVar

from bot.services.job_cancel import terminate_all
from bot.services.transcribe import JobCancelled

T = TypeVar("T")


async def run_killable(
    cancel_event: threading.Event | None,
    fn: Callable[..., T],
    /,
    *args,
    poll_sec: float = 0.25,
    **kwargs,
) -> T:
    if cancel_event is None:
        return await asyncio.to_thread(fn, *args, **kwargs)

    done = threading.Event()
    result: dict[str, object] = {"value": None, "err": None}

    def _worker() -> None:
        try:
            result["value"] = fn(*args, **kwargs)
        except BaseException as e:
            result["err"] = e
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()
    while not done.is_set():
        if cancel_event.is_set():
            terminate_all()
            raise JobCancelled()
        await asyncio.sleep(poll_sec)

    err = result["err"]
    if err is not None:
        if isinstance(err, JobCancelled):
            terminate_all()
        raise err
    if cancel_event.is_set():
        terminate_all()
        raise JobCancelled()
    return result["value"]  # type: ignore[return-value]
