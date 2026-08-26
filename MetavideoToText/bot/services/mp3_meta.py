"""Metadatos opcionales (título / autor) al exportar MP3."""

from __future__ import annotations

import re
import threading

from telegram.ext import ContextTypes

_AWAIT_TITLE = "awaiting_mp3_title"
_AWAIT_AUTHOR = "awaiting_mp3_author"
_TITLE = "mp3_meta_title"
_AUTHOR = "mp3_meta_author"
_DEFAULT_TITLE = "mp3_default_title"
_LINK_ONLY = "mp3_link_only"


_PENDING_URL = "pending_link_mp3_url"
_READY_URL = "link_mp3_ready_url"
_SESSION_URL = "link_mp3_session_url"
_SESSION_SOURCE_ID = "link_mp3_session_source_id"
_LINK_MP3_GEN = "link_mp3_generation"
_LINK_MP3_DL_STATE = "link_mp3_dl_state"
_LINK_MP3_DL_ERROR = "link_mp3_dl_error"
_PREFETCH_CANCEL = "link_mp3_prefetch_cancel"


def clear_mp3_meta_prompt(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quita solo el estado de espera de texto (conserva título/autor ya escritos)."""
    context.user_data.pop(_AWAIT_TITLE, None)
    context.user_data.pop(_AWAIT_AUTHOR, None)


def clear_mp3_meta_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_mp3_meta_prompt(context)
    for key in (_TITLE, _AUTHOR, _LINK_ONLY):
        context.user_data.pop(key, None)


def set_pending_link_mp3_url(context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    u = (url or "").strip()
    if u:
        context.user_data[_PENDING_URL] = u


def get_pending_link_mp3_url(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    url = context.user_data.get(_PENDING_URL)
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def clear_pending_link_mp3_url(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_PENDING_URL, None)


def clear_link_mp3_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_pending_link_mp3_url(context)
    clear_mp3_meta_flow(context)


def set_link_mp3_ready_url(context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    u = (url or "").strip()
    if u:
        context.user_data[_READY_URL] = u


def get_link_mp3_ready_url(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    url = context.user_data.get(_READY_URL)
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def clear_link_mp3_ready_url(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_READY_URL, None)


def set_link_mp3_prefetch_cancel_event(
    context: ContextTypes.DEFAULT_TYPE, ev: threading.Event | None
) -> None:
    if ev is None:
        context.user_data.pop(_PREFETCH_CANCEL, None)
    else:
        context.user_data[_PREFETCH_CANCEL] = ev


def cancel_link_mp3_prefetch(context: ContextTypes.DEFAULT_TYPE) -> None:
    ev = context.user_data.get(_PREFETCH_CANCEL)
    if isinstance(ev, threading.Event):
        ev.set()
    context.user_data.pop(_PREFETCH_CANCEL, None)
    context.user_data.pop(_LINK_MP3_DL_STATE, None)
    try:
        from bot.services.job_cancel import terminate_all

        terminate_all()
    except Exception:
        pass


def bump_link_mp3_generation(context: ContextTypes.DEFAULT_TYPE) -> int:
    gen = int(context.user_data.get(_LINK_MP3_GEN, 0)) + 1
    context.user_data[_LINK_MP3_GEN] = gen
    return gen


def get_link_mp3_generation(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get(_LINK_MP3_GEN, 0))


def bind_link_mp3_session(
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    source_id: str | None = None,
) -> None:
    u = (url or "").strip()
    if u:
        context.user_data[_SESSION_URL] = u
    sid = (source_id or "").strip()
    if sid:
        context.user_data[_SESSION_SOURCE_ID] = sid
    elif u:
        from bot.services.source_links import youtube_video_id

        vid = youtube_video_id(u)
        if vid:
            context.user_data[_SESSION_SOURCE_ID] = vid


def clear_link_mp3_session_url(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop(_SESSION_URL, None)
    context.user_data.pop(_SESSION_SOURCE_ID, None)


def link_mp3_session_matches(
    context: ContextTypes.DEFAULT_TYPE, url: str | None
) -> bool:
    """True si el audio en sesión pertenece a este enlace (no solo ready_url)."""
    from bot.services.session_audio import has_session_audio
    from bot.services.source_links import same_media_url, youtube_video_id

    if not has_session_audio(context) or not url:
        return False
    bound = context.user_data.get(_SESSION_URL)
    if not isinstance(bound, str) or not bound.strip():
        return False
    if not same_media_url(bound.strip(), url):
        return False
    expected_id = youtube_video_id(url)
    stored_id = context.user_data.get(_SESSION_SOURCE_ID)
    if expected_id:
        if not isinstance(stored_id, str) or stored_id.strip() != expected_id:
            return False
    return True


def clear_stale_link_mp3_session(
    context: ContextTypes.DEFAULT_TYPE, url: str | None
) -> None:
    """Quita audio de sesión que no corresponde al enlace pedido."""
    from bot.services.session_audio import clear_session_audio, has_session_audio

    if not has_session_audio(context):
        return
    if url and link_mp3_session_matches(context, url):
        return
    clear_session_audio(context)
    clear_link_mp3_session_url(context)
    clear_link_mp3_ready_url(context)
    context.user_data.pop(_LINK_MP3_DL_STATE, None)


def reset_link_mp3_workflow(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Nuevo enlace: cancelar prefetch anterior y descartar MP3 previo."""
    from bot.services.session_audio import clear_session_audio

    cancel_link_mp3_prefetch(context)
    bump_link_mp3_generation(context)
    clear_link_mp3_state(context)
    clear_link_mp3_ready_url(context)
    clear_link_mp3_session_url(context)
    clear_session_audio(context)
    context.user_data.pop(_DEFAULT_TITLE, None)
    context.user_data.pop(_LINK_MP3_DL_ERROR, None)


def is_awaiting_mp3_meta(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(
        context.user_data.get(_AWAIT_TITLE) or context.user_data.get(_AWAIT_AUTHOR)
    )


def is_mp3_link_only(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get(_LINK_ONLY))


def start_mp3_title_prompt(
    context: ContextTypes.DEFAULT_TYPE, *, link_only: bool = False
) -> None:
    clear_mp3_meta_prompt(context)
    context.user_data.pop(_TITLE, None)
    context.user_data.pop(_AUTHOR, None)
    context.user_data[_AWAIT_TITLE] = True
    if link_only:
        context.user_data[_LINK_ONLY] = True
    else:
        context.user_data.pop(_LINK_ONLY, None)


def store_mp3_default_title(context: ContextTypes.DEFAULT_TYPE, title: str | None) -> None:
    t = (title or "").strip()
    if t:
        context.user_data[_DEFAULT_TITLE] = t[:200]
    else:
        context.user_data.pop(_DEFAULT_TITLE, None)


def sanitize_filename_part(text: str, *, max_len: int = 72) -> str:
    s = (text or "").strip()
    if not s:
        return "audio"
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:max_len] if s else "audio") or "audio"


