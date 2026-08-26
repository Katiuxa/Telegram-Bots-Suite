import asyncio
import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import (
    EXPORT_TOC,
    TELEGRAM_SAFE_CHARS,
    TRANSCRIPT_BODY_MAX,
    TRANSCRIPT_INLINE_MAX_PARTS,
)
from bot.i18n import get_lang, t
from bot.i18n_progress import prog
from bot.services.transcript_active import (
    get_active_formatted,
    get_content_lang,
)
from bot.keyboards import (
    after_transcript_keyboard,
    summary_back_keyboard,
    summary_page_keyboard,
    transcript_page_keyboard,
)
from bot.services.summary_pages import (
    page_body as summary_page_body,
    store_summary_pages,
    summary_header,
)
from bot.services.transcript_pages import (
    page_body,
    store_transcript_pages,
    transcript_header,
)
from bot.services.text_chunks import split_for_telegram, split_moments_for_telegram
from bot.services.export_files import write_pdf, write_txt
from bot.services.metadata import export_file_prefix_from_context, get_document_metadata
from bot.services.format_timestamps import build_moment_blocks
from bot.services.format_timestamps import segments_from_stored
from bot.services.telegraph import publish_page
from bot.services.telegraph_format import build_transcript_telegraph

if TYPE_CHECKING:
    from bot.services.progress import ProgressReporter

logger = logging.getLogger(__name__)


async def send_text_chunks(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    header: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    lang = get_lang(context)
    parts = split_for_telegram(text)
    total = len(parts)
    for i, part in enumerate(parts, 1):
        if i == 1:
            body = header + part
        else:
            body = t("continues_part", lang, cur=i, total=total) + part
        try:
            await context.bot.send_message(
                chat_id,
                body,
                reply_markup=reply_markup if i == total else None,
            )
        except Exception:
            await context.bot.send_message(
                chat_id,
                body.replace("*", "").replace("_", ""),
                reply_markup=reply_markup if i == total else None,
            )


async def deliver_summary(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    summary: str,
) -> None:
    """Un mensaje con paginación; no parte el resumen en mensajes sueltos."""
    lang = get_lang(context)
    store_summary_pages(context, summary)
    flat = context.user_data["sum_parts"]
    n_pages = len(flat)
    body = summary_page_body(flat, 0)
    markup = (
        summary_page_keyboard(0, n_pages, lang)
        if n_pages > 1
        else summary_back_keyboard(lang)
    )
    text = summary_header(0, n_pages, lang) + body
    try:
        sent = await context.bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=markup,
        )
    except Exception:
        sent = await context.bot.send_message(
            chat_id,
            text.replace("*", "").replace("_", ""),
            reply_markup=markup,
        )
    context.user_data["sum_view_msg_id"] = sent.message_id
    context.user_data["sum_view_chat_id"] = chat_id


async def send_formatted_chat(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    formatted: str,
    engine: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    await send_text_chunks(chat_id, context, formatted, "", reply_markup)


def _transcript_view_payload(
    context: ContextTypes.DEFAULT_TYPE,
    formatted: str,
    *,
    page: int | None = None,
    engine: str = "",
) -> tuple[str, object, int, int] | None:
    if not formatted.strip():
        return None
    parts = split_for_telegram(formatted, TRANSCRIPT_BODY_MAX)
    store_transcript_pages(
        context,
        parts,
        engine=engine or context.user_data.get("tx_engine", ""),
    )
    flat = context.user_data["tx_parts"]
    n_pages = len(flat)
    if page is not None:
        from bot.services.transcript_pages import set_transcript_page

        set_transcript_page(context, page)
    from bot.services.transcript_pages import get_transcript_page

    page = get_transcript_page(context)
    lang = get_lang(context)
    body = page_body(flat, page)
    text = transcript_header(page, n_pages, lang, context=context) + body
    markup = transcript_page_keyboard(page, n_pages, lang, context=context)
    return text, markup, page, n_pages


async def _send_or_edit_transcript_view(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup,
    *,
    force_new: bool,
) -> bool:
    view_chat = context.user_data.get("tx_view_chat_id") or chat_id
    msg_id = context.user_data.get("tx_view_msg_id")

    if not force_new and msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=view_chat,
                message_id=msg_id,
                text=text,
                reply_markup=markup,
            )
            return True
        except Exception:
            pass

    try:
        sent = await context.bot.send_message(
            chat_id,
            text,
            reply_markup=markup,
        )
    except Exception:
        sent = await context.bot.send_message(
            chat_id,
            text.replace("*", "").replace("_", ""),
            reply_markup=markup,
        )
    context.user_data["tx_view_msg_id"] = sent.message_id
    context.user_data["tx_view_chat_id"] = chat_id
    return True


