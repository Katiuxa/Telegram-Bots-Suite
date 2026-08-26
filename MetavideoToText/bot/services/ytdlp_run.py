"""Ejecuta yt-dlp en subproceso (cancelable, con tiempo máximo)."""

from __future__ import annotations

import json
import logging
import queue
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable

from bot.config import (
    FAST_POLISH,
    ROOT,
    TEMP_DIR,
    YTDLP_CONCURRENT_FRAGMENTS,
    YTDLP_JOB_TIMEOUT_SEC,
    YTDLP_SOCKET_TIMEOUT,
)
from bot.i18n_progress import prog
from bot.services.job_cancel import TrackedPopen, terminate_all
from bot.services.progress import ProgressCallback, format_bytes, format_speed

logger = logging.getLogger(__name__)

_DL_PCT = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_DL_DONE = re.compile(r"\[download\]\s+100%")


def ytdlp_ejs_installed() -> bool:
    try:
        import importlib.metadata

        importlib.metadata.version("yt-dlp-ejs")
        return True
    except Exception:
        return False


def _append_extra_args(cmd: list[str], extra: dict) -> None:
    if path := extra.get("cookiefile"):
        cmd.extend(["--cookies", str(path)])
    if browser := extra.get("cookiesfrombrowser"):
        if isinstance(browser, (tuple, list)) and browser:
            cmd.extend(["--cookies-from-browser", str(browser[0])])
    ea = extra.get("extractor_args") or {}
    if isinstance(ea, dict):
        yt = ea.get("youtube")
        if isinstance(yt, dict):
            clients = yt.get("player_client")
            if clients:
                if isinstance(clients, str):
                    clients = [clients]
                cmd.extend(["--extractor-args", f"youtube:player_client={','.join(clients)}"])
        ig = ea.get("instagram")
        if isinstance(ig, dict):
            preload = ig.get("preload_features")
            if preload:
                cmd.extend(["--extractor-args", f"instagram:preload_features={preload}"])


def _parse_progress_line(
    line: str,
    callback: ProgressCallback | None,
    *,
    pct_start: int,
    pct_end: int,
    lang: str,
    progress_label: str | None = None,
) -> None:
    if not callback:
        return
    m = _DL_PCT.search(line)
    if not m:
        return
    inner = float(m.group(1)) / 100.0
    pct = pct_start + int(inner * (pct_end - pct_start))
    sub = prog("download_sub_partial", lang, done=f"{m.group(1)}%", speed="")
    label = progress_label or prog("downloading", lang)
    callback(pct, label, sub)


def youtube_download_timeout_sec(filesize: int, duration_sec: float) -> int:
    """Tiempo máximo según tamaño y duración (Pi + vídeos de horas)."""
    mb = filesize / (1024 * 1024) if filesize > 0 else 0.0
    if mb <= 0 and duration_sec > 0:
        mb = duration_sec * 128 / 8 / 1024
    by_size = int(mb * 12) + 900
    by_duration = int(duration_sec) + 900 if duration_sec > 0 else 0
    return max(YTDLP_JOB_TIMEOUT_SEC, by_size, by_duration)


def probe_youtube_metadata(
    url: str,
    fmt: str,
    extra: dict,
    *,
    lang: str = "es",
) -> dict:
    """Metadatos del formato elegido sin descargar (duración, tamaño, vcodec)."""
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "-J",
        "-f",
        fmt,
        "--skip-download",
    ]
    _append_extra_args(cmd, extra)
    cmd.append(url)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            cwd=str(ROOT),
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(prog("download_timeout", lang, sec=180)) from e
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err[:400] or prog("download_cli_failed", lang, code=proc.returncode))
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(proc.stdout[:200] or "metadata") from e