def build_mp3_filename(title: str, author: str) -> str:
    t = sanitize_filename_part(title)
    a = sanitize_filename_part(author)
    if a and a != "audio":
        return f"{t} - {a}.mp3"
    return f"{t}.mp3"


def clip_telegram_meta(text: str, limit: int = 64) -> str:
    s = (text or "").strip()
    return s[:limit] if s else ""


def clear_mp3_user_fields(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Quita título/artista escritos por el usuario (conserva el default del vídeo)."""
    context.user_data.pop(_TITLE, None)
    context.user_data.pop(_AUTHOR, None)


def _fallback_mp3_title(context: ContextTypes.DEFAULT_TYPE) -> str:
    default = str(context.user_data.get(_DEFAULT_TITLE) or "").strip()
    if default:
        return default
    from bot.services.metadata import get_document_metadata

    doc = get_document_metadata(context).get("title", "")
    if isinstance(doc, str) and doc.strip():
        return doc.strip()
    return ""


def resolve_mp3_title(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Título: el del usuario si lo escribió; si no, el del vídeo/enlace."""
    user = str(context.user_data.get(_TITLE) or "").strip()
    if user:
        return user[:200]
    return _fallback_mp3_title(context)


def resolve_mp3_author(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Artista: solo lo que escribió el usuario; vacío si lo omitió."""
    return str(context.user_data.get(_AUTHOR) or "").strip()


def get_resolved_mp3_meta(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str]:
    return resolve_mp3_title(context), resolve_mp3_author(context)


def apply_mp3_direct_defaults(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Descarga sin datos: usar título del vídeo y artista vacío."""
    clear_mp3_meta_prompt(context)
    clear_mp3_user_fields(context)
    context.user_data.pop(_DEFAULT_TITLE, None)


def try_handle_mp3_meta_text(
    context: ContextTypes.DEFAULT_TYPE, text: str
) -> str | None:
    """
    Guarda título o autor según el paso (vacío = usar valor por defecto / omitir).
    Devuelve: 'need_author' | 'ready' | None si no aplica.
    """
    msg = (text or "").strip()

    if context.user_data.get(_AWAIT_TITLE):
        if msg:
            context.user_data[_TITLE] = msg[:200]
        context.user_data.pop(_AWAIT_TITLE, None)
        context.user_data[_AWAIT_AUTHOR] = True
        return "need_author"

    if context.user_data.get(_AWAIT_AUTHOR):
        if msg:
            context.user_data[_AUTHOR] = msg[:200]
        context.user_data.pop(_AWAIT_AUTHOR, None)
        return "ready"

    return None


def get_mp3_meta(context: ContextTypes.DEFAULT_TYPE) -> tuple[str, str]:
    return get_resolved_mp3_meta(context)
