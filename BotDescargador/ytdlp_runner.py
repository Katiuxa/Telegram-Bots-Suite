"""Ejecuta yt-dlp en subproceso con progreso, cancelación y YouTube optimizado."""

from __future__ import annotations

import json
import logging
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event

from job_control import JobCancelled, TrackedPopen, check_cancelled, terminate_all

logger = logging.getLogger(__name__)

_DL_PCT = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
ProgressFn = Callable[[int, str], None]

PLATFORM_LABEL = {
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Reels",
    "twitter": "X",
    "facebook": "Facebook",
    "other": "enlace",
}

FAST_PLATFORMS = frozenset({"tiktok", "instagram", "twitter", "facebook", "other"})
COOKIE_PLATFORMS = frozenset({"youtube", "instagram", "twitter", "facebook"})
# YouTube >15 min: un solo paso ffmpeg (no bajar 300 MB y recomprimir)
YOUTUBE_FFMPEG_PASS_SEC = 900


def platform_label(platform: str) -> str:
    return PLATFORM_LABEL.get(platform, "enlace")


def is_fast_platform(platform: str) -> bool:
    return platform in FAST_PLATFORMS


def ejs_installed() -> bool:
    try:
        import importlib.metadata

        importlib.metadata.version("yt-dlp-ejs")
        return True
    except Exception:
        return False


def needs_metadata_probe(platform: str) -> bool:
    return platform == "youtube"


def _ytdlp_cookies_copy(cookies: Path | None) -> Path | None:
    """Copia cookies a un temp único (yt-dlp reescribe el archivo y puede borrar sessionid)."""
    if not cookies or not cookies.is_file():
        return None
    dest_dir = cookies.parent / "temp"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f".ytdlp_cookies_{time.time_ns()}_{threading.get_ident()}.txt"
    shutil.copy2(cookies, dest)
    return dest


def _is_private_content_error(msg: str) -> bool:
    low = msg.lower()
    return any(
        k in low
        for k in (
            "private",
            "privado",
            "not available",
            "followers",
            "members only",
            "locked",
            "restricted",
        )
    )


def _needs_session_cookies(msg: str) -> bool:
    """Cookies solo para redes sociales restringidas (no YouTube 403)."""
    if _is_youtube_retryable_error(msg):
        return False
    if _is_private_content_error(msg):
        return True
    low = msg.lower()
    return any(
        k in low
        for k in (
            "empty media",
            "login",
            "log in",
            "sign in",
            "authentication",
            "sesión",
            "session",
            "bloqueó",
            "blocked",
            "401",
        )
    )


def _is_youtube_retryable_error(msg: str) -> bool:
    low = msg.lower()
    return any(
        k in low
        for k in (
            "403",
            "forbidden",
            "unable to download video data",
            "sign in",
            "bot",
            "not available",
            "requested format",
            "http error",
            "sabr",
            "drm",
            "n challenge",
            "missing a url",
        )
    )


def _youtube_player_clients() -> list[list[str]]:
    return [
        ["tv_embedded"],
        ["android_vr", "web_safari"],
        ["web_embedded"],
        ["mweb"],
        ["ios"],
    ]


def _instagram_error_message(detail: str) -> str:
    low = (detail or "").lower()
    if _is_private_content_error(detail):
        return (
            "Este Reel es de una cuenta privada o restringida.\n\n"
            "Necesitas cookies.txt con sesión iniciada en Instagram."
        )
    if any(
        k in low
        for k in (
            "login_required",
            "logged out",
            "logueado",
            "sesión",
            "session",
            "empty media",
            "401",
            "403",
            "bloqueó",
            "actualiza cookies",
        )
    ):
        return (
            "Instagram ha cerrado la sesión de cookies.txt.\n\n"
            "1. Entra en instagram.com en el navegador\n"
            "2. Exporta cookies.txt (extensión Get cookies.txt LOCALLY)\n"
            "3. Envíalo a este bot como archivo, o ejecuta COPIAR_COOKIES_PI.cmd"
        )
    return (
        "No pude descargar este Reel.\n\n"
        "Prueba otro enlace o actualiza cookies.txt.\n\n"
        f"{detail[:200]}"
    )