def run_ytdlp_cli(
    url: str,
    fmt: str,
    extra: dict,
    *,
    on_progress: ProgressCallback | None = None,
    cancel_event=None,
    timeout_sec: int | None = None,
    lang: str = "es",
    max_mb: int | None = None,
    progress_label: str | None = None,
) -> None:
    """Descarga con yt-dlp CLI; lanza RuntimeError si falla o expira."""
    from bot.services.transcribe import JobCancelled

    if not ytdlp_ejs_installed() and (
        "youtube.com" in url.lower() or "youtu.be" in url.lower()
    ):
        logger.warning("yt-dlp-ejs no instalado; YouTube puede fallar")

    timeout = timeout_sec or YTDLP_JOB_TIMEOUT_SEC
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--playlist-end",
        "1",
        "--newline",
        "--no-warnings",
        "--force-overwrites",
        "-f",
        fmt,
        "-o",
        str(TEMP_DIR / "%(id)s.%(ext)s"),
        f"--socket-timeout={YTDLP_SOCKET_TIMEOUT}",
    ]
    if max_mb and max_mb > 0:
        cmd.append(f"--max-filesize={max_mb}M")
    # Instagram DASH + concurrent-fragments falla a menudo en Pi (código 1 inmediato).
    url_l = url.lower()
    is_instagram = "instagram.com" in url_l or "instagr.am" in url_l
    if YTDLP_CONCURRENT_FRAGMENTS > 0 and not is_instagram:
        cmd.extend(
            [
                "--concurrent-fragments",
                str(YTDLP_CONCURRENT_FRAGMENTS),
                "--http-chunk-size",
                "1048576",
            ]
        )
    if FAST_POLISH:
        cmd.extend(["--retries", "2", "--fragment-retries", "3", "--extractor-retries", "2"])
    _append_extra_args(cmd, extra)
    # No --impersonate: en Pi curl_cffi suele estar "unsupported" y tumba
    # toda descarga de Instagram con código 1. yt-dlp ya funciona sin eso.
    cmd.append(url)

    logger.info("yt-dlp CLI: %s", " ".join(cmd[:12]) + " ...")

    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    start = time.monotonic()
    line_queue: queue.Queue[str | None] = queue.Queue()
    error_lines: list[str] = []
    recent_lines: list[str] = []

    def _enqueue_stdout() -> None:
        assert proc.stdout is not None
        for chunk in iter(proc.stdout.readline, ""):
            line_queue.put(chunk)
        line_queue.put(None)

    threading.Thread(target=_enqueue_stdout, daemon=True).start()
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                terminate_all()
                raise JobCancelled()
            if time.monotonic() - start > timeout:
                proc.kill()
                terminate_all()
                raise RuntimeError(prog("download_timeout", lang, sec=timeout))
            try:
                line = line_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if line is None:
                break
            stripped = line.strip()
            if stripped:
                recent_lines.append(stripped)
                if len(recent_lines) > 40:
                    del recent_lines[: len(recent_lines) - 40]
                if "ERROR:" in stripped or stripped.lower().startswith("error"):
                    error_lines.append(stripped)
            _parse_progress_line(
                line,
                on_progress,
                pct_start=8,
                pct_end=48,
                lang=lang,
                progress_label=progress_label,
            )
        rc = proc.wait(timeout=5)
    except JobCancelled:
        raise
    except Exception:
        proc.kill()
        terminate_all()
        raise
    if rc != 0:
        detail = error_lines[-1] if error_lines else ""
        if not detail and recent_lines:
            detail = " | ".join(recent_lines[-6:])
            logger.warning("yt-dlp salió %s sin ERROR: %s", rc, detail[:400])
        if detail:
            raise RuntimeError(detail[:500])
        raise RuntimeError(prog("download_cli_failed", lang, code=rc))


def run_ytdlp_cli_chain(
    url: str,
    formats: tuple[str, ...],
    extra: dict,
    **kwargs,
) -> None:
    last_err = ""
    for fmt in formats:
        try:
            run_ytdlp_cli(url, fmt, extra, **kwargs)
            return
        except Exception as e:
            last_err = str(e)
            low = last_err.lower()
            if "format is not available" in low or "requested format" in low:
                logger.info("Formato %s no disponible, siguiente", fmt)
                continue
            if "código -" in low or "code -" in low:
                logger.info("Descarga interrumpida con %s, reintento", fmt)
                try:
                    run_ytdlp_cli(url, fmt, extra, **kwargs)
                    return
                except Exception as retry_err:
                    last_err = str(retry_err)
                    low = last_err.lower()
                    if "format is not available" in low or "requested format" in low:
                        logger.info("Formato %s no disponible tras reintento", fmt)
                        continue
            raise
    if last_err:
        raise RuntimeError(last_err)
