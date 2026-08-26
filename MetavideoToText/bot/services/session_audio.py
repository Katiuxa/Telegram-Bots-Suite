"""Exportar MP3 bajo demanda; enlace directo sin copiar archivos grandes."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Event

from telegram.ext import ContextTypes

from bot.config import FFMPEG_THREADS, TELEGRAM_AUDIO_MAX_MB, TEMP_DIR

logger = logging.getLogger(__name__)

_SESSION_MP3_KEY = "session_audio_mp3"
_SESSION_SOURCE_KEY = "session_audio_source"
_COPY_EXTS = frozenset({".webm", ".m4a", ".opus", ".mp3", ".ogg", ".wav", ".aac"})
_TELEGRAM_READY_EXTS = frozenset({".mp3", ".m4a", ".aac", ".ogg"})

ProgressCallback = Callable[[int, str], None]


def clear_session_audio(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (_SESSION_MP3_KEY, _SESSION_SOURCE_KEY):
        old = context.user_data.pop(key, None)
        if isinstance(old, str):
            _unlink(Path(old))


def get_session_mp3(context: ContextTypes.DEFAULT_TYPE) -> Path | None:
    raw = context.user_data.get(_SESSION_MP3_KEY)
    if isinstance(raw, str):
        path = Path(raw)
        if path.is_file():
            return path
    return None


def has_session_audio(context: ContextTypes.DEFAULT_TYPE) -> bool:
    if get_session_mp3(context):
        return True
    raw = context.user_data.get(_SESSION_SOURCE_KEY)
    return isinstance(raw, str) and Path(raw).is_file()


def _unlink(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError as e:
        logger.debug("No borré %s: %s", path, e)


def probe_audio_duration_sec(path: Path) -> float:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return max(0.0, float(proc.stdout.strip()))
    except (ValueError, subprocess.TimeoutExpired, OSError):
        pass
    return 0.0


def _target_bitrate_kbps(duration_sec: float, max_mb: int) -> int:
    if duration_sec <= 0:
        return 96
    budget_bits = max_mb * 1024 * 1024 * 8 * 0.92
    kbps = int(budget_bits / duration_sec / 1000)
    return max(16, min(128, kbps))


def _persist_path(source: Path, chat_id: int) -> Path | None:
    """Enlace duro (instantáneo) o copia mínima; evita duplicar 100+ MB en Pi."""
    if not source.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = TEMP_DIR / f"audio_{chat_id}_{stamp}{source.suffix.lower()}"
    try:
        os.link(source, out)
        return out
    except OSError:
        if source.stat().st_size <= 25 * 1024 * 1024:
            try:
                shutil.copy2(source, out)
                return out
            except OSError as e:
                logger.warning("Copia audio sesión: %s", e)
        return source


def store_session_audio_source(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    source_path: Path | None,
    wav_path: Path | None,
) -> Path | None:
    clear_session_audio(context)
    for p in (source_path, wav_path):
        if not p or not p.is_file():
            continue
        if p.suffix.lower() not in _COPY_EXTS:
            continue
        kept = _persist_path(p, chat_id)
        if kept:
            context.user_data[_SESSION_SOURCE_KEY] = str(kept)
            return kept
    return None


def _to_mp3(
    input_path: Path,
    output_path: Path,
    *,
    max_mb: int | None = None,
    fast_encode: bool = False,
    on_progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> None:
    from bot.services.job_cancel import TrackedPopen, check_cancelled
    from bot.services.transcribe import JobCancelled

    limit = max_mb or TELEGRAM_AUDIO_MAX_MB
    duration = probe_audio_duration_sec(input_path)
    size = input_path.stat().st_size
    if input_path.suffix.lower() == ".mp3" and size <= limit * 1024 * 1024:
        shutil.copy2(input_path, output_path)
        if on_progress:
            on_progress(100, "")
        return

    if fast_encode:
        from bot.config import MP3_FAST_ENCODE_KBPS

        kbps = max(64, min(192, MP3_FAST_ENCODE_KBPS))
    else:
        kbps = _target_bitrate_kbps(duration, limit)
    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        str(max(1, FFMPEG_THREADS)),
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "22050",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{kbps}k",
        "-compression_level",
        "0",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]
    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    last_pct = -1
    start = time.monotonic()
    timeout = max(1800.0, duration * 2.0 + 180.0) if duration > 0 else 1800.0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            check_cancelled(cancel_event)
            if time.monotonic() - start > timeout:
                proc.kill()
                raise RuntimeError("La conversión a MP3 tardó demasiado.")
            line = line.strip()
            if not on_progress or not duration or not line.startswith("out_time_ms="):
                continue
            try:
                ms = int(line.split("=", 1)[1])
            except ValueError:
                continue
            pct = min(99, int(100 * (ms / 1_000_000.0) / duration))
            if pct != last_pct:
                last_pct = pct
                on_progress(pct, f"{pct}%")
        check_cancelled(cancel_event)
        proc.wait(timeout=30)
    except JobCancelled:
        proc.kill()
        raise
    finally:
        from bot.services.job_cancel import unregister_pid

        unregister_pid(proc.pid)
    if proc.returncode != 0 or not output_path.is_file():
        raise RuntimeError("No se pudo crear el MP3.")
    if on_progress:
        on_progress(100, "")


def _mp3_encode_plan(source: Path) -> tuple[int, bool]:
    """max_mb para ffmpeg y si usar bitrate fijo (host externo)."""
    from bot.config import (
        EXTERNAL_UPLOAD_ENABLED,
        MAX_EXTERNAL_FILE_MB,
        MP3_FAST_ENCODE_KBPS,
        TELEGRAM_AUDIO_MAX_MB,
    )

    if not EXTERNAL_UPLOAD_ENABLED:
        return TELEGRAM_AUDIO_MAX_MB, False
    duration = probe_audio_duration_sec(source)
    if duration <= 0:
        return MAX_EXTERNAL_FILE_MB, False
    est_mb = (duration * MP3_FAST_ENCODE_KBPS * 1000) / (8 * 1024 * 1024)
    if est_mb > TELEGRAM_AUDIO_MAX_MB * 0.85:
        return MAX_EXTERNAL_FILE_MB, True
    return TELEGRAM_AUDIO_MAX_MB, False


def _to_mp3_quick(
    input_path: Path,
    output_path: Path,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> None:
    """Conversión ligera a MP3 (solo cuando cabe en Telegram)."""
    from bot.config import MP3_FAST_ENCODE_KBPS

    size = input_path.stat().st_size
    from bot.config import TELEGRAM_AUDIO_MAX_MB

    limit = TELEGRAM_AUDIO_MAX_MB * 1024 * 1024
    if input_path.suffix.lower() == ".mp3" and size <= limit:
        shutil.copy2(input_path, output_path)
        if on_progress:
            on_progress(100, "")
        return

    duration = probe_audio_duration_sec(input_path)
    kbps = max(96, min(192, MP3_FAST_ENCODE_KBPS))
    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        str(max(1, FFMPEG_THREADS)),
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        f"{kbps}k",
        "-compression_level",
        "0",
        "-progress",
        "pipe:1",
        "-nostats",
        str(output_path),
    ]
    from bot.services.job_cancel import TrackedPopen, check_cancelled
    from bot.services.transcribe import JobCancelled

    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    last_pct = -1
    start = time.monotonic()
    timeout = max(600.0, duration * 1.5 + 120.0) if duration > 0 else 600.0
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            check_cancelled(cancel_event)
            if time.monotonic() - start > timeout:
                proc.kill()
                raise RuntimeError("La conversión a MP3 tardó demasiado.")
            line = line.strip()
            if not on_progress or not duration or not line.startswith("out_time_ms="):
                continue
            try:
                ms = int(line.split("=", 1)[1])
            except ValueError:
                continue
            pct = min(99, int(100 * (ms / 1_000_000.0) / duration))
            if pct != last_pct:
                last_pct = pct
                on_progress(pct, f"{pct}%")
        check_cancelled(cancel_event)
        proc.wait(timeout=30)
    except JobCancelled:
        proc.kill()
        raise
    finally:
        from bot.services.job_cancel import unregister_pid

        unregister_pid(proc.pid)
    if proc.returncode != 0 or not output_path.is_file():
        raise RuntimeError("No se pudo crear el MP3.")
    if on_progress:
        on_progress(100, "")


def prepare_session_delivery(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> Path | None:
    """Prepara audio para envío: sin ffmpeg si ya sirve o va a host externo."""
    existing = get_session_mp3(context)
    if existing:
        return existing

    raw = context.user_data.get(_SESSION_SOURCE_KEY)
    if not isinstance(raw, str):
        return None
    source = Path(raw)
    if not source.is_file():
        return None

    from bot.config import EXTERNAL_UPLOAD_ENABLED, TELEGRAM_AUDIO_MAX_MB

    size = source.stat().st_size
    max_tg = TELEGRAM_AUDIO_MAX_MB * 1024 * 1024

    if EXTERNAL_UPLOAD_ENABLED and size > max_tg:
        context.user_data[_SESSION_MP3_KEY] = str(source)
        if on_progress:
            on_progress(100, "")
        return source

    if source.suffix.lower() in _TELEGRAM_READY_EXTS and size <= max_tg:
        context.user_data[_SESSION_MP3_KEY] = str(source)
        if on_progress:
            on_progress(100, "")
        return source

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = TEMP_DIR / f"audio_{chat_id}_{stamp}.mp3"
    try:
        _to_mp3_quick(
            source,
            out,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
        if out.is_file() and out.stat().st_size > 0:
            context.user_data[_SESSION_MP3_KEY] = str(out)
            return out
    except Exception as e:
        logger.warning("MP3 entrega rápida falló: %s", e)
        _unlink(out)
        raise
    return None


def ensure_session_mp3(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event: Event | None = None,
) -> Path | None:
    existing = get_session_mp3(context)
    if existing:
        return existing

    raw = context.user_data.get(_SESSION_SOURCE_KEY)
    if not isinstance(raw, str):
        return None
    source = Path(raw)
    if not source.is_file():
        return None

    duration = probe_audio_duration_sec(source)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = TEMP_DIR / f"audio_{chat_id}_{stamp}.mp3"
    max_mb, fast_encode = _mp3_encode_plan(source)

    try:
        _to_mp3(
            source,
            out,
            max_mb=max_mb,
            fast_encode=fast_encode,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
        if out.is_file() and out.stat().st_size > 0:
            context.user_data[_SESSION_MP3_KEY] = str(out)
            return out
    except Exception as e:
        logger.warning("MP3 bajo demanda falló: %s", e)
        _unlink(out)
        raise
    return None


def save_session_audio_mp3(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    source_path: Path | None,
    wav_path: Path | None,
) -> Path | None:
    store_session_audio_source(context, chat_id, source_path, wav_path)
    return ensure_session_mp3(context, chat_id)