def _append_cookies(cmd: list[str], cookies: Path | None, platform: str) -> None:
    if cookies and cookies.is_file() and platform in COOKIE_PLATFORMS:
        cmd.extend(["--cookies", str(cookies)])


def _append_youtube_args(
    cmd: list[str],
    cookies: Path | None,
    *,
    clients: list[str] | None = None,
) -> None:
    cl = clients or ["tv_embedded", "android_vr", "web_safari"]
    cmd.extend(["--extractor-args", f"youtube:player_client={','.join(cl)}"])
    cmd.append("--force-ipv4")
    _append_cookies(cmd, _ytdlp_cookies_copy(cookies), "youtube")


def _append_platform_args(
    cmd: list[str],
    platform: str,
    cookies: Path | None,
    *,
    youtube_clients: list[str] | None = None,
    instagram_impersonate: bool = False,
) -> None:
    if platform == "youtube":
        _append_youtube_args(cmd, cookies, clients=youtube_clients)
    elif platform == "instagram":
        cmd.extend(["--extractor-args", "instagram:preload_features=boxes"])
        _append_cookies(cmd, cookies, platform)
        if instagram_impersonate:
            cmd.extend(["--impersonate", "Chrome-131:Android-14"])
    elif platform in ("twitter", "facebook"):
        _append_cookies(cmd, cookies, platform)


def _run_cmd(
    cmd: list[str],
    *,
    cancel_event: Event | None,
    timeout_sec: int,
    on_line: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess | None:
    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    start = time.monotonic()
    assert proc.stdout is not None
    lines: list[str] = []
    try:
        for line in proc.stdout:
            check_cancelled(cancel_event)
            if time.monotonic() - start > timeout_sec:
                proc.kill()
                terminate_all()
                raise RuntimeError(f"Tiempo agotado ({timeout_sec // 60} min).")
            lines.append(line)
            if on_line:
                on_line(line)
        check_cancelled(cancel_event)
        proc.wait(timeout=30)
    except JobCancelled:
        proc.kill()
        terminate_all()
        raise
    finally:
        from job_control import unregister_pid

        unregister_pid(proc.pid)
    return subprocess.CompletedProcess(cmd, proc.returncode or 0, "".join(lines), "")


def _parse_duration_value(raw: str) -> float:
    raw = (raw or "").strip().splitlines()[-1].strip()
    if not raw or raw.lower() in ("na", "none", "null"):
        return 0.0
    try:
        val = float(raw)
    except ValueError:
        return 0.0
    return val if val > 0 else 0.0


def _probe_youtube_duration_json(
    url: str,
    *,
    socket_timeout: int,
    cancel_event: Event | None,
    timeout_sec: int = 180,
) -> float:
    """Metadatos JSON (más fiable en vídeos muy largos)."""
    last_err = ""
    for clients in _youtube_player_clients():
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-warnings",
            "-J",
            "--skip-download",
            f"--socket-timeout={socket_timeout}",
        ]
        _append_youtube_args(cmd, None, clients=clients)
        cmd.append(url)
        result = _run_cmd(cmd, cancel_event=cancel_event, timeout_sec=timeout_sec)
        if result and result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                last_err = result.stdout[:200]
                continue
            if entries := data.get("entries"):
                data = entries[0] if entries else data
            val = float(data.get("duration") or 0)
            if val > 0:
                return val
        last_err = (result.stdout if result else "").strip()
        if not _is_youtube_retryable_error(last_err):
            break
    return 0.0


