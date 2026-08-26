"""Enviar audio descargado: un solo archivo completo (MP3, duración íntegra)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from telegram.ext import ContextTypes

from bot.config import TELEGRAM_AUDIO_MAX_MB, TEMP_DIR
from bot.i18n import get_lang, t
from bot.i18n_progress import prog
from bot.services.job_cancel import check_cancelled
from bot.services.killable_thread import run_killable
from bot.services.session_audio import _SESSION_MP3_KEY, _to_mp3

logger = logging.getLogger(__name__)

_MAX_BYTES = TELEGRAM_AUDIO_MAX_MB * 1024 * 1024
_SEND_AUDIO_EXTS = frozenset({".mp3", ".m4a", ".ogg", ".opus"})


async def deliver_downloaded_audio(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    source_path: Path,
    progress=None,
    *,
    cancel_event=None,
) -> None:
    """Un único archivo con toda la duración; re-codifica solo si supera límite Telegram."""
    from bot.keyboards import main_menu_inline

    lang = get_lang(context)
    if not source_path.is_file():
        raise ValueError(t("no_session_audio", lang))

    label = t("btn_link_mp3_only", lang)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    loop = asyncio.get_running_loop() if progress else None
    size = source_path.stat().st_size
    out = source_path
    encoded = False

    if size > _MAX_BYTES:
        out = TEMP_DIR / f"audio_{chat_id}_{stamp}.mp3"

        def _mp3_progress(pct: int, sub: str) -> None:
            if not progress:
                return
            mapped = 52 + int(43 * pct / 100)
            asyncio.run_coroutine_threadsafe(
                progress.set_real(mapped, prog("creating_mp3", lang), sub),
                loop,
            )

        if progress:
            await progress.set_real(52, prog("creating_mp3", lang), force=True)

        check_cancelled(cancel_event)

        def _encode() -> None:
            _to_mp3(
                source_path,
                out,
                max_mb=TELEGRAM_AUDIO_MAX_MB,
                on_progress=_mp3_progress if progress else None,
                cancel_event=cancel_event,
            )

        await run_killable(cancel_event, _encode)
        encoded = True
    elif progress:
        await progress.set_real(70, prog("sending_file", lang), force=True)

    check_cancelled(cancel_event)

    if not out.is_file():
        raise RuntimeError("No se pudo preparar el audio.")

    if out.stat().st_size > _MAX_BYTES:
        if encoded:
            out.unlink(missing_ok=True)
        raise ValueError(t("session_audio_too_big", lang))

    if progress:
        await progress.set_real(96, prog("sending_file", lang), force=True)

    ext = out.suffix.lower()
    with out.open("rb") as fh:
        if ext in _SEND_AUDIO_EXTS:
            await context.bot.send_audio(
                chat_id,
                audio=fh,
                filename=out.name,
                title=label,
            )
        else:
            await context.bot.send_document(
                chat_id,
                document=fh,
                filename=out.name,
            )

    await context.bot.send_message(
        chat_id,
        t("file_sent", lang, label=label),
        reply_markup=main_menu_inline(lang),
    )
    if progress:
        await progress.done(prog("file_ready", lang, label=label))

    if encoded and out.is_file():
        context.user_data[_SESSION_MP3_KEY] = str(out)
