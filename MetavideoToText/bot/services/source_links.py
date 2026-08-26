"""Enlace al vídeo original y URLs con marca de tiempo (YouTube)."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from telegram.ext import ContextTypes

from bot.services.media import (
    extract_social_url,
    is_twitter_url,
    is_youtube_url,
    twitter_status_id,
)

_YT_ID_RE = re.compile(r"^[\w-]{11}$")

# TikTok / Reels: el reproductor web no abre un segundo concreto vía URL de forma fiable.


def _youtube_video_id(url: str) -> str | None:
    u = (url or "").strip()
    if not u:
        return None
    try:
        parsed = urlparse(u)
    except Exception:
        return None
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = parsed.path or ""

    if host in ("youtu.be",):
        vid = path.strip("/").split("/")[0]
        return vid if _YT_ID_RE.match(vid) else None

    if "youtube.com" in host or "music.youtube.com" in host:
        if path.startswith("/shorts/"):
            vid = path.split("/")[2] if len(path.split("/")) > 2 else ""
            return vid if _YT_ID_RE.match(vid) else None
        if path.startswith("/live/"):
            vid = path.split("/")[2] if len(path.split("/")) > 2 else ""
            return vid if _YT_ID_RE.match(vid) else None
        if path.startswith("/embed/"):
            vid = path.split("/")[2] if len(path.split("/")) > 2 else ""
            return vid if _YT_ID_RE.match(vid) else None
        qs = parse_qs(parsed.query)
        vid = (qs.get("v") or [None])[0]
        return vid if vid and _YT_ID_RE.match(vid) else None

    return None


def media_source_kind(url: str) -> str:
    u = (url or "").lower()
    if is_youtube_url(url):
        return "youtube"
    if "tiktok.com" in u or "vt.tiktok" in u:
        return "tiktok"
    if "instagram.com" in u or "instagr.am" in u:
        return "instagram"
    if is_twitter_url(url):
        return "twitter"
    return "other"


def clear_media_source(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("media_source_url", "media_source_kind", "media_source_yt_id"):
        context.user_data.pop(key, None)


def youtube_video_id(url: str) -> str | None:
    """ID de 11 caracteres para enlaces YouTube; None si no aplica."""
    return _youtube_video_id(url)


def same_media_url(a: str | None, b: str | None) -> bool:
    """True si dos enlaces apuntan al mismo vídeo (p. ej. youtu.be vs watch?v=)."""
    left = (a or "").strip()
    right = (b or "").strip()
    if not left or not right:
        return False
    if left == right:
        return True
    if is_youtube_url(left) and is_youtube_url(right):
        vid_left = _youtube_video_id(left)
        vid_right = _youtube_video_id(right)
        if vid_left and vid_right:
            return vid_left == vid_right
    if is_twitter_url(left) and is_twitter_url(right):
        tid_left = twitter_status_id(left)
        tid_right = twitter_status_id(right)
        if tid_left and tid_right:
            return tid_left == tid_right
    return left.rstrip("/") == right.rstrip("/")


def store_media_source(context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    """Guarda el enlace del último vídeo procesado por URL."""
    url = (url or "").strip()
    kind = media_source_kind(url)
    context.user_data["media_source_url"] = url
    context.user_data["media_source_kind"] = kind
    if kind == "youtube":
        vid = _youtube_video_id(url)
        if vid:
            context.user_data["media_source_yt_id"] = vid


def get_media_source(context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, str]:
    url = context.user_data.get("media_source_url")
    kind = context.user_data.get("media_source_kind") or ""
    if isinstance(url, str) and url.strip():
        return url.strip(), str(kind)
    return None, ""


def seek_url_for_time(context: ContextTypes.DEFAULT_TYPE, seconds: float) -> str | None:
    """URL para abrir el vídeo en ese instante (solo YouTube por ahora)."""
    _, kind = get_media_source(context)
    if kind != "youtube":
        return None

    vid = context.user_data.get("media_source_yt_id")
    if not isinstance(vid, str) or not _YT_ID_RE.match(vid):
        url, _ = get_media_source(context)
        vid = _youtube_video_id(url or "") if url else None
    if not vid:
        return None

    t = max(0, int(seconds))
    return f"https://www.youtube.com/watch?v={vid}&t={t}"


def seek_button_label(context: ContextTypes.DEFAULT_TYPE) -> str:
    kind = get_media_source(context)[1]
    if kind == "youtube":
        return "▶️ Acceder a esta parte en YouTube"
    return ""


def seek_hint_markdown(context: ContextTypes.DEFAULT_TYPE) -> str:
    """1–2 líneas reservadas en el mensaje cuando hay botón de enlace."""
    kind = get_media_source(context)[1]
    if kind == "youtube":
        return (
            "\n\n▶️ *Abrir en YouTube*\n"
            "_Pulsa el botón de abajo para ir a este momento del vídeo._"
        )
    return ""


def store_media_source_from_text(context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    url = extract_social_url(text or "")
    if url:
        store_media_source(context, url)
        return True
    return False