def probe_youtube_duration(
    url: str,
    *,
    cookies: Path | None,
    socket_timeout: int,
    cancel_event: Event | None = None,
    timeout_sec: int = 40,
) -> float:
    """Duración del vídeo; JSON si --print devuelve un valor sospechoso."""
    if not ejs_installed():
        raise RuntimeError("Falta yt-dlp-ejs. Ejecuta ACTUALIZAR_PI.cmd.")
    last_err = ""
    best = 0.0
    for clients in _youtube_player_clients():
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-warnings",
            "--print",
            "duration",
            "--skip-download",
            f"--socket-timeout={min(socket_timeout, 30)}",
        ]
        _append_youtube_args(cmd, None, clients=clients)
        cmd.append(url)
        result = _run_cmd(cmd, cancel_event=cancel_event, timeout_sec=timeout_sec)
        if result and result.returncode == 0:
            val = _parse_duration_value(result.stdout)
            if val >= 120:
                return val
            if val > best:
                best = val
        else:
            last_err = (result.stdout if result else "").strip()
            if not _is_youtube_retryable_error(last_err):
                break

    json_dur = _probe_youtube_duration_json(
        url, socket_timeout=socket_timeout, cancel_event=cancel_event
    )
    if json_dur >= 120:
        return json_dur
    if json_dur > best:
        best = json_dur
    if best > 0:
        return best

    from instagram_fallback import resolve_cookies_file

    retry_cookies = resolve_cookies_file(Path(__file__).resolve().parent)
    if retry_cookies and retry_cookies.is_file():
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-warnings",
            "-J",
            "--skip-download",
            f"--socket-timeout={socket_timeout}",
        ]
        _append_youtube_args(cmd, retry_cookies, clients=["tv_embedded"])
        cmd.append(url)
        result = _run_cmd(cmd, cancel_event=cancel_event, timeout_sec=180)
        if result and result.returncode == 0 and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                if entries := data.get("entries"):
                    data = entries[0] if entries else data
                val = float(data.get("duration") or 0)
                if val > 0:
                    return val
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        last_err = (result.stdout if result else "").strip() or last_err
    raise RuntimeError(last_err[:400] or "No pude leer la duración de YouTube.")


def download_timeout_sec(
    duration_sec: float,
    filesize: int = 0,
    *,
    platform: str = "other",
) -> int:
    if platform in FAST_PLATFORMS and platform != "other":
        return 900
    if duration_sec <= 0:
        return 900 if platform != "youtube" else 2400
    if duration_sec <= 180:
        return max(600, int(duration_sec * 8) + 180)
    if duration_sec <= YOUTUBE_FFMPEG_PASS_SEC:
        return max(1200, int(duration_sec * 6) + 300)
    mb = filesize / (1024 * 1024) if filesize > 0 else duration_sec * 300 / 8 / 1024
    by_size = int(mb * 12) + 600
    by_duration = int(duration_sec * 0.8) + 600
    return max(2400, by_size, by_duration)


def _fast_video_format_chain() -> tuple[str, ...]:
    # TikTok/Reels: HEVC (bytevc1) a veces devuelve 404; priorizar H.264.
    h264_mux = (
        "best[vcodec^=avc]/best[vcodec^=h264]/"
        "best[ext=mp4]/best[acodec!=none]/best"
    )
    return (h264_mux, "best[ext=mp4]/best", "best")


def _is_fast_format_retryable_error(msg: str) -> bool:
    low = msg.lower()
    return any(
        k in low
        for k in (
            "404",
            "unable to download video data",
            "format is not available",
            "requested format",
        )
    )


def format_for_platform(platform: str, duration_sec: float, max_mb: int) -> str:
    if is_fast_platform(platform):
        return _fast_video_format_chain()[0]
    if duration_sec > 3600:
        h = 240
    elif duration_sec > 1800:
        h = 360
    elif duration_sec > 600:
        h = 480
    else:
        h = 720
    return (
        f"bestvideo[height<={h}][vcodec!=none][ext!=mhtml]+bestaudio/"
        f"best[height<={h}][ext=mp4][vcodec!=none]/"
        f"best[height<={h}][vcodec!=none]/"
        f"best[vcodec!=none][ext!=mhtml]/"
        f"best[filesize<{max_mb * 2}M]/best"
    )


def youtube_stream_format(duration_sec: float) -> str:
    if duration_sec > 3600:
        h = 240
    elif duration_sec > 1800:
        h = 360
    else:
        h = 480
    return (
        f"bestvideo[height<={h}][vcodec!=none][ext!=mhtml]+bestaudio/"
        f"best[height<={h}][ext=mp4][vcodec!=none]/"
        f"best[height<={h}][vcodec!=none]/"
        f"best[vcodec!=none][ext!=mhtml]/best"
    )


def _telegram_video_kbps(duration_sec: float, max_mb: int = 48) -> int:
    if duration_sec <= 0:
        return 400
    budget = max_mb * 1024 * 8 * 0.88 / duration_sec
    return max(48, min(900, int(budget - 64)))


