import logging

import re

import subprocess

import threading

from collections.abc import Callable

from pathlib import Path



import yt_dlp



from bot.services.progress import ProgressCallback, make_ytdlp_progress_hook



from bot.config import (
    FAST_POLISH,
    FFMPEG_THREADS,
    LINK_PATTERNS,
    MAX_LINK_DURATION_SEC,
    MAX_YOUTUBE_DOWNLOAD_MB,
    MAX_YOUTUBE_DURATION_SEC,
    ROOT,
    TEMP_DIR,
    TWITTER_PATTERNS,
    YOUTUBE_PATTERNS,
    YTDLP_BROWSER,
    YTDLP_SOCKET_TIMEOUT,
)



logger = logging.getLogger(__name__)

# Archivos enviados como "documento" en Telegram (p. ej. MP3 adjunto)
AUDIO_FILE_EXTENSIONS = frozenset(
    {
        ".mp3",
        ".m4a",
        ".aac",
        ".ogg",
        ".opus",
        ".wav",
        ".flac",
        ".wma",
        ".webm",
        ".amr",
        ".3gp",
        ".aiff",
        ".aif",
        ".mpeg",
        ".mpga",
        ".mid",
        ".midi",
        ".caf",
        ".ape",
    }
)

_AUDIO_MIME_TO_EXT = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
    "audio/aac": ".aac",
    "audio/amr": ".amr",
    "audio/x-flac": ".flac",
}


def audio_suffix_for_document(file_name: str | None, mime_type: str | None) -> str | None:
    """Extensión si el documento de Telegram es audio (por nombre o MIME)."""
    name = file_name or ""
    ext = Path(name).suffix.lower()
    mime = (mime_type or "").lower().split(";")[0].strip()

    if ext in AUDIO_FILE_EXTENSIONS:
        return ext
    if mime.startswith("audio/"):
        if ext in AUDIO_FILE_EXTENSIONS:
            return ext
        return _AUDIO_MIME_TO_EXT.get(mime, ".mp3")
    if mime == "application/ogg" and (not ext or ext in AUDIO_FILE_EXTENSIONS):
        return ext or ".ogg"
    return None


def telegram_message_is_audio(msg) -> bool:
    if getattr(msg, "voice", None) or getattr(msg, "audio", None):
        return True
    doc = getattr(msg, "document", None)
    if doc and audio_suffix_for_document(doc.file_name, doc.mime_type):
        return True
    return False



# De más específico a más permisivo (evita "Requested format is not available")

def _youtube_format_chain(*, for_telegram: bool = False) -> tuple[str, ...]:
    """Solo pistas de audio. Nunca 'best' (baja vídeo+audio y se corta por max-filesize)."""
    if for_telegram:
        # Bitrate bajo → cabe en ~48 MB sin re-codificar horas en la Pi
        return (
            "ba[abr<=48]/bestaudio[abr<=48]/"
            "bestaudio[abr<=64]/worstaudio[abr<=48]/worstaudio",
            "bestaudio/ba/worstaudio",
        )
    # Transcripción: máxima calidad posible. ABR bajo hace que Whisper
    # corte finales (también→tambi, través→trav, sí→s).
    return (
        "bestaudio/ba/worstaudio",
        "bestaudio[abr<=256]/bestaudio[abr<=192]/ba",
    )


def _social_format_chain() -> tuple[str, ...]:
    # TikTok/Reels: HEVC (bytevc1) a veces llega sin pista de audio; priorizar H.264.
    h264_mux = (
        "best[vcodec^=avc]/best[vcodec^=h264]/"
        "best[acodec!=none]/download/best"
    )
    if FAST_POLISH:
        return (h264_mux, "bestaudio[ext=m4a]/bestaudio/ba/b")
    return (h264_mux, "bestaudio/best", "ba/b", "best")


def _social_audio_format_chain() -> tuple[str, ...]:
    """Solo audio (MP3 directo): evita bajar vídeo completo en TikTok/Reels."""
    return (
        "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/ba/b",
        "ba/b",
        "bestaudio/best",
    )





def looks_like_social_link(text: str) -> bool:

    t = text.strip().lower()

    return any(re.search(p, t, re.I) for p in LINK_PATTERNS)





