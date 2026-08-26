"""Bot Descargador — vídeo de TikTok, Reels, YouTube y más (yt-dlp)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from job_control import JobCancelled, TrackedPopen, check_cancelled, terminate_all
from ytdlp_runner import (
    YOUTUBE_FFMPEG_PASS_SEC,
    download_timeout_sec,
    ejs_installed,
    needs_metadata_probe,
    platform_label,
    probe_youtube_duration,
    run_download,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("botdescargador")

ROOT = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or os.getenv("BOT_TOKEN", "").strip()
if not TOKEN:
    _token_file = ROOT / "token.txt"
    if _token_file.is_file():
        TOKEN = _token_file.read_text(encoding="utf-8").strip()
if not TOKEN:
    print("[ERROR] Falta TELEGRAM_BOT_TOKEN en .env o token.txt")
    sys.exit(1)

TMP_DIR = Path(os.getenv("BOT_TMP_DIR", str(ROOT / "temp")))
TMP_DIR.mkdir(parents=True, exist_ok=True)

TELEGRAM_MAX_MB = int(os.getenv("TELEGRAM_MAX_MB", "48") or "48")
MAX_DURATION_SEC = int(os.getenv("MAX_VIDEO_DURATION_SEC", "21600") or "21600")
YTDLP_SOCKET_TIMEOUT = int(os.getenv("YTDLP_SOCKET_TIMEOUT", "60") or "60")
COOKIES_FILE = ROOT / "cookies.txt"
BOT_VERSION = "2026-08-13-v11"


def resolve_cookies_file() -> Path | None:
    """Desactivado: no usar cookies de cuenta (Instagram/sesión)."""
    return None

bot = telebot.TeleBot(TOKEN)
_lock = threading.Lock()
_jobs: dict[int, dict] = {}


def _cancel_markup() -> InlineKeyboardMarkup:
    m = InlineKeyboardMarkup()
    m.add(InlineKeyboardButton("❌ Cancelar", callback_data="dl:cancel"))
    return m


def _is_busy(chat_id: int) -> bool:
    with _lock:
        return chat_id in _jobs


def _begin_job(chat_id: int) -> tuple[threading.Event, int]:
    with _lock:
        seq = int(_jobs.get(chat_id, {}).get("seq", 0)) + 1 if chat_id in _jobs else 1
        if chat_id not in _jobs:
            _jobs[chat_id] = {}
        ev = threading.Event()
        _jobs[chat_id] = {"cancel": ev, "seq": seq}
        return ev, seq


def _get_cancel(chat_id: int) -> threading.Event | None:
    with _lock:
        j = _jobs.get(chat_id)
        return j.get("cancel") if j else None


def _end_job(chat_id: int, job_seq: int) -> None:
    with _lock:
        j = _jobs.get(chat_id)
        if j and j.get("seq") == job_seq:
            _jobs.pop(chat_id, None)


def _job_valid(chat_id: int, job_seq: int) -> bool:
    with _lock:
        j = _jobs.get(chat_id)
        return bool(j and j.get("seq") == job_seq)


URL_RE = re.compile(r"https?://\S+", re.I)
INSTAGRAM_RE = re.compile(
    r"https?://(?:(?:www\.)?instagram\.com/(?:reels?|p|tv)/|(?:www\.)?instagr\.am/p/)",
    re.I,
)
TIKTOK_RE = re.compile(
    r"https?://(?:(?:vm|vt|www|m)\.)?tiktok\.com/",
    re.I,
)
YOUTUBE_RE = re.compile(
    r"https?://(?:(?:www|m|music)\.)?(?:youtube\.com/|youtu\.be/)",
    re.I,
)
YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^#]*?&)?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})",
    re.I,
)
TWITTER_RE = re.compile(
    r"https?://(?:(?:www|mobile|video)\.)?(?:twitter\.com|x\.com)/",
    re.I,
)
FACEBOOK_RE = re.compile(
    r"https?://(?:(?:www|m|web|mbasic)\.)?facebook\.com/|https?://fb\.watch/",
    re.I,
)


def _platform(url: str) -> str:
    if YOUTUBE_RE.search(url):
        return "youtube"
    if INSTAGRAM_RE.search(url):
        return "instagram"
    if TIKTOK_RE.search(url):
        return "tiktok"
    if TWITTER_RE.search(url):
        return "twitter"
    if FACEBOOK_RE.search(url):
        return "facebook"
    return "other"


def _probe_file_duration(path: Path) -> float:
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
            timeout=120,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return max(1.0, float(proc.stdout.strip()))
    except (ValueError, subprocess.TimeoutExpired, OSError):
        pass
    return 1.0


def _edit_status(
    chat_id: int,
    msg_id: int,
    text: str,
    *,
    show_cancel: bool = True,
) -> None:
    markup = _cancel_markup() if show_cancel else None
    try:
        bot.edit_message_text(
            text,
            chat_id,
            msg_id,
            parse_mode="Markdown",
            reply_markup=markup,
        )
    except Exception:
        try:
            bot.edit_message_text(
                text.replace("*", ""),
                chat_id,
                msg_id,
                reply_markup=markup,
            )
        except Exception as e:
            logger.debug("edit falló: %s", e)


def compress_for_telegram(
    source: Path,
    cancel_event: threading.Event | None,
    on_progress,
) -> Path:
    limit = TELEGRAM_MAX_MB * 1024 * 1024
    if source.stat().st_size <= limit:
        return source
    if not shutil.which("ffmpeg"):
        mb = source.stat().st_size // (1024 * 1024)
        raise RuntimeError(
            f"Vídeo ~{mb} MB (Telegram ~{TELEGRAM_MAX_MB} MB). Falta FFmpeg."
        )
    duration = _probe_file_duration(source)
    budget_kbps = int((TELEGRAM_MAX_MB * 1024 * 8 * 0.9) / duration)
    video_kbps = max(150, min(900, budget_kbps - 96))
    height = 240 if duration > 5400 else (360 if duration > 1800 else 480)
    out = TMP_DIR / f"{source.stem}_tg.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-threads",
        "2",
        "-i",
        str(source),
        "-vf",
        f"scale=-2:'min({height},ih)'",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        f"{video_kbps}k",
        "-maxrate",
        f"{int(video_kbps * 1.15)}k",
        "-bufsize",
        f"{int(video_kbps * 2)}k",
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
    proc = TrackedPopen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    timeout = max(1800, int(duration * 1.5) + 300)
    start = time.monotonic()
    last_pct = -1
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            check_cancelled(cancel_event)
            if time.monotonic() - start > timeout:
                proc.kill()
                terminate_all()
                raise RuntimeError("Compresión tardó demasiado.")
            line = line.strip()
            if duration > 0 and line.startswith("out_time_ms="):
                try:
                    ms = int(line.split("=", 1)[1])
                    pct = min(99, int(100 * (ms / 1_000_000.0) / duration))
                    if pct != last_pct:
                        last_pct = pct
                        on_progress(pct, f"Comprimiendo {pct}%")
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
        raise RuntimeError("No pude comprimir el vídeo para Telegram.")
    on_progress(100, "Listo")
    return out


@bot.message_handler(commands=["start", "help"])
def welcome(message):
    ejs = "✅" if ejs_installed() else "❌ (ACTUALIZAR_PI.cmd)"
    yt_fast = int(YOUTUBE_FFMPEG_PASS_SEC // 60)
    txt = (
        f"🎬 *Meta Downloader* `{BOT_VERSION}`\n"
        "Descarga *vídeo* de enlaces públicos.\n\n"
        "✅ TikTok · Reels · YouTube · X · Facebook\n"
        f"✅ YouTube JS: {ejs}\n\n"
        f"📎 YouTube >{yt_fast} min: modo rápido (1 paso, ~48 MB).\n"
        "📎 TikTok/Reels/X: segundos.\n"
        "❌ *Cancelar* en pantalla para otro enlace.\n"
        f"📦 Telegram ~{TELEGRAM_MAX_MB} MB.\n"
        "🔓 Reels públicos: sin cookies.\n"
        "🔒 Solo privados (que sigues): cookies.txt opcional."
    )
    bot.send_message(message.chat.id, txt, parse_mode="Markdown")


def _extract_url(text: str) -> str | None:
    m = URL_RE.search(text or "")
    if not m:
        yt = YOUTUBE_ID_RE.search(text or "")
        if yt:
            return f"https://www.youtube.com/watch?v={yt.group(1)}"
        return None
    return _normalize_url(m.group(0).rstrip(").,]\"'"))


def _normalize_url(url: str) -> str:
    yt = YOUTUBE_ID_RE.search(url)
    if yt:
        return f"https://www.youtube.com/watch?v={yt.group(1)}"
    return url


def _url_from_message(message) -> str | None:
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    for ent in entities:
        if ent.type == "text_link" and ent.url:
            return _normalize_url(ent.url.rstrip(").,]\"'"))
        if ent.type == "url" and text:
            raw = text[ent.offset : ent.offset + ent.length]
            found = _extract_url(raw) or _extract_url(text)
            if found:
                return found
    return _extract_url(text)


@bot.callback_query_handler(func=lambda c: c.data == "dl:cancel")
def on_cancel_download(call):
    chat_id = call.message.chat.id
    ev = _get_cancel(chat_id)
    if ev is None:
        bot.answer_callback_query(call.id, "No hay descarga activa.")
        return
    ev.set()
    terminate_all()
    bot.answer_callback_query(call.id, "Cancelando…")
    try:
        bot.edit_message_text(
            "❌ *Cancelado.*\nYa puedes enviar otro enlace.",
            chat_id,
            call.message.message_id,
            parse_mode="Markdown",
        )
    except Exception:
        pass


@bot.message_handler(
    content_types=["document"],
    func=lambda m: bool(
        m.document
        and m.document.file_name
        and m.document.file_name.lower() in ("cookies.txt", "cookies.txt.txt")
    ),
)
def on_cookies_upload(message):
    bot.reply_to(
        message,
        "🚫 *Subida de cookies desactivada.*\n\n"
        "No se guarda ni usa login de Instagram/cuenta "
        "para evitar flags de automatización.",
        parse_mode="Markdown",
    )

@bot.message_handler(func=lambda m: bool((m.text or m.caption) and _url_from_message(m)))
def process_link(message):
    chat_id = message.chat.id
    if _is_busy(chat_id):
        bot.reply_to(
            message,
            "⏳ Hay una descarga en curso.\nPulsa *❌ Cancelar* en el mensaje de progreso.",
            parse_mode="Markdown",
        )
        return

    url = _url_from_message(message)
    assert url
    platform = _platform(url)
    label = platform_label(platform)
    logger.info("Enlace %s: %s", platform, url)
    cancel_ev, job_seq = _begin_job(chat_id)

    status = bot.reply_to(
        message,
        f"⏳ *Procesando {label}…*",
        parse_mode="Markdown",
        reply_markup=_cancel_markup(),
    )

    def worker() -> None:
        path = None
        compressed = None
        try:
            duration = 0.0
            if needs_metadata_probe(platform):
                _edit_status(chat_id, status.message_id, f"⏳ *Preparando {label}…*")
                try:
                    duration = probe_youtube_duration(
                        url,
                        cookies=None,
                        socket_timeout=YTDLP_SOCKET_TIMEOUT,
                        cancel_event=cancel_ev,
                    )
                except RuntimeError as e:
                    logger.warning("YouTube duración: %s — modo largo", e)
                    duration = float(YOUTUBE_FFMPEG_PASS_SEC + 60)
                check_cancelled(cancel_ev)
                if duration > MAX_DURATION_SEC:
                    raise RuntimeError(
                        f"Duración ~{int(duration // 60)} min "
                        f"(~{duration / 3600:.1f} h). "
                        f"Máximo ~{MAX_DURATION_SEC // 3600} h por mensaje de Telegram."
                    )
                mins = int(duration // 60) if duration else 0
                if duration > YOUTUBE_FFMPEG_PASS_SEC:
                    _edit_status(
                        chat_id,
                        status.message_id,
                        f"⏳ *YouTube* (~{mins} min)\n"
                        "Modo rápido: preparando vídeo para Telegram…",
                    )
                else:
                    _edit_status(
                        chat_id,
                        status.message_id,
                        f"⏳ *Descargando {label}* (~{mins} min)…",
                    )
            else:
                _edit_status(
                    chat_id,
                    status.message_id,
                    f"⏳ *Descargando {label}…*",
                )

            def on_dl_progress(pct: int, sub: str) -> None:
                if not _job_valid(chat_id, job_seq):
                    return
                _edit_status(
                    chat_id,
                    status.message_id,
                    f"⏳ *{label}* {pct}%\n_{sub}_",
                )

            timeout = download_timeout_sec(duration, platform=platform)
            path = run_download(
                url,
                TMP_DIR,
                platform=platform,
                duration_sec=duration,
                cookies=None,
                socket_timeout=YTDLP_SOCKET_TIMEOUT,
                cancel_event=cancel_ev,
                on_progress=on_dl_progress,
                timeout_sec=timeout,
                max_mb=TELEGRAM_MAX_MB,
            )
            check_cancelled(cancel_ev)

            actual_dur = _probe_file_duration(path)
            if (
                platform == "youtube"
                and duration >= 300
                and actual_dur < min(120, duration * 0.02)
            ):
                raise RuntimeError(
                    f"Descarga incompleta (~{int(actual_dur)} s de "
                    f"~{int(duration // 60)} min). Vuelve a intentarlo."
                )

            if duration <= 0 or (
                platform == "youtube" and actual_dur > duration * 0.5
            ):
                duration = actual_dur
            dur_txt = (
                f"{int(duration // 60)} min"
                if duration >= 60
                else f"{int(duration or 30)} s"
            )

            size_mb = path.stat().st_size / (1024 * 1024)
            if size_mb > TELEGRAM_MAX_MB:
                _edit_status(
                    chat_id,
                    status.message_id,
                    f"⏳ *Comprimiendo* ({size_mb:.0f} → ~{TELEGRAM_MAX_MB} MB)…",
                )

                def on_cmp(pct: int, sub: str) -> None:
                    _edit_status(
                        chat_id,
                        status.message_id,
                        f"⏳ *Comprimiendo* {pct}%\n_{sub}_",
                    )

                compressed = compress_for_telegram(path, cancel_ev, on_cmp)
                send_path = compressed
            else:
                send_path = path

            check_cancelled(cancel_ev)
            _edit_status(
                chat_id,
                status.message_id,
                "⏳ *Enviando a Telegram…*",
                show_cancel=False,
            )
            with open(send_path, "rb") as f:
                bot.send_video(
                    chat_id,
                    f,
                    caption=f"✅ *Listo* ({dur_txt})",
                    parse_mode="Markdown",
                    timeout=600,
                )
            try:
                bot.delete_message(chat_id, status.message_id)
            except Exception:
                pass
        except JobCancelled:
            logger.info("Cancelado chat=%s", chat_id)
            if _job_valid(chat_id, job_seq):
                _edit_status(
                    chat_id,
                    status.message_id,
                    "❌ *Cancelado.*\nYa puedes enviar otro enlace.",
                    show_cancel=False,
                )
        except Exception as e:
            if _job_valid(chat_id, job_seq):
                logger.exception("Error %s %s", platform, url)
                _edit_status(
                    chat_id,
                    status.message_id,
                    f"❌ *Error:*\n{str(e)[:500]}",
                    show_cancel=False,
                )
        finally:
            terminate_all()
            for p in (path, compressed):
                if p and p.is_file():
                    try:
                        p.unlink()
                    except OSError:
                        pass
            _end_job(chat_id, job_seq)

    threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    logger.info("Meta Downloader %s — ejs=%s", BOT_VERSION, ejs_installed())
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
