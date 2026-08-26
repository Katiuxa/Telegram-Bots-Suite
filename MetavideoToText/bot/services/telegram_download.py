"""Descarga con progreso real desde la API de archivos de Telegram."""

import threading
import time
from pathlib import Path

import httpx

from bot.i18n_progress import prog
from bot.services.progress import ProgressReporter, format_bytes, format_speed
from bot.services.transcribe import JobCancelled


def telegram_file_url(bot_token: str, file_path: str) -> str:
    """PTB puede devolver ruta relativa o URL completa."""
    path = (file_path or "").strip()
    if path.startswith(("http://", "https://")):
        return path
    return f"https://api.telegram.org/file/bot{bot_token}/{path.lstrip('/')}"


async def download_to_path(
    *,
    bot_token: str,
    file_path: str,
    dest: Path,
    file_size: int | None,
    progress: ProgressReporter,
    pct_start: int = 12,
    pct_end: int = 28,
    cancel_event: threading.Event | None = None,
    lang: str = "es",
) -> Path:
    url = telegram_file_url(bot_token, file_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    done = 0
    total = file_size or 0
    t0 = time.monotonic()
    last_speed_t = t0
    last_speed_done = 0
    speed = 0.0

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            if not total:
                cl = resp.headers.get("content-length")
                if cl and cl.isdigit():
                    total = int(cl)

            with dest.open("wb") as out:
                async for chunk in resp.aiter_bytes(chunk_size=256 * 1024):
                    if cancel_event and cancel_event.is_set():
                        from bot.services.job_cancel import terminate_all

                        terminate_all()
                        raise JobCancelled()
                    out.write(chunk)
                    done += len(chunk)
                    now = time.monotonic()
                    if now - last_speed_t >= 0.4:
                        speed = (done - last_speed_done) / max(now - last_speed_t, 0.001)
                        last_speed_t = now
                        last_speed_done = done

                    if total > 0:
                        inner = done / total
                        pct = pct_start + int(inner * (pct_end - pct_start))
                        sub = prog(
                            "download_sub_of",
                            lang,
                            done=format_bytes(done),
                            total=format_bytes(total),
                            speed=format_speed(speed),
                        )
                    else:
                        pct = pct_start
                        sub = prog(
                            "download_sub_partial",
                            lang,
                            done=format_bytes(done),
                            speed=format_speed(speed),
                        )
                    await progress.set_real(
                        pct, prog("downloading", lang), sub
                    )

    return dest