def is_youtube_url(url: str) -> bool:

    u = url.lower()

    return any(re.search(p, u) for p in YOUTUBE_PATTERNS)


def is_youtube_shorts_url(url: str) -> bool:
    """True para /shorts/… (Whisper; los auto-subs de Shorts cortan y puntúan mal)."""
    return bool(re.search(r"(?:youtube\.com|youtu\.be)/shorts/", (url or "").lower()))


def is_twitter_url(url: str) -> bool:

    u = url.lower()

    return any(re.search(p, u) for p in TWITTER_PATTERNS)


def is_instagram_url(url: str) -> bool:
    u = url.lower()
    return "instagram.com" in u or "instagr.am" in u


def twitter_status_id(url: str) -> str | None:

    m = re.search(
        r"(?:twitter\.com|x\.com)/(?:[\w]+/status/|i/status/)(\d+)",
        url,
        re.I,
    )

    return m.group(1) if m else None


def _social_ytdlp_extra(url: str) -> dict:
    extra: dict = {}
    if is_instagram_url(url):
        extra.setdefault("extractor_args", {})["instagram"] = {
            "preload_features": "boxes",
        }
    return extra


def _cookies_txt_path() -> Path | None:
    """Cookies de cuenta desactivadas (evitar login automático / flags de Instagram)."""
    return None


def _is_private_content_error(msg: str) -> bool:
    low = msg.lower()
    return any(
        k in low
        for k in (
            "private",
            "privado",
            "not available",
            "no está disponible",
            "followers",
            "members only",
            "locked",
            "restricted",
            "candado",
        )
    )


def _needs_session_cookies(msg: str) -> bool:
    """True solo si el fallo sugiere que hace falta sesión (contenido restringido)."""
    low = msg.lower()
    if _is_private_content_error(msg):
        return True
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
            "403",
        )
    )


def _social_extra(url: str, *, use_cookies: bool) -> dict:
    extra = _social_ytdlp_extra(url)
    # Nunca cookies de cuenta en redes (Instagram/TikTok/etc.)
    if use_cookies and not is_instagram_url(url) and (p := _cookies_txt_path()):
        extra["cookiefile"] = str(p)
    return extra





def max_duration_for_url(url: str) -> int:

    return MAX_YOUTUBE_DURATION_SEC if is_youtube_url(url) else MAX_LINK_DURATION_SEC





def extract_url(text: str) -> str | None:

    m = re.search(r"https?://\S+", text.strip())

    return m.group(0).rstrip(").,]\"'") if m else None





def extract_social_url(text: str) -> str | None:

    for m in re.finditer(r"https?://\S+", text):

        url = m.group(0).rstrip(").,]\"'")

        if looks_like_social_link(url):

            return url

    t = text.strip()

    if t.lower().startswith("http") and looks_like_social_link(t):

        return extract_url(t) or t

    return None





def probe_media_duration_sec(source: Path) -> float:
    """Duración del archivo (segundos) vía ffprobe; 0 si no se puede leer."""
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
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return max(0.0, float(proc.stdout.strip()))
    except (ValueError, subprocess.TimeoutExpired, OSError):
        pass
    return 0.0


def probe_media_has_audio(source: Path) -> bool:
    """True si ffprobe detecta al menos una pista de audio."""
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.returncode == 0 and "audio" in proc.stdout
    except (subprocess.TimeoutExpired, OSError):
        return False


def _ffmpeg_to_wav_cmd(source: Path, out: Path, *, use_audio_map: bool) -> list[str]:
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-threads",
        str(max(1, FFMPEG_THREADS)),
        "-i",
        str(source),
        "-vn",
        "-sn",
        "-dn",
    ]
    if use_audio_map:
        cmd.extend(["-map", "0:a:0?"])
    cmd.extend(
        [
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-progress",
            "pipe:1",
            "-nostats",
            str(out),
        ]
    )
    return cmd