def _get_stream_urls(
    url: str,
    fmt: str,
    cookies: Path | None,
    socket_timeout: int,
    cancel_event: Event | None,
) -> list[str]:
    last_err = ""
    for clients in _youtube_player_clients():
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--no-warnings",
            "-g",
            "-f",
            fmt,
            f"--socket-timeout={socket_timeout}",
        ]
        _append_youtube_args(cmd, cookies, clients=clients)
        cmd.append(url)
        result = _run_cmd(cmd, cancel_event=cancel_event, timeout_sec=120)
        if result and result.returncode == 0:
            urls = [
                ln.strip()
                for ln in result.stdout.splitlines()
                if ln.strip().startswith("http")
            ]
            if urls:
                return urls
        last_err = (result.stdout if result else "").strip()
        if not _is_youtube_retryable_error(last_err):
            break
    raise RuntimeError(last_err[:300] or "No pude obtener el vídeo de YouTube.")


def run_youtube_ffmpeg_pass(
    url: str,
    out_dir: Path,
    *,
    duration_sec: float,
    cookies: Path | None,
    socket_timeout: int,
    cancel_event: Event | None = None,
    on_progress: ProgressFn | None = None,
    timeout_sec: int | None = None,
    max_mb: int = 48,
) -> Path:
    """Un solo paso: streams → MP4 listo para Telegram (vídeos largos)."""
    if not shutil_which("ffmpeg"):
        raise RuntimeError("Falta FFmpeg en la Pi.")

    fmt = youtube_stream_format(duration_sec)
    urls = _get_stream_urls(url, fmt, cookies, socket_timeout, cancel_event)
    out = out_dir / f"yt_{int(time.time())}.mp4"
    height = 240 if duration_sec > 3600 else (360 if duration_sec > 1800 else 480)
    vkbps = _telegram_video_kbps(duration_sec, max_mb)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-threads", "2"]
    for u in urls:
        cmd.extend(["-i", u])
    if len(urls) > 1:
        cmd.extend(["-map", "0:v:0?", "-map", "1:a:0?"])
    cmd.extend(
        [
            "-vf",
            f"scale=-2:'min({height},ih)'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            f"{vkbps}k",
            "-maxrate",
            f"{int(vkbps * 1.15)}k",
            "-bufsize",
            f"{int(vkbps * 2)}k",
            "-c:a",
            "aac",
            "-b:a",
            "64k",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(out),
        ]
    )

    timeout = timeout_sec or download_timeout_sec(duration_sec, platform="youtube")
    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    start = time.monotonic()
    last_pct = -1
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            check_cancelled(cancel_event)
            if time.monotonic() - start > timeout:
                proc.kill()
                terminate_all()
                raise RuntimeError("Conversión YouTube tardó demasiado.")
            line = line.strip()
            if on_progress and duration_sec > 0 and line.startswith("out_time_ms="):
                try:
                    ms = int(line.split("=", 1)[1])
                    pct = min(99, int(100 * (ms / 1_000_000.0) / duration_sec))
                    if pct != last_pct:
                        last_pct = pct
                        on_progress(pct, f"{pct}%")
                except ValueError:
                    pass
        check_cancelled(cancel_event)
        proc.wait(timeout=60)
    except JobCancelled:
        proc.kill()
        terminate_all()
        raise
    finally:
        from job_control import unregister_pid

        unregister_pid(proc.pid)

    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError("No pude preparar el vídeo de YouTube.")
    if on_progress:
        on_progress(100, "Listo")
    return out


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _build_ytdlp_cmd(
    url: str,
    out_dir: Path,
    *,
    platform: str,
    fmt: str,
    fast: bool,
    socket_timeout: int,
    cookies: Path | None,
    youtube_clients: list[str] | None = None,
    instagram_impersonate: bool = False,
) -> list[str]:
    ytdlp_cookies = _ytdlp_cookies_copy(cookies)
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--newline",
        "--no-warnings",
        "-f",
        fmt,
        "-o",
        str(out_dir / "%(id)s.%(ext)s"),
        f"--socket-timeout={min(socket_timeout, 25) if fast else socket_timeout}",
        "--retries",
        "2" if fast else "4",
        "--fragment-retries",
        "3" if fast else "8",
    ]
    if fast:
        cmd.append("--no-part")
    else:
        cmd.extend(["--merge-output-format", "mp4"])
        cmd.extend(["--concurrent-fragments", "3", "--http-chunk-size", "1048576"])
    _append_platform_args(
        cmd,
        platform,
        ytdlp_cookies,
        youtube_clients=youtube_clients,
        instagram_impersonate=instagram_impersonate,
    )
    cmd.append(url)
    return cmd


