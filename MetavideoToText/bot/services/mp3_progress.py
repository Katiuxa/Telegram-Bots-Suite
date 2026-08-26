"""Etapas de progreso real para el flujo MP3 (descarga → conversión → envío)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from bot.i18n_progress import prog

# Rangos globales del flujo MP3 (0–100)
DOWNLOAD_LO, DOWNLOAD_HI = 5, 46
CONVERT_LO, CONVERT_HI = 46, 74
SEND_LO, SEND_HI = 74, 98

LINK_MP3_PROGRESS_KEY = "link_mp3_dl_progress"


def _lerp(lo: int, hi: int, inner_pct: int) -> int:
    p = max(0, min(100, int(inner_pct)))
    return lo + int((hi - lo) * p / 100)


def map_download_inner(inner_pct: int) -> int:
    """inner_pct 0–100 dentro de la fase descarga."""
    return _lerp(DOWNLOAD_LO, DOWNLOAD_HI, inner_pct)


def map_ytdlp_pct(pct: int) -> int:
    """Convierte % del hook yt-dlp (≈8–48) a etapa descarga MP3."""
    if pct <= 8:
        return DOWNLOAD_LO
    if pct >= 48:
        return DOWNLOAD_HI
    inner = int((pct - 8) / 40 * 100)
    return map_download_inner(inner)


def map_convert_inner(inner_pct: int) -> int:
    return _lerp(CONVERT_LO, CONVERT_HI, inner_pct)


def map_send_inner(inner_pct: int) -> int:
    return _lerp(SEND_LO, SEND_HI, inner_pct)


def store_link_mp3_progress(
    context: Any,
    pct: int,
    label: str,
    sub: str = "",
) -> None:
    context.user_data[LINK_MP3_PROGRESS_KEY] = {
        "pct": max(0, min(99, int(pct))),
        "label": label,
        "sub": sub,
        "ts": time.monotonic(),
    }


def pop_link_mp3_progress(context: Any) -> dict | None:
    raw = context.user_data.pop(LINK_MP3_PROGRESS_KEY, None)
    return raw if isinstance(raw, dict) else None


def get_link_mp3_progress(context: Any) -> dict | None:
    raw = context.user_data.get(LINK_MP3_PROGRESS_KEY)
    return raw if isinstance(raw, dict) else None


def make_mp3_download_callback(
    loop: Any,
    reporter: Any,
    cancel_event: Any = None,
    *,
    lang: str = "es",
    bg_context: Any = None,
) -> Any:
    """Callback hilo-seguro: descarga con % real mapeado a etapa MP3."""
    from bot.services.progress import thread_safe_callback

    base = thread_safe_callback(loop, reporter, cancel_event)

    def cb(pct: int, label: str, sub: str = "") -> None:
        mapped = map_ytdlp_pct(pct)
        dl_label = label or prog("downloading_audio_only", lang)
        if bg_context is not None:
            store_link_mp3_progress(bg_context, mapped, dl_label, sub)
        base(mapped, dl_label, sub)

    return cb


def make_mp3_convert_callback(
    loop: Any,
    reporter: Any,
    *,
    lang: str = "es",
) -> Any:
    """Callback para ffmpeg durante conversión a MP3."""

    def cb(inner_pct: int, sub: str = "") -> None:
        mapped = map_convert_inner(inner_pct)
        label = prog("creating_mp3", lang)
        detail = sub or (f"{inner_pct}%" if inner_pct > 0 else "")
        asyncio.run_coroutine_threadsafe(
            reporter.set_real(mapped, label, detail),
            loop,
        )

    return cb