async def deliver_transcript_view(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    formatted: str | None = None,
    *,
    force_new: bool = False,
    reset_page: bool = True,
    engine: str = "",
) -> bool:
    """
    Muestra el texto activo (original o traducción) como mensaje del bot
    con paginación y botones, igual que la transcripción larga.
    """
    text_content = formatted if formatted is not None else get_active_formatted(context)
    payload = _transcript_view_payload(
        context,
        text_content,
        page=0 if reset_page else None,
        engine=engine,
    )
    if not payload:
        return False
    body_text, markup, _, _ = payload
    return await _send_or_edit_transcript_view(
        chat_id, context, body_text, markup, force_new=force_new
    )


async def open_transcript_view(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    reset_page: bool = True,
    force_new: bool = False,
) -> bool:
    """Abre o actualiza el visor paginado del texto activo (original o traducción)."""
    return await deliver_transcript_view(
        chat_id, context, reset_page=reset_page, force_new=force_new
    )


async def refresh_transcript_view(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Actualiza el visor paginado (p. ej. al cambiar idioma o traducción)."""
    return await deliver_transcript_view(chat_id, context, reset_page=True)


async def deliver_transcript(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    formatted: str,
    engine: str,
    progress: "ProgressReporter | None" = None,
) -> None:
    lang = get_lang(context)
    note = context.user_data.pop("auto_detect_note", None)
    if note:
        banner = t("auto_detect_banner", lang, detected=note["detected"])
        if note.get("auto_translated"):
            banner += t("auto_detect_translated", lang, target=note["target"])
        elif context.user_data.pop("auto_detect_translate_error", None):
            banner += t("auto_detect_translate_failed", lang, target=note["target"])
        else:
            banner += t("auto_detect_no_translate", lang, target=note["target"])
        try:
            await context.bot.send_message(chat_id, banner, parse_mode="Markdown")
        except Exception:
            await context.bot.send_message(
                chat_id, banner.replace("*", "").replace("_", "")
            )

    try:
        if progress:
            parts = split_for_telegram(formatted)
            total = max(len(parts), 1)
            for i, _ in enumerate(parts, 1):
                pct = 94 + int(5 * i / total)
                sub = (
                    prog("message_n_of_m", lang, cur=i, total=total)
                    if total > 1
                    else ""
                )
                await progress.set_real(
                    min(99, pct),
                    prog("sending_text", lang),
                    sub,
                    force=(i == 1),
                )

        segments = context.user_data.get("last_segments")

        use_paged_view = (
            len(split_for_telegram(formatted, TRANSCRIPT_BODY_MAX))
            > TRANSCRIPT_INLINE_MAX_PARTS
            or len(formatted) > TELEGRAM_SAFE_CHARS
        )
        if use_paged_view:
            await deliver_transcript_view(
                chat_id, context, formatted, force_new=True, engine=engine
            )
        else:
            await send_formatted_chat(
                chat_id, context, formatted, engine, reply_markup=None
            )
            await context.bot.send_message(
                chat_id,
                t("transcript_actions", lang),
                reply_markup=after_transcript_keyboard(lang, context=context),
            )

        if progress:
            await progress.done(prog("done", lang))

    except Exception as e:
        logger.exception("Error entregando transcripción")
        if progress:
            await progress.fail(prog("send_result_fail", lang), str(e)[:500])
        else:
            await context.bot.send_message(
                chat_id, prog("send_error_detail", lang, detail=e)
            )


async def deliver_moments_index(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    segments: list,
    progress: "ProgressReporter | None" = None,
) -> None:
    lang = get_lang(context)
    from bot.keyboards import index_toc_keyboard
    from bot.services.format_timestamps import segments_from_stored
    from bot.services.moments_view import format_index_toc, store_moments_view

    from bot.services.transcript_cache import (
        get_cached_index_blocks,
        store_index_cache,
    )

    if isinstance(segments, list) and segments and isinstance(segments[0], dict):
        segs = segments_from_stored(segments)
    else:
        segs = segments

    cached_blocks, _ = get_cached_index_blocks(context)
    from_cache = cached_blocks is not None

    if from_cache:
        blocks = cached_blocks
        if progress:
            await progress.set_real(50, prog("opening_index", lang), force=True)
    else:
        if progress:
            await progress.set_real(12, prog("organizing_chapters", lang), force=True)
        tx_lang = get_content_lang(context)
        blocks = await asyncio.to_thread(
            lambda: build_moment_blocks(segs, lang=tx_lang)
        )
        if not blocks:
            raise ValueError(prog("no_timestamps", lang))
        store_index_cache(context, blocks)

    try:
        if progress and not from_cache:
            await progress.set_real(35, prog("index_almost", lang), force=True)

        store_moments_view(context, blocks)
        total = len(blocks)

        if progress and not from_cache:
            await progress.set_real(45, prog("building_index", lang), force=True)

        text = format_index_toc(blocks, 0, lang=lang)
        sent = await context.bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=index_toc_keyboard(blocks, 0, lang=lang),
        )
        context.user_data["mom_view_msg_id"] = sent.message_id
        context.user_data["mom_view_chat_id"] = chat_id
        context.user_data["mom_mode"] = "toc"

        if progress:
            await progress.done(prog("index_done", lang, total=total))
    except Exception as e:
        if progress:
            await progress.fail(prog("fail_index", lang), str(e)[:400])
        raise


async def deliver_highlights(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    segments: list,
    progress: "ProgressReporter | None" = None,
) -> None:
    lang = get_lang(context)
    from bot.keyboards import highlights_toc_keyboard
    from bot.services.format_timestamps import segments_from_stored
    from bot.services.highlights import build_highlights
    from bot.services.highlights_view import format_highlights_toc, store_highlights_view

    from bot.services.transcript_cache import (
        get_cached_highlights,
        store_highlights_cache,
    )

    if isinstance(segments, list) and segments and isinstance(segments[0], dict):
        segs = segments_from_stored(segments)
    else:
        segs = segments

    formatted = get_active_formatted(context)
    cached_items, _ = get_cached_highlights(context)
    from_cache = cached_items is not None

    if from_cache:
        items = cached_items
        if progress:
            await progress.set_real(50, prog("opening_highlights", lang), force=True)
    else:
        if progress:
            await progress.set_real(15, prog("finding_highlights", lang), force=True)
        tx_lang = get_content_lang(context)
        items = await asyncio.to_thread(
            lambda: build_highlights(segs, formatted, lang=tx_lang)
        )
        if not items:
            raise ValueError(prog("no_highlights_extract", lang))
        store_highlights_cache(context, items)

    try:
        store_highlights_view(context, items)
        total = len(items)

        if progress and not from_cache:
            await progress.set_real(50, prog("building_highlights", lang), force=True)

        text = format_highlights_toc(items, 0, lang=lang)
        sent = await context.bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=highlights_toc_keyboard(items, 0, lang=lang),
        )
        context.user_data["hi_view_msg_id"] = sent.message_id
        context.user_data["hi_view_chat_id"] = chat_id
        context.user_data["hi_mode"] = "toc"

        if progress:
            await progress.done(prog("highlights_done", lang, total=total))
    except Exception as e:
        if progress:
            await progress.fail(prog("fail_highlights", lang), str(e)[:400])
        raise


async def deliver_session_mp3(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    progress: "ProgressReporter | None" = None,
    *,
    audio_title: str | None = None,
    audio_author: str | None = None,
    show_transcript_actions: bool = True,
    user_id: int | None = None,
) -> None:
    import asyncio

    from html import escape

    from bot.keyboards import after_transcript_keyboard, main_menu_inline
    from bot.services.mp3_meta import build_mp3_filename, clip_telegram_meta
    from bot.services.session_audio import get_session_mp3

    lang = get_lang(context)
    path = get_session_mp3(context)
    if not path:
        raise ValueError(t("no_session_audio", lang))

    label = t("btn_mp3", lang)
    resolved_title = clip_telegram_meta(audio_title or "")
    resolved_author = clip_telegram_meta(audio_author or "") if audio_author else ""
    display_title = resolved_title or label
    if resolved_title:
        filename = build_mp3_filename(resolved_title, resolved_author)
    elif path.suffix.lower() in {".mp3", ".m4a", ".aac", ".ogg"}:
        filename = path.name
    else:
        filename = "audio.mp3"
    from bot.config import EXTERNAL_UPLOAD_ENABLED, TELEGRAM_AUDIO_MAX_MB
    from bot.services.mp3_progress import map_send_inner

    max_bytes = TELEGRAM_AUDIO_MAX_MB * 1024 * 1024
    size = path.stat().st_size
    size_mb = size / (1024 * 1024)

    if size > max_bytes and not EXTERNAL_UPLOAD_ENABLED:
        raise ValueError(t("session_audio_too_big", lang))

    try:
        if progress:
            await progress.set_real(
                map_send_inner(5), prog("sending_file", lang), force=True
            )

        if size <= max_bytes:
            if progress:
                await progress.set_real(
                    map_send_inner(35), prog("sending_file", lang), force=True
                )
            with path.open("rb") as audio_file:
                await context.bot.send_audio(
                    chat_id,
                    audio=audio_file,
                    filename=filename,
                    title=display_title,
                    performer=resolved_author or None,
                )
            sent_text = t("file_sent", lang, label=label)
        else:
            from bot.services.external_upload import ExternalLink, upload_video_external

            loop = asyncio.get_running_loop()

            def _upload_progress(pct: int, sub: str) -> None:
                if not progress:
                    return
                mapped = map_send_inner(40 + int(55 * max(0, min(100, pct)) / 100))
                asyncio.run_coroutine_threadsafe(
                    progress.set_real(mapped, sub or prog("uploading_external", lang)),
                    loop,
                )

            if progress:
                await progress.set_real(
                    map_send_inner(40), prog("uploading_external", lang), force=True
                )

            link: ExternalLink = await asyncio.to_thread(
                upload_video_external,
                path,
                user_id,
                on_progress=_upload_progress,
            )
            safe_title = escape(display_title[:900])
            safe_url = link.url.replace("&", "&amp;")
            lines = [
                t("mp3_external_header", lang, title=safe_title, size=f"{size_mb:.1f}"),
                t(
                    "mp3_external_server",
                    lang,
                    provider=escape(link.provider),
                    max_mb=link.max_mb,
                ),
                t("mp3_external_expiry", lang, expiry=escape(link.expiry_text)),
                t("mp3_external_howto", lang),
                f'<a href="{safe_url}">{t("mp3_external_download", lang)}</a>',
                link.url,
            ]
            await context.bot.send_message(
                chat_id,
                "\n".join(lines),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent_text = t("mp3_external_sent", lang, label=label)

        await context.bot.send_message(
            chat_id,
            sent_text,
            reply_markup=(
                after_transcript_keyboard(lang, context=context)
                if show_transcript_actions
                else main_menu_inline(lang)
            ),
        )
        if progress:
            await progress.done(prog("file_ready", lang, label=label))
        from bot.services.audit_log import audit_out

        audit_out(
            None,
            uid=user_id,
            action="sent_mp3",
            response=f"{filename} ({size_mb:.1f} MB) title={display_title}",
        )
    except Exception as e:
        if progress:
            await progress.fail(prog("file_create_fail", lang, label=label), str(e)[:400])
        from bot.services.audit_log import audit_out

        audit_out(None, uid=user_id, action="mp3_fail", response=str(e)[:400])
        raise


async def deliver_file(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    content: str,
    file_kind: str,
    progress: "ProgressReporter | None" = None,
    label: str = "Archivo",
) -> None:
    lang = get_lang(context)
    files: list[Path] = []
    ext = "pdf" if file_kind.endswith("_pdf") or file_kind == "pdf" else "txt"
    prefix = file_kind.replace("_pdf", "").replace("_txt", "")
    if prefix in ("index", "moments"):
        prefix = "indice"
    elif prefix == "highlights":
        prefix = "highlights"
    elif prefix in ("pdf", "txt", "transcripcion"):
        prefix = "transcripcion"
    is_transcript_export = prefix == "transcripcion"
    doc_meta = get_document_metadata(context) if is_transcript_export else {}
    file_prefix = export_file_prefix_from_context(context, prefix)
    doc_title = doc_meta.get("title")
    doc_description = doc_meta.get("description")
    doc_source = (
        f"{t('metainfo_source', lang)}: {doc_meta['source']}"
        if doc_meta.get("source")
        else None
    )
    try:
        if progress:
            await progress.set_real(15, prog("preparing_file_step", lang), force=True)
        if ext == "txt":
            if progress:
                await progress.set_real(55, prog("creating_txt", lang))
            files.append(
                write_txt(
                    content,
                    prefix=file_prefix,
                    title=doc_title,
                    description=doc_description,
                    source=doc_source,
                )
            )
        else:
            if progress:
                await progress.set_real(55, prog("creating_pdf", lang))
            try:
                if is_transcript_export:
                    from bot.services.pdf_export import export_transcript_pdf

                    files.append(
                        await asyncio.to_thread(
                            export_transcript_pdf,
                            title=doc_title or "Transcripción",
                            description=doc_description or "",
                            body=content,
                            include_toc=EXPORT_TOC,
                            prefix=file_prefix,
                            source=doc_source,
                        )
                    )
                else:
                    files.append(
                        write_pdf(
                            content,
                            prefix=file_prefix,
                            title=doc_title,
                            description=doc_description,
                            source=doc_source,
                        )
                    )
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception("PDF export failed: %s", e)
                files.append(
                    write_txt(
                        content,
                        prefix=file_prefix,
                        title=doc_title,
                        description=doc_description,
                        source=doc_source,
                    )
                )
                await context.bot.send_message(chat_id, t("pdf_fallback_txt", lang))
        if progress:
            await progress.set_real(88, prog("sending_file", lang))
        for f in files:
            with f.open("rb") as doc:
                await context.bot.send_document(chat_id, doc, filename=f.name)
            try:
                f.unlink()
            except OSError:
                pass

        await context.bot.send_message(
            chat_id,
            t("file_sent", lang, label=label),
            reply_markup=after_transcript_keyboard(lang, context=context),
        )
        if progress:
            await progress.done(prog("file_ready", lang, label=label))
    except Exception as e:
        if progress:
            await progress.fail(prog("file_create_fail", lang, label=label), str(e)[:400])


async def deliver_telegraph_read(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    progress: "ProgressReporter | None" = None,
) -> None:
    from bot.services.transcript_cache import (
        get_cached_telegraph_url,
        store_telegraph_cache,
    )

    lang = get_lang(context)

    from bot.services.transcript_active import get_active_segments_stored

    active_segments = get_active_segments_stored(context)
    if not active_segments:
        raise ValueError(t("no_transcript_saved", lang))
    content_lang = get_content_lang(context)

    url = get_cached_telegraph_url(context)
    if not url:
        if progress:
            await progress.set_real(20, t("progress_read_tg", lang), force=True)

        def _publish() -> str | None:
            segs = segments_from_stored(active_segments)
            title, nodes = build_transcript_telegraph(segs, lang=content_lang)
            return publish_page(title, nodes)

        if progress:
            await progress.set_real(55, t("progress_read_tg", lang))
        url = await asyncio.to_thread(_publish)
        if not url:
            raise ValueError(t("read_tg_fail", lang))
        store_telegraph_cache(context, url)

    if progress:
        await progress.set_real(90, t("progress_read_tg", lang))
    await context.bot.send_message(
        chat_id,
        t("read_tg_ready", lang, url=url),
        parse_mode="Markdown",
        disable_web_page_preview=False,
        reply_markup=after_transcript_keyboard(lang, context=context),
    )
    if progress:
        await progress.done(t("read_tg_done", lang))