def _run_ytdlp_cmd(
    cmd: list[str],
    *,
    fast: bool,
    timeout: int,
    cancel_event: Event | None,
    on_progress: ProgressFn | None,
) -> tuple[int, list[str]]:
    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    start = time.monotonic()
    last_pct = -1
    error_lines: list[str] = []
    assert proc.stdout is not None
    try:
        if fast:
            for line in proc.stdout:
                check_cancelled(cancel_event)
                if time.monotonic() - start > timeout:
                    proc.kill()
                    terminate_all()
                    raise RuntimeError(
                        f"Descarga cancelada por tiempo ({timeout // 60} min)."
                    )
                stripped = line.strip()
                if stripped and "ERROR:" in stripped:
                    error_lines.append(stripped)
                m = _DL_PCT.search(line)
                if m and on_progress:
                    pct = int(float(m.group(1)))
                    if pct != last_pct:
                        last_pct = pct
                        on_progress(pct, f"{pct}%")
        else:
            line_queue: queue.Queue[str | None] = queue.Queue()

            def _reader() -> None:
                for ln in iter(proc.stdout.readline, ""):
                    line_queue.put(ln)
                line_queue.put(None)

            threading.Thread(target=_reader, daemon=True).start()
            while True:
                check_cancelled(cancel_event)
                if time.monotonic() - start > timeout:
                    proc.kill()
                    terminate_all()
                    raise RuntimeError(
                        f"Descarga cancelada por tiempo ({timeout // 60} min)."
                    )
                try:
                    line = line_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if line is None:
                    break
                stripped = line.strip()
                if stripped and "ERROR:" in stripped:
                    error_lines.append(stripped)
                m = _DL_PCT.search(line)
                if m and on_progress:
                    pct = int(float(m.group(1)))
                    if pct != last_pct:
                        last_pct = pct
                        on_progress(pct, f"{pct}%")
        check_cancelled(cancel_event)
        rc = proc.wait(timeout=30)
    except JobCancelled:
        proc.kill()
        terminate_all()
        raise
    finally:
        from job_control import unregister_pid

        unregister_pid(proc.pid)
    return rc, error_lines