def _run_ffmpeg_wav(
    source: Path,
    out: Path,
    *,
    duration_sec: float,
    on_progress: Callable[[int, str], None] | None,
    cancel_event: threading.Event | None = None,
) -> bool:
    from bot.services.format_timestamps import format_timestamp
    from bot.services.job_cancel import TrackedPopen, check_cancelled

    last_pct = -1
    for use_map in (True, False):
        proc = TrackedPopen(
            _ffmpeg_to_wav_cmd(source, out, use_audio_map=use_map),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                check_cancelled(cancel_event)
                line = line.strip()
                if not on_progress or not duration_sec or not line.startswith("out_time_ms="):
                    continue
                try:
                    ms = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                elapsed = ms / 1_000_000.0
                pct = min(99, int(100 * elapsed / duration_sec))
                if pct != last_pct:
                    last_pct = pct
                    sub = (
                        f"{format_timestamp(elapsed)} / "
                        f"{format_timestamp(duration_sec)}"
                    )
                    on_progress(pct, sub)
            check_cancelled(cancel_event)
            proc.wait(timeout=max(7200, int(duration_sec * 2) + 300))
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("FFmpeg tardó demasiado extrayendo el audio")
        finally:
            from bot.services.job_cancel import unregister_pid

            unregister_pid(proc.pid)
        if proc.returncode == 0 and out.exists():
            if on_progress:
                on_progress(100, "")
            return True
        if use_map and out.exists():
            out.unlink()
    return False


def to_wav_16k(
    source: Path,
    on_progress: Callable[[int, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> Path:
    from bot.services.job_cancel import check_cancelled

    check_cancelled(cancel_event)
    out = TEMP_DIR / f"{source.stem}_16k.wav"
    duration_sec = probe_media_duration_sec(source)
    if on_progress and duration_sec > 0:
        on_progress(0, "")
    if not _run_ffmpeg_wav(
        source,
        out,
        duration_sec=duration_sec,
        on_progress=on_progress,
        cancel_event=cancel_event,
    ):
        if not probe_media_has_audio(source):
            raise RuntimeError(
                "El archivo descargado no tiene pista de audio (vídeo mudo). "
                "Prueba otro enlace o reenvía el archivo."
            )
        raise RuntimeError(
            "No pude procesar el archivo de audio. ¿Tienes FFmpeg instalado?"
        )
    return out





def _pick_info(info: dict | None) -> dict | None:

    if not info:

        return None

    if info.get("_type") in ("playlist", "multi_video") and info.get("entries"):

        return info["entries"][0] or info

    return info


def extract_media_title(info: dict | None) -> str:
    picked = _pick_info(info)
    if not picked:
        return ""
    title = (picked.get("title") or picked.get("track") or "").strip()
    return title[:200] if title else ""


def media_meta_from_info(info: dict | None) -> dict[str, str]:
    title = extract_media_title(info)
    return {"title": title} if title else {}





def _is_audio_only_format(info: dict) -> bool:
    """True si el formato elegido es pista de audio (no vídeo muxeado)."""
    vc = str(info.get("vcodec") or "none").strip().lower()
    if vc in ("none", "null", ""):
        return True
    ac = str(info.get("acodec") or "").strip().lower()
    ext = str(info.get("ext") or "").strip().lower()
    if ac in ("", "none"):
        return False
    if info.get("width") or info.get("height"):
        return False
    return ext in ("m4a", "webm", "opus", "ogg", "mp3", "aac", "mka")


def _check_duration(info: dict, url: str) -> None:

    dur = info.get("duration") or 0

    limit = max_duration_for_url(url)

    if dur and dur > limit:

        mins = int(dur // 60)

        cap = limit // 60

        platform = "YouTube" if is_youtube_url(url) else "este enlace"

        raise RuntimeError(
            f"NO PUEDO: el vídeo dura ~{mins} min. "
            f"Máximo para {platform}: ~{cap} min."
        )


def _estimated_audio_bytes(duration_sec: float, abr_kbps: int = 160) -> int:
    if duration_sec <= 0:
        return 0
    return int(duration_sec * abr_kbps * 1000 / 8)


def _check_download_size(info: dict, url: str, lang: str) -> None:
    from bot.i18n_progress import prog

    if not is_youtube_url(url):
        return
    limit = MAX_YOUTUBE_DOWNLOAD_MB * 1024 * 1024
    size = 0
    for key in ("filesize", "filesize_approx"):
        raw = info.get(key)
        if raw:
            size = max(size, int(raw))
    if not size:
        size = _estimated_audio_bytes(float(info.get("duration") or 0))
    if size and size > limit:
        mb = size / (1024 * 1024)
        raise RuntimeError(
            prog(
                "youtube_download_too_large",
                lang,
                mb=f"{mb:.0f}",
                max_mb=MAX_YOUTUBE_DOWNLOAD_MB,
            )
        )


def _reject_oversized_file(path: Path, lang: str) -> None:
    from bot.i18n_progress import prog

    if not path.is_file():
        return
    limit = MAX_YOUTUBE_DOWNLOAD_MB * 1024 * 1024
    size = path.stat().st_size
    if size > limit:
        mb = size / (1024 * 1024)
        try:
            path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            prog("youtube_download_too_large", lang, mb=f"{mb:.0f}", max_mb=MAX_YOUTUBE_DOWNLOAD_MB)
        )





def _find_downloaded_file(
    info: dict | None,
    since: float,
    *,
    expected_id: str | None = None,
) -> Path | None:
    vid = (info or {}).get("id") or expected_id

    if vid:
        for ext in ("m4a", "mp3", "webm", "mp4", "opus", "mkv"):
            candidate = TEMP_DIR / f"{vid}.{ext}"
            if candidate.is_file():
                return candidate

        matches = sorted(
            TEMP_DIR.glob(f"{vid}*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for candidate in matches:
            if candidate.is_file():
                return candidate
        return None

    audio_ext = {".m4a", ".mp3", ".webm", ".mp4", ".opus", ".mkv", ".wav"}
    recent = [
        p
        for p in TEMP_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() in audio_ext
        and p.stat().st_mtime >= since - 2
    ]
    if recent:
        return max(recent, key=lambda p: p.stat().st_mtime)
    return None


def _expected_youtube_id(url: str) -> str | None:
    if is_youtube_url(url):
        from bot.services.source_links import youtube_video_id

        return youtube_video_id(url)
    return None


def _expected_media_id(url: str) -> str | None:
    """Id predecible del archivo en temp/ (YouTube o shortcode de Instagram)."""
    if yt := _expected_youtube_id(url):
        return yt
    if is_instagram_url(url):
        from bot.services.instagram_fallback import instagram_shortcode

        return instagram_shortcode(url)
    return None


def _validate_download_path(path: Path, url: str, meta: dict | None) -> None:
    """Evita reutilizar un .m4a viejo de temp/ de otro vídeo."""
    expected = _expected_media_id(url)
    if not expected:
        return
    meta_id = str((meta or {}).get("id") or "").strip()
    if meta_id and meta_id != expected:
        raise RuntimeError(
            f"La descarga no coincide con el enlace (id {meta_id} ≠ {expected})."
        )
    if expected not in path.name:
        raise RuntimeError(
            "Se encontró un archivo temporal de otro vídeo; reintenta el enlace."
        )


def _resolve_downloaded_file(
    info: dict | None, since: float, url: str
) -> Path:
    meta = _pick_info(info)
    expected_id = _expected_media_id(url)
    found = _find_downloaded_file(meta, since, expected_id=expected_id)
    if not found:
        raise RuntimeError(
            "No encontré el archivo descargado para este enlace."
        )
    _validate_download_path(found, url, meta)
    return found





def _is_format_error(msg: str) -> bool:

    low = msg.lower()

    return "format is not available" in low or "requested format" in low


def _is_download_interrupted(msg: str) -> bool:
    low = msg.lower()
    return "código -15" in low or "código -9" in low or "code -15" in low or "code -9" in low





def _is_cookie_error(msg: str) -> bool:

    low = msg.lower()

    return "dpapi" in low or "decrypt" in low or "could not find" in low and "cookies" in low





def _friendly_instagram_error(msg: str) -> str:
    if _is_private_content_error(msg):
        return (
            "Este Reel es de una cuenta privada o restringida.\n\n"
            "Los enlaces públicos funcionan sin cookies ni tocar tu cuenta."
        )
    if _needs_session_cookies(msg) and not _cookies_txt_path():
        return (
            "No pude acceder a este Reel.\n\n"
            "Si el enlace es público, prueba otro. "
            "cookies.txt solo hace falta para contenido privado que tú sigues (opcional)."
        )
    return f"No pude descargar de Instagram/Reels: {msg[:200]}"


def _friendly_youtube_error(msg: str) -> str:

    low = msg.lower()

    if _is_cookie_error(msg):

        cookies_path = ROOT / "cookies.txt"

        return (

            "No pude usar las cookies del navegador en Windows.\n\n"

            "🔧 *Solución recomendada:*\n"

            "1. En Chrome o Edge, instala la extensión *Get cookies.txt LOCALLY*\n"

            "2. Entra en youtube.com (sesión iniciada)\n"

            f"3. Exporta el archivo como:\n   `{cookies_path}`\n"

            "4. Reinicia el bot (`LANZAR_BOT.cmd`) y reenvía el enlace.\n\n"

            "También puedes cerrar por completo Chrome/Edge y probar de nuevo."

        )

    if "bot" in low or "sign in" in low:

        return (

            "YouTube pidió verificación o bloqueó el acceso.\n\n"

            "🔧 Usa el archivo `cookies.txt` en la carpeta del bot "

            "(exportado desde el navegador con sesión en YouTube).\n"

            "TikTok y Reels no necesitan este paso."

        )

    if _is_format_error(msg):

        return (

            "YouTube no ofreció un formato compatible en ningún intento.\n"

            "Prueba otro vídeo o exporta cookies.txt (ver ayuda con /help)."

        )

    return f"No pude descargar de YouTube: {msg[:200].removeprefix('No pude descargar de YouTube: ')}"





def _base_ytdlp_opts(
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    *,
    format_str: str = "bestaudio/best",
    extract_audio: bool = True,
    youtube_audio_only: bool = False,
    lang: str = "es",
) -> dict:
    opts: dict = {
        "format": format_str,
        "outtmpl": str(TEMP_DIR / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "playlistend": 1,
        "overwrites": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
        "fragment_retries": 5,
        "socket_timeout": YTDLP_SOCKET_TIMEOUT,
        "max_filesize": MAX_YOUTUBE_DOWNLOAD_MB * 1024 * 1024,
    }
    if youtube_audio_only:
        opts["concurrent_fragment_downloads"] = 4
        opts["http_chunk_size"] = 1048576
    # YouTube: el archivo ya es audio; evitar postproceso FFmpeg (lento en Pi)
    if extract_audio and not youtube_audio_only:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "128",
            }
        ]
    if on_progress or cancel_event:
        opts["progress_hooks"] = [
            make_ytdlp_progress_hook(on_progress, cancel_event=cancel_event, lang=lang)
        ]
    return opts





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
        )
    )


def _youtube_attempt_opts_list(*, audio_only: bool = False) -> list[dict]:
    """Varios clientes de YouTube; cookies.txt solo al final si todo falla."""
    cookies_file = _cookies_txt_path()
    attempts: list[dict] = [
        {"extractor_args": {"youtube": {"player_client": ["tv_embedded"]}}},
        {"extractor_args": {"youtube": {"player_client": ["android_vr", "web_safari"]}}},
        {"extractor_args": {"youtube": {"player_client": ["mweb"]}}},
        {"extractor_args": {"youtube": {"player_client": ["web"]}}},
        {"extractor_args": {"youtube": {"player_client": ["android"]}}},
    ]
    if not audio_only and not FAST_POLISH:
        attempts.append({"extractor_args": {"youtube": {"player_client": ["ios"]}}})
    attempts.append({})
    if cookies_file:
        attempts.append({"cookiefile": str(cookies_file)})
    return attempts





def _run_ytdlp_download(
    url: str,
    extra: dict,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    *,
    format_chain: tuple[str, ...] | None = None,
    youtube_mode: bool = False,
    lang: str = "es",
    youtube_meta: dict | None = None,
) -> dict | None:
    from bot.i18n_progress import prog
    from bot.services.ytdlp_run import (
        run_ytdlp_cli_chain,
        youtube_download_timeout_sec,
        ytdlp_ejs_installed,
    )

    if is_youtube_url(url) and not ytdlp_ejs_installed():
        raise RuntimeError(prog("ytdlp_ejs_missing", lang))

    formats = format_chain or _social_format_chain()
    dl_label = prog("downloading_audio_only", lang) if youtube_mode else prog("downloading", lang)
    if on_progress:
        on_progress(10, dl_label, prog("link_starting", lang))

    timeout_sec = None
    if youtube_mode and youtube_meta:
        size = int(youtube_meta.get("filesize") or youtube_meta.get("filesize_approx") or 0)
        dur = float(youtube_meta.get("duration") or 0)
        timeout_sec = youtube_download_timeout_sec(size, dur)

    run_ytdlp_cli_chain(
        url,
        formats,
        extra,
        on_progress=on_progress,
        cancel_event=cancel_event,
        lang=lang,
        max_mb=MAX_YOUTUBE_DOWNLOAD_MB if youtube_mode else None,
        timeout_sec=timeout_sec,
        progress_label=dl_label if youtube_mode else None,
    )
    return youtube_meta





def _download_youtube(

    url: str,

    on_progress: ProgressCallback | None = None,

    cancel_event: threading.Event | None = None,

    lang: str = "es",

    *,
    for_telegram: bool = False,
    audio_only: bool = False,
) -> dict | None:

    last_err = ""
    attempts = _youtube_attempt_opts_list(audio_only=audio_only)
    total = len(attempts)

    for idx, extra in enumerate(attempts, start=1):

        if cancel_event and cancel_event.is_set():

            raise RuntimeError("Descarga cancelada.")

        label = list(extra.keys()) if extra else ["default"]

        try:
            from bot.i18n_progress import prog
            from bot.services.ytdlp_run import probe_youtube_metadata

            if on_progress:
                on_progress(
                    6,
                    prog("downloading_audio_only", lang),
                    prog("youtube_try", lang, n=idx, total=total),
                )

            fmt = _youtube_format_chain(for_telegram=for_telegram)[0]
            meta = probe_youtube_metadata(url, fmt, extra, lang=lang)
            if not _is_audio_only_format(meta):
                last_err = f"cliente {label} ofreció vídeo (vcodec={meta.get('vcodec')})"
                logger.warning(
                    "YouTube %s no es solo audio, siguiente cliente", label
                )
                continue
            _check_duration(meta, url)
            _check_download_size(meta, url, lang)

            logger.info(
                "YouTube intento %s/%s: %s · formato %s · ~%.0f MB",
                idx,
                total,
                label,
                meta.get("format_id"),
                (meta.get("filesize") or meta.get("filesize_approx") or 0) / (1024 * 1024),
            )

            dl_kwargs = dict(
                url=url,
                extra=extra,
                on_progress=on_progress,
                cancel_event=cancel_event,
                format_chain=_youtube_format_chain(for_telegram=for_telegram),
                youtube_mode=True,
                lang=lang,
                youtube_meta=meta,
            )
            try:
                return _run_ytdlp_download(**dl_kwargs)
            except Exception as dl_err:
                dl_msg = str(dl_err)
                if _is_format_error(dl_msg) or _is_cookie_error(dl_msg):
                    raise
                if _is_download_interrupted(dl_msg):
                    logger.warning("YouTube descarga interrumpida, reintento (%s)", label)
                    return _run_ytdlp_download(**dl_kwargs)
                if _is_youtube_retryable_error(dl_msg):
                    last_err = dl_msg
                    logger.warning(
                        "YouTube descarga falló (%s), probando otro cliente", label
                    )
                    continue
                logger.warning(
                    "YouTube descarga falló tras probe OK (%s): %s", label, dl_err
                )
                raise RuntimeError(_friendly_youtube_error(dl_msg)) from dl_err

        except yt_dlp.utils.DownloadCancelled:

            raise RuntimeError("Descarga cancelada.") from None

        except yt_dlp.utils.MaxDownloadsReached:

            return None

        except Exception as e:

            last_err = str(e)

            if _is_cookie_error(last_err):

                logger.warning("Cookies navegador fallaron: %s", e)

                continue

            if _is_format_error(last_err):

                logger.warning("YouTube sin formato audio (%s): %s", label, e)

                continue

            if _is_youtube_retryable_error(last_err):

                logger.warning("YouTube falló (%s), probando otro cliente: %s", label, e)

                continue

            logger.warning("YouTube falló (%s): %s", label, e)
            break

    if last_err:

        raise RuntimeError(_friendly_youtube_error(last_err))

    return None





def download_from_link(
    text_or_url: str,
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
    lang: str = "es",
    *,
    for_telegram: bool = False,
    audio_only: bool = False,
) -> tuple[Path, dict[str, str]]:
    import time

    from bot.i18n_progress import prog

    url = extract_social_url(text_or_url) or text_or_url.strip()

    if not looks_like_social_link(url):

        raise RuntimeError(

            "No encontré un enlace válido (TikTok, Reels, X/Twitter o YouTube)."

        )



    since = time.time()

    info = None



    if is_youtube_url(url):
        if on_progress:
            on_progress(6, prog("downloading_audio_only", lang), "")
        yt_for_tg = for_telegram or audio_only
        info = _download_youtube(
            url,
            on_progress,
            cancel_event,
            lang,
            for_telegram=yt_for_tg,
            audio_only=audio_only,
        )
        if info is None and not _find_downloaded_file(
            {"id": _expected_youtube_id(url)} if _expected_youtube_id(url) else None,
            since,
            expected_id=_expected_youtube_id(url),
        ):
            raise RuntimeError(
                _friendly_youtube_error("No se pudo completar la descarga de YouTube.")
            )

    else:
        if on_progress:
            on_progress(8, prog("downloading", lang), prog("link_starting", lang))

        formats = _social_audio_format_chain() if audio_only else _social_format_chain()
        last_err = ""
        tried_cookies = False
        for use_cookies in (False, True):
            extra = _social_extra(url, use_cookies=use_cookies)
            if use_cookies:
                if not _needs_session_cookies(last_err) or not _cookies_txt_path():
                    break
                tried_cookies = True
                logger.info("Reintentando enlace social con cookies (contenido restringido)")
            for fmt_idx, fmt in enumerate(formats):
                since = time.time()
                try:
                    info = _run_ytdlp_download(
                        url,
                        extra,
                        on_progress,
                        cancel_event,
                        format_chain=(fmt,),
                        lang=lang,
                    )
                except RuntimeError as e:
                    last_err = str(e)
                    if fmt_idx + 1 < len(formats):
                        logger.info("Formato %s falló, siguiente: %s", fmt, e)
                        continue
                    break
                except yt_dlp.utils.DownloadCancelled:
                    raise RuntimeError("Descarga cancelada.") from None
                except yt_dlp.utils.MaxDownloadsReached:
                    pass
                except yt_dlp.utils.DownloadError as e:
                    last_err = str(e)
                    if "Private" in last_err or "private" in last_err:
                        raise RuntimeError(
                            "El vídeo es privado o no está disponible."
                        ) from e
                    if fmt_idx + 1 < len(formats):
                        logger.info("Formato %s falló, siguiente: %s", fmt, e)
                        continue
                    break
                else:
                    meta = _pick_info(info)
                    if meta:
                        _check_duration(meta, url)
                    try:
                        found = _resolve_downloaded_file(info, since, url)
                    except RuntimeError:
                        found = None
                    if found and probe_media_has_audio(found):
                        return found, media_meta_from_info(info)
                    if found:
                        logger.warning(
                            "Descarga sin pista de audio (formato %s), reintentando", fmt
                        )
                        try:
                            found.unlink()
                        except OSError:
                            pass
                        last_err = "sin pista de audio"
                        continue
                    last_err = "sin pista de audio"
                    break
            else:
                continue
            if last_err != "sin pista de audio":
                continue
            break

        if last_err == "sin pista de audio":
            raise RuntimeError(
                "El vídeo se descargó pero no incluye audio. "
                "Prueba otro enlace o actualiza el bot (yt-dlp)."
            )
        if is_instagram_url(url):
            raise RuntimeError(_friendly_instagram_error(last_err or "fallo desconocido"))
        raise RuntimeError(
            "Enlace no válido o contenido privado. Prueba otro enlace público."
        )

    meta = _pick_info(info)
    if meta:
        _check_duration(meta, url)
        if is_youtube_url(url):
            _check_download_size(meta, url, lang)

    found = _resolve_downloaded_file(info, since, url)
    if is_youtube_url(url):
        _reject_oversized_file(found, lang)
    return found, media_meta_from_info(info)

