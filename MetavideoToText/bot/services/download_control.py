"""Cancelación de descargas y trabajos pesados."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from bot.i18n_progress import prog
from bot.services.job_cancel import terminate_all
from bot.services.progress import ProgressCallback
from bot.services.transcribe import JobCancelled

logger = logging.getLogger(__name__)


def download_from_link_killable(
    url: str,
    on_progress: ProgressCallback | None,
    cancel_event: threading.Event | None,
    lang: str = "es",
    *,
    for_telegram: bool = False,
    audio_only: bool = False,
) -> tuple[Path, dict[str, str]]:
    from bot.services.media import download_from_link

    if cancel_event is None:
        path, meta = download_from_link(
            url,
            on_progress,
            None,
            lang,
            for_telegram=for_telegram,
            audio_only=audio_only,
        )
        return Path(path), meta

    result: dict = {"path": None, "meta": {}, "err": None}
    done = threading.Event()

    def _worker() -> None:
        try:
            path, meta = download_from_link(
                url,
                on_progress,
                cancel_event,
                lang,
                for_telegram=for_telegram,
                audio_only=audio_only,
            )
            result["path"] = path
            result["meta"] = meta
        except Exception as e:
            result["err"] = e
        finally:
            done.set()

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    try:
        while not done.wait(timeout=0.2):
            if cancel_event.is_set():
                terminate_all()
                raise JobCancelled()
    except JobCancelled:
        terminate_all()
        raise

    if cancel_event.is_set():
        terminate_all()
        raise JobCancelled()

    if result["err"] is not None:
        err = result["err"]
        if isinstance(err, JobCancelled):
            terminate_all()
            raise err
        if "cancelad" in str(err).lower() or "cancel" in str(err).lower():
            raise JobCancelled() from err
        raise err
    if result["path"] is None:
        raise RuntimeError(prog("download_unknown_error", lang))
    return Path(result["path"]), result.get("meta") or {}