def run_download(
    url: str,
    out_dir: Path,
    *,
    platform: str,
    duration_sec: float,
    cookies: Path | None,
    socket_timeout: int,
    cancel_event: Event | None = None,
    on_progress: ProgressFn | None = None,
    timeout_sec: int | None = None,
    max_mb: int = 48,
) -> Path:
    if platform == "youtube" and duration_sec > YOUTUBE_FFMPEG_PASS_SEC:
        try:
            return run_youtube_ffmpeg_pass(
                url,
                out_dir,
                duration_sec=duration_sec,
                cookies=None,
                socket_timeout=socket_timeout,
                cancel_event=cancel_event,
                on_progress=on_progress,
                timeout_sec=timeout_sec,
                max_mb=max_mb,
            )
        except RuntimeError as ffmpeg_err:
            logger.warning("YouTube ffmpeg pass: %s — pruebo yt-dlp", ffmpeg_err)

    timeout = timeout_sec or download_timeout_sec(duration_sec, platform=platform)
    fast = is_fast_platform(platform)
    fmt_chain = (
        _fast_video_format_chain()
        if fast
        else (format_for_platform(platform, duration_sec, max_mb),)
    )

    from instagram_fallback import resolve_cookies_file

    root = Path(__file__).resolve().parent
    attempts: list[tuple[Path | None, list[str] | None, bool]] = []

    if platform == "youtube":
        for clients in _youtube_player_clients():
            attempts.append((None, clients, False))
        cookies_file = resolve_cookies_file(root)
        if cookies_file and cookies_file.is_file():
            attempts.append((cookies_file, ["tv_embedded"], False))
    elif platform == "instagram":
        # Sin cookies de cuenta (evitar flags de automatización Instagram).
        attempts.append((None, None, True))
        attempts.append((None, None, False))
    else:
        attempts.append((None, None, False))
        cookies_file = resolve_cookies_file(root)
        if cookies_file and cookies_file.is_file():
            attempts.append((cookies_file, None, False))

    rc = 1
    error_lines: list[str] = []
    detail = ""
    tried_cookies = False
    social_cookie_pass = False

    for fmt in fmt_chain:
        for cookies_path, yt_clients, ig_imp in attempts:
            if platform != "youtube" and cookies_path and social_cookie_pass:
                continue
            if platform == "instagram" and cookies_path:
                # Instagram: permitir cookies desde el primer intento si hay sessionid.
                if (
                    not social_cookie_pass
                    and detail
                    and not _needs_session_cookies(detail)
                    and "sessionid"
                    not in cookies_path.read_text(encoding="utf-8", errors="replace")
                ):
                    continue
                tried_cookies = True
            if platform not in ("youtube", "instagram") and cookies_path:
                if not _needs_session_cookies(detail):
                    continue
                tried_cookies = True
            if platform == "youtube" and cookies_path:
                tried_cookies = True
            if platform != "youtube" and cookies_path:
                social_cookie_pass = True

            cmd = _build_ytdlp_cmd(
                url,
                out_dir,
                platform=platform,
                fmt=fmt,
                fast=fast,
                socket_timeout=socket_timeout,
                cookies=cookies_path,
                youtube_clients=yt_clients,
                instagram_impersonate=ig_imp,
            )
            logger.info("yt-dlp [%s]: %s", platform, " ".join(cmd[:16]))
            rc, error_lines = _run_ytdlp_cmd(
                cmd,
                fast=fast,
                timeout=timeout,
                cancel_event=cancel_event,
                on_progress=on_progress,
            )
            detail = error_lines[-1] if error_lines else ""
            if rc == 0:
                break
            # empty media / login: no tiene sentido rotar formatos H.264
            if platform == "instagram" and _needs_session_cookies(detail):
                logger.info("Reintentando %s (cliente/cookies distintos)", platform)
                continue
            if fast and _is_fast_format_retryable_error(detail):
                logger.info("Reintentando %s (formato distinto)", platform)
                break
            if platform == "youtube" and not _is_youtube_retryable_error(detail):
                break
            if platform == "instagram" and not ig_imp and not _needs_session_cookies(detail):
                break
            if platform not in ("youtube", "instagram") and not _needs_session_cookies(detail):
                break
            logger.info("Reintentando %s (cliente/cookies distintos)", platform)
        if rc == 0:
            break
        if platform == "instagram" and _needs_session_cookies(detail):
            break
        if not (fast and _is_fast_format_retryable_error(detail)):
            break

    check_cancelled(cancel_event)
    if rc != 0:
        if platform == "instagram":
            from instagram_fallback import download_reel

            try:
                return download_reel(
                    url,
                    out_dir,
                    cookies=resolve_cookies_file(root),
                )
            except Exception as fb_err:
                detail = str(fb_err) or detail
                logger.info("Instagram fallback: %s", detail[:200])
            raise RuntimeError(_instagram_error_message(detail)) from None
        if platform == "youtube":
            raise RuntimeError(
                f"No pude descargar YouTube.\n\n{detail[:300]}"
            ) from None
        label = platform_label(platform)
        hint = ""
        if platform == "facebook" and _needs_session_cookies(detail):
            hint = " Contenido restringido: cookies.txt opcional."
        raise RuntimeError(
            f"No pude descargar {label} (código {rc}).{hint}"
            + (f"\n{detail[:300]}" if detail else "")
        )

    video_exts = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
    recent = sorted(
        (p for p in out_dir.glob("*") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in recent:
        if p.suffix.lower() in video_exts:
            return p
    names = [p.name for p in recent[:8]]
    hint = ""
    if any(p.suffix.lower() == ".mhtml" for p in recent):
        hint = " YouTube solo entregó storyboards (SABR), no un MP4."
    elif names:
        hint = f" Archivos: {', '.join(names)}"
    raise RuntimeError("Descarga terminada pero no encontré el archivo de vídeo." + hint)
