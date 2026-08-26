import asyncio
import logging
import threading
from pathlib import Path

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from bot.config import (
    GROQ_API_KEY,
    MAX_TELEGRAM_AUDIO_MB,
    MAX_TELEGRAM_FILE_MB,
    MAX_VIDEO_DURATION_SEC,
    TEMP_DIR,
)
from bot.handlers.common import (
    apply_ui_lang_change,
    send_help,
    send_main_menu,
    send_start,
)
from bot.i18n import LANG_MENU, SUPPORTED, active_lang_label, ensure_user_lang, get_lang, t
from bot.i18n_progress import prog
from bot.services.delivery import (
    deliver_file,
    deliver_session_mp3,
    deliver_highlights,
    deliver_moments_index,
    deliver_summary,
    deliver_telegraph_read,
    deliver_transcript,
    deliver_transcript_view,
    refresh_transcript_view,
)
from bot.services.cleanup_temp import cleanup_old_files
from bot.services.format_text import format_transcript
from bot.services.format_timestamps import (
    build_moment_blocks,
    format_moments_plain,
    segments_from_stored,
    store_segments,
)
from bot.services.highlights import build_highlights, format_highlights_plain
from bot.services.download_control import download_from_link_killable
from bot.services.media import (
    audio_suffix_for_document,
    extract_social_url,
    telegram_message_is_audio,
    is_youtube_url,
    to_wav_16k,
)
from bot.services.source_links import clear_media_source, store_media_source
from bot.services.progress import ProgressReporter, format_bytes, thread_safe_callback
from bot.services.telegram_download import download_to_path
from bot.services.summarize import summarize_text
from bot.services.transcript_active import (
    VARIANT_ORIGINAL,
    get_active_formatted,
    get_active_segments,
    get_active_segments_stored,
    get_content_lang,
    get_source_lang,
    has_translation,
    init_transcript_session,
    rebuild_formatted_from_segments,
    segments_to_stored,
    set_variant,
    store_translation,
    variant_button_label,
)
from bot.services.orthography import restore_formatted_orthography, restore_segments_orthography
from bot.services.transcript_lang import (
    detected_language_label,
    get_transcript_lang,
    is_auto_detect,
    is_supported_source,
    normalize_source_lang,
    polish_lang,
)
from bot.services.translate import TranslationError, translate_formatted_text, translate_segments
from bot.services.transcribe import (
    JobCancelled,
    TranscriptSegment,
    TranscriptionError,
    transcribe_audio,
)
from bot.services.killable_thread import run_killable
from bot.services.user_busy import (
    begin_heavy_job,
    busy_message,
    cancelled_message,
    end_heavy_job,
    force_end_heavy_job,
    get_active_progress,
    get_cancel_event,
    get_heavy_job_id,
    has_cached_transcript,
    is_heavy_busy,
    reject_if_heavy_busy,
    request_cancel,
    set_active_progress,
    should_block_callback,
)

logger = logging.getLogger(__name__)

def _file_too_big_message(
    lang: str, *, mb: float | None = None, max_mb: int | None = None
) -> str:
    cap = max_mb if max_mb is not None else MAX_TELEGRAM_FILE_MB
    head = (
        prog("file_too_big_mb", lang, mb=mb)
        if mb is not None
        else ""
    )
    return (
        f"{head}\n\n{prog('file_too_big_help', lang, max_mb=cap)}"
    ).strip()


def _mb(size_bytes: int | None) -> float:
    if not size_bytes:
        return 0.0
    return size_bytes / (1024 * 1024)


def _check_telegram_size(
    size_bytes: int | None, lang: str, *, max_mb: int | None = None
) -> None:
    limit_mb = max_mb if max_mb is not None else MAX_TELEGRAM_FILE_MB
    if size_bytes and size_bytes > limit_mb * 1024 * 1024:
        raise ValueError(_file_too_big_message(lang, mb=_mb(size_bytes), max_mb=limit_mb))


def _cleanup(*paths: Path) -> None:
    for p in paths:
        try:
            if p.exists():
                p.unlink()
        except OSError:
            pass


def _raise_if_cancelled(context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.services.job_cancel import check_cancelled

    check_cancelled(get_cancel_event(context))


async def run_transcription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    source_path: Path | None,
    label: str,
    progress: ProgressReporter,
    *,
    cancel_event: threading.Event | None = None,
    precomputed: tuple[list, str] | None = None,
) -> None:
    chat = update.effective_chat
    wav = None

    loop = asyncio.get_running_loop()
    cancel_ev = cancel_event or get_cancel_event(context)
    prog_cb = thread_safe_callback(loop, progress, cancel_ev)

    try:
        _raise_if_cancelled(context)
        tx_mode = get_transcript_lang(context)
        auto_mode = is_auto_detect(tx_mode)

        if precomputed is not None:
            segments, detected = precomputed
            await progress.set_real(80, progress.p("polishing_text"), force=True)
        else:
            if source_path is None:
                raise RuntimeError("Falta audio para transcribir")
            await progress.set_real(50, progress.p("extracting_audio"), force=True)

            def _extract_wav() -> Path:
                def on_extract(pct: int, sub: str) -> None:
                    if cancel_ev and cancel_ev.is_set():
                        raise JobCancelled()
                    prog_cb(
                        50 + int(7 * pct / 100),
                        progress.p("extracting_audio"),
                        sub,
                    )

                return to_wav_16k(
                    source_path, on_progress=on_extract, cancel_event=cancel_ev
                )

            wav = await asyncio.to_thread(_extract_wav)
            _raise_if_cancelled(context)

            try:
                segments, detected = await asyncio.to_thread(
                    lambda: transcribe_audio(
                        wav, prog_cb, cancel_ev, language=tx_mode
                    )
                )
            except TranscriptionError:
                from bot.services.media import is_youtube_shorts_url, is_youtube_url
                from bot.services.source_links import get_media_source
                from bot.services.youtube_captions import try_fetch_youtube_captions

                src, _ = get_media_source(context)
                if not (src and is_youtube_url(src)) or is_youtube_shorts_url(src):
                    raise
                logger.warning(
                    "Whisper falló; subtítulos auto solo en vídeo largo %s", src
                )
                await progress.set_real(72, progress.p("youtube_captions"), force=True)
                caps = await asyncio.to_thread(
                    try_fetch_youtube_captions, src, tx_mode, allow_auto=True
                )
                if not caps:
                    raise
                segments, detected = caps
            _raise_if_cancelled(context)

        if auto_mode:
            source_lang = normalize_source_lang(detected) if detected else "en"
        else:
            source_lang = tx_mode
        fmt_lang = polish_lang(source_lang)
        fmt_fast = auto_mode or not is_supported_source(source_lang)

        await progress.set_real(86, progress.p("polishing_text"), force=True)
        segments = await asyncio.to_thread(
            restore_segments_orthography, segments, source_lang
        )
        _raise_if_cancelled(context)

        await progress.set_real(90, progress.p("polishing_text"), force=True)
        formatted = await asyncio.to_thread(
            format_transcript, segments, lang=fmt_lang, fast=fmt_fast
        )
        formatted = await asyncio.to_thread(
            restore_formatted_orthography, formatted, source_lang
        )
        if not formatted.strip():
            await progress.fail(
                progress.p("fail_transcription_empty"),
                progress.p("fail_transcription_empty_hint"),
            )
            return

        stored = store_segments(segments)
        init_transcript_session(context, stored, formatted, source_lang)

        ui_lang = get_lang(context)
        detected_label = detected_language_label(source_lang, ui_lang)
        deliver_formatted = formatted
        # Sin auto-traducción: el usuario usa Traducir… si la quiere
        context.user_data["auto_detect_note"] = {
            "detected": detected_label,
            "auto_translated": False,
            "target": active_lang_label(ui_lang),
        } if auto_mode else None

        from bot.services.formatter import plain_for_document
        from bot.services.metadata import (
            apply_metadata_updates,
            finalize_transcript_document,
            get_document_metadata,
            maybe_generate_auto_pdf,
        )
        from bot.services.source_links import get_media_source

        source_url, _ = get_media_source(context)
        pdf_path = None
        try:
            _, meta_updates = await finalize_transcript_document(
                formatted=formatted,
                lang=source_lang,
                source=source_url,
                label=label,
            )
            apply_metadata_updates(context, meta_updates)
            doc_meta = get_document_metadata(context)
            pdf_path = await maybe_generate_auto_pdf(
                context,
                title=doc_meta.get("title", ""),
                description=doc_meta.get("description", ""),
                body_plain_len=len(plain_for_document(formatted)),
            )
        except Exception:
            logger.exception("Metadatos automáticos")
        from bot.services.mp3_meta import clear_mp3_meta_flow

        clear_mp3_meta_flow(context)
        from bot.services.session_audio import store_session_audio_source

        await deliver_transcript(
            chat.id, context, deliver_formatted, detected or "", progress=progress
        )

        if pdf_path and pdf_path.is_file():
            try:
                with pdf_path.open("rb") as doc:
                    await context.bot.send_document(
                        chat.id, doc, filename=pdf_path.name
                    )
            except Exception:
                logger.exception("Envío AUTO_PDF")

        if source_path is not None:
            await asyncio.to_thread(
                store_session_audio_source, context, chat.id, source_path, wav
            )
    except JobCancelled:
        from bot.services.job_cancel import terminate_all

        terminate_all()
        await progress.cancelled()
    except TranscriptionError as e:
        await progress.fail(progress.p("fail_transcription"), str(e)[:3500])
    except Exception as e:
        logger.exception("Error en transcripción")
        await progress.fail(
            progress.p("fail_process"),
            f"{e}\n\n{progress.p('fail_process_hint')}",
        )
    finally:
        if source_path is not None:
            _cleanup(source_path)
        if wav:
            _cleanup(wav)
        await asyncio.to_thread(cleanup_old_files)


async def download_telegram_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    suffix: str,
    progress: ProgressReporter,
    file_size: int | None = None,
    *,
    media: str = "default",
    cancel_event: threading.Event | None = None,
) -> Path:
    lang = progress._lang
    if media == "audio":
        # Intentar descargar aunque el tamaño declarado sea grande (límite real: Telegram)
        if file_size and file_size <= MAX_TELEGRAM_AUDIO_MB * 1024 * 1024:
            pass
    else:
        _check_telegram_size(file_size, lang)
    await progress.set_real(12, progress.p("downloading"), force=True)
    try:
        tg_file = await context.bot.get_file(file_id)
    except BadRequest as e:
        if "too big" in str(e).lower():
            cap = MAX_TELEGRAM_AUDIO_MB if media == "audio" else MAX_TELEGRAM_FILE_MB
            raise ValueError(
                prog("file_too_big_tg", lang, max_mb=cap)
                + prog("file_too_big_help", lang, max_mb=cap)
            ) from e
        raise
    dest = TEMP_DIR / f"{file_id}{suffix}"
    if tg_file.file_path:
        try:
            await download_to_path(
                bot_token=context.bot.token,
                file_path=tg_file.file_path,
                dest=dest,
                file_size=file_size or tg_file.file_size,
                progress=progress,
                cancel_event=cancel_event or get_cancel_event(context),
                lang=lang,
            )
        except JobCancelled:
            raise
        except Exception:
            logger.warning(
                "Descarga streaming falló, uso método clásico de Telegram"
            )
            if cancel_event and cancel_event.is_set():
                raise JobCancelled()
            await tg_file.download_to_drive(custom_path=str(dest))
            if cancel_event and cancel_event.is_set():
                raise JobCancelled()
            await progress.set_real(22, progress.p("downloading"), force=True)
    else:
        await tg_file.download_to_drive(custom_path=str(dest))
        await progress.set_real(20, progress.p("downloading"), force=True)
    size = dest.stat().st_size if dest.exists() else 0
    await progress.set_real(
        28,
        progress.p("download_ready"),
        format_bytes(size),
        force=True,
    )
    return dest


async def handle_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    was_busy = is_heavy_busy(context)

    if query:
        try:
            await query.answer(
                prog("cancelling", get_lang(context))
                if was_busy
                else prog("nothing_running", get_lang(context)),
                show_alert=not was_busy,
            )
        except Exception:
            pass

    from bot.services.job_cancel import terminate_all

    from bot.services.mp3_meta import clear_mp3_meta_flow

    request_cancel(context)
    terminate_all()
    force_end_heavy_job(context)
    clear_mp3_meta_flow(context)

    if not was_busy:
        if update.effective_chat:
            await update.effective_chat.send_message(
                prog("state_cleared", get_lang(context)), parse_mode="Markdown"
            )
        return
    progress = get_active_progress(context)
    if progress is not None:
        await progress.cancelled()
    elif query and query.message:
        try:
            await query.edit_message_text(
                cancelled_message(get_lang(context)), parse_mode="Markdown", reply_markup=None
            )
        except Exception:
            if update.effective_chat:
                await update.effective_chat.send_message(
                    cancelled_message(get_lang(context)), parse_mode="Markdown"
                )
    elif update.effective_chat:
        await update.effective_chat.send_message(
            cancelled_message(get_lang(context)), parse_mode="Markdown"
        )

    context.user_data.pop("awaiting_search", None)


def _store_pending_telegram_job(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    file_id: str,
    suffix: str,
    file_size: int | None,
    media: str,
    label: str,
    duration: int | None = None,
) -> None:
    context.user_data["pending_job"] = {
        "kind": "telegram",
        "file_id": file_id,
        "suffix": suffix,
        "file_size": file_size,
        "media": media,
        "label": label,
        "duration": duration,
    }


async def _prompt_audio_lang(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, intro: str | None = None
) -> None:
    from bot.keyboards import audio_lang_keyboard

    lang = get_lang(context)
    chat = update.effective_chat
    text = intro or t("audio_lang_prompt", lang)
    await chat.send_message(
        text,
        parse_mode="Markdown",
        reply_markup=audio_lang_keyboard(lang),
    )


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg:
        return

    lang = get_lang(context)
    if await reject_if_heavy_busy(update, context):
        return
    clear_media_source(context)
    from bot.services.mp3_meta import store_mp3_default_title

    default_title = _telegram_default_mp3_title(msg)
    if default_title:
        store_mp3_default_title(context, default_title)

    file_id = None
    suffix = ".ogg"
    file_size = None
    if msg.voice:
        file_id = msg.voice.file_id
        file_size = msg.voice.file_size
    elif msg.audio:
        file_id = msg.audio.file_id
        file_size = msg.audio.file_size
        suffix = Path(msg.audio.file_name or "audio.mp3").suffix or ".mp3"
    elif msg.document:
        doc_suffix = audio_suffix_for_document(
            msg.document.file_name, msg.document.mime_type
        )
        if not doc_suffix:
            await msg.reply_text(t("send_audio", lang))
            return
        file_id = msg.document.file_id
        file_size = msg.document.file_size
        suffix = doc_suffix
    else:
        await msg.reply_text(t("send_audio", lang))
        return

    _store_pending_telegram_job(
        context,
        file_id=file_id,
        suffix=suffix,
        file_size=file_size,
        media="audio",
        label="Audio",
    )
    await _prompt_audio_lang(update, context)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await reject_if_heavy_busy(update, context):
        return
    clear_media_source(context)
    msg = update.message
    lang = get_lang(context)
    try:
        file_id = None
        suffix = ".mp4"
        duration = None
        file_size = None
        if msg.video:
            file_id = msg.video.file_id
            duration = msg.video.duration
            file_size = msg.video.file_size
        elif msg.video_note:
            file_id = msg.video_note.file_id
            duration = msg.video_note.duration
            file_size = msg.video_note.file_size
        elif msg.document and (msg.document.mime_type or "").startswith("video/"):
            file_id = msg.document.file_id
            file_size = msg.document.file_size
            suffix = Path(msg.document.file_name or "video.mp4").suffix or ".mp4"
        else:
            await msg.reply_text(t("send_video", lang))
            return

        from bot.services.mp3_meta import store_mp3_default_title

        default_title = _telegram_default_mp3_title(msg)
        if default_title:
            store_mp3_default_title(context, default_title)
        _check_telegram_size(file_size, lang)
        if duration and duration > MAX_VIDEO_DURATION_SEC:
            await msg.reply_text(
                prog(
                    "video_too_long",
                    lang,
                    minutes=MAX_VIDEO_DURATION_SEC // 60,
                )
            )
            return

        _store_pending_telegram_job(
            context,
            file_id=file_id,
            suffix=suffix,
            file_size=file_size,
            media="video",
            label="Vídeo",
            duration=duration,
        )
        await _prompt_audio_lang(update, context)
    except ValueError as e:
        await msg.reply_text(str(e), parse_mode="Markdown")
    except BadRequest as e:
        await msg.reply_text(
            prog("video_too_big_short", lang, detail=e),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("handle_video")
        await msg.reply_text(t("error_video", lang, detail=e))


async def prompt_link_mode(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    from bot.services.mp3_meta import reset_link_mp3_workflow

    lang = get_lang(context)
    reset_link_mp3_workflow(context)
    context.user_data["pending_link_url"] = url
    context.user_data["pending_job"] = {"kind": "link", "url": url}
    store_media_source(context, url)
    asyncio.create_task(
        _start_link_mp3_download_bg(update, context, url, occupy_heavy=False)
    )
    from bot.keyboards import audio_lang_keyboard
    from bot.services.audit_log import audit

    await update.message.reply_text(
        t("link_choose_mode", lang) + "\n\n" + t("audio_lang_prompt", lang),
        parse_mode="Markdown",
        reply_markup=audio_lang_keyboard(lang),
    )
    audit(
        update,
        phase="out",
        action="link_menu",
        response=f"menu enlace {url[:120]}",
    )


async def _run_pending_telegram_transcribe(
    update: Update, context: ContextTypes.DEFAULT_TYPE, job: dict
) -> None:
    begin_heavy_job(context)
    job_id = get_heavy_job_id(context)
    cancel_ev = get_cancel_event(context)
    lang = get_lang(context)
    media = job.get("media") or "audio"
    label = job.get("label") or "Audio"
    chat = update.effective_chat
    try:
        status = await chat.send_message(t("preparing", lang))
        progress = (
            ProgressReporter.video(status, lang=lang)
            if media == "video"
            else ProgressReporter.audio(status, lang=lang)
        )
        set_active_progress(context, progress)
        await progress.set_real(5, progress.p("received"), force=True)
        path = await download_telegram_file(
            update,
            context,
            job["file_id"],
            job.get("suffix") or ".mp4",
            progress,
            file_size=job.get("file_size"),
            media="audio" if media == "audio" else "default",
            cancel_event=cancel_ev,
        )
        await run_transcription(
            update, context, path, label, progress, cancel_event=cancel_ev
        )
    except JobCancelled:
        active_progress = get_active_progress(context)
        if active_progress:
            await active_progress.cancelled()
    except ValueError as e:
        await chat.send_message(str(e), parse_mode="Markdown")
    except BadRequest as e:
        await chat.send_message(
            prog("video_too_big_short", lang, detail=e),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("pending telegram transcribe")
        key = "error_video" if media == "video" else "error_audio"
        await chat.send_message(t(key, lang, detail=e))
    finally:
        end_heavy_job(context, job_id)
        await asyncio.to_thread(cleanup_old_files)


async def _run_pending_telegram_mp3(
    update: Update, context: ContextTypes.DEFAULT_TYPE, job: dict
) -> None:
    from bot.services.session_audio import store_session_audio_source

    begin_heavy_job(context)
    job_id = get_heavy_job_id(context)
    cancel_ev = get_cancel_event(context)
    lang = get_lang(context)
    media = job.get("media") or "audio"
    chat = update.effective_chat
    try:
        status = await chat.send_message(t("preparing", lang))
        progress = ProgressReporter.mp3_only(status, lang=lang)
        set_active_progress(context, progress)
        await progress.set_real(5, progress.p("received"), force=True)
        path = await download_telegram_file(
            update,
            context,
            job["file_id"],
            job.get("suffix") or ".mp4",
            progress,
            file_size=job.get("file_size"),
            media="audio" if media == "audio" else "default",
            cancel_event=cancel_ev,
        )
        await asyncio.to_thread(
            store_session_audio_source, context, chat.id, path, None
        )
        await handle_mp3_title_prompt(update, context, link_only=False)
    except JobCancelled:
        active_progress = get_active_progress(context)
        if active_progress:
            await active_progress.cancelled()
    except Exception as e:
        logger.exception("pending telegram mp3")
        await chat.send_message(t("error_audio", lang, detail=e))
    finally:
        end_heavy_job(context, job_id)
        await asyncio.to_thread(cleanup_old_files)


async def _download_link_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    progress: ProgressReporter,
    cancel_ev: threading.Event,
    lang: str,
    *,
    for_telegram: bool = False,
    mp3_stages: bool = False,
) -> tuple[Path, dict[str, str]]:
    from bot.services.mp3_progress import make_mp3_download_callback

    loop = asyncio.get_running_loop()
    if mp3_stages:
        dl_cb = make_mp3_download_callback(
            loop, progress, cancel_ev, lang=lang, bg_context=context
        )
    else:
        dl_cb = thread_safe_callback(loop, progress, cancel_ev)
    yt = is_youtube_url(url)
    first_label = (
        progress.p("downloading_audio_only")
        if yt
        else progress.p("downloading")
    )
    start_pct = 5 if mp3_stages else 5
    await progress.set_real(start_pct, first_label, progress.p("link_starting"), force=True)
    stop_pulse = asyncio.Event()
    wait_subs = (
        progress.p("fetch_wait_1"),
        progress.p("fetch_wait_2"),
        progress.p("fetch_wait_3"),
    )

    async def _pulse_fetch() -> None:
        i = 0
        while not stop_pulse.is_set():
            await asyncio.sleep(12)
            if stop_pulse.is_set():
                break
            i += 1
            if mp3_stages:
                from bot.services.mp3_progress import get_link_mp3_progress

                snap = get_link_mp3_progress(context)
                if snap:
                    continue
                pct = min(44, 6 + i * 3)
            else:
                pct = min(44, 6 + i * 4)
            await progress.set_real(
                pct,
                first_label,
                wait_subs[i % len(wait_subs)],
                force=True,
            )

    pulse_task = asyncio.create_task(_pulse_fetch())
    try:
        path, meta = await run_killable(
            cancel_ev,
            download_from_link_killable,
            url,
            dl_cb,
            cancel_ev,
            lang,
            for_telegram=for_telegram or mp3_stages,
            audio_only=mp3_stages,
        )
    finally:
        stop_pulse.set()
        pulse_task.cancel()
        try:
            await pulse_task
        except asyncio.CancelledError:
            pass
    return path, meta


def _telegram_default_mp3_title(msg) -> str:
    if not msg:
        return ""
    if msg.audio:
        if msg.audio.title:
            return msg.audio.title.strip()
        if msg.audio.file_name:
            return Path(msg.audio.file_name).stem.strip()
    if msg.caption and msg.caption.strip():
        return msg.caption.strip()
    if msg.document and msg.document.file_name:
        return Path(msg.document.file_name).stem.strip()
    if msg.video and getattr(msg.video, "file_name", None):
        return Path(msg.video.file_name).stem.strip()
    return ""


def _effective_user_id(update: Update) -> int | None:
    user = update.effective_user
    return user.id if user else None


async def _deliver_resolved_mp3(
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    progress: ProgressReporter,
    *,
    show_transcript: bool | None = None,
    user_id: int | None = None,
) -> None:
    from bot.services.mp3_meta import clear_mp3_meta_flow, get_resolved_mp3_meta
    from bot.services.mp3_progress import map_convert_inner, pop_link_mp3_progress
    from bot.services.session_audio import has_session_audio, prepare_session_delivery
    from bot.services.user_busy import has_cached_transcript

    lang = get_lang(context)
    if not has_session_audio(context):
        await progress.fail(t("no_session_audio", lang), "")
        return

    title, author = get_resolved_mp3_meta(context)
    link_only = show_transcript is False
    clear_mp3_meta_flow(context)

    snap = pop_link_mp3_progress(context)
    if snap and snap.get("pct", 0) >= 46:
        await progress.set_real(
            int(snap["pct"]),
            str(snap.get("label") or progress.p("creating_mp3")),
            str(snap.get("sub") or ""),
            force=True,
        )
    else:
        await progress.set_real(
            46, progress.p("creating_mp3"), force=True
        )

    loop = asyncio.get_running_loop()
    cancel_ev = get_cancel_event(context)

    def _prep_progress(pct: int, sub: str) -> None:
        mapped = map_convert_inner(pct)
        label = progress.p("creating_mp3")
        detail = sub or (f"{pct}%" if 0 < pct < 100 else "")
        asyncio.run_coroutine_threadsafe(
            progress.set_real(mapped, label, detail),
            loop,
        )

    audio = await run_killable(
        cancel_ev,
        prepare_session_delivery,
        context,
        chat_id,
        on_progress=_prep_progress,
        cancel_event=cancel_ev,
    )
    if not audio:
        await progress.fail(t("no_session_audio", lang), "")
        return

    if show_transcript is None:
        show_transcript = has_cached_transcript(context) and not link_only

    await deliver_session_mp3(
        chat_id,
        context,
        progress=progress,
        audio_title=title,
        audio_author=author,
        show_transcript_actions=show_transcript,
        user_id=user_id,
    )


_LINK_MP3_DL_STATE = "link_mp3_dl_state"


class _NullProgress:
    """Progreso silencioso para descarga en segundo plano."""

    _lang = "es"

    async def set_real(self, *args, **kwargs) -> None:
        return

    def p(self, key: str) -> str:
        return key


async def _wait_link_mp3_background(
    context: ContextTypes.DEFAULT_TYPE,
    progress: ProgressReporter | None,
    lang: str,
) -> None:
    from bot.services.mp3_progress import get_link_mp3_progress

    if context.user_data.get(_LINK_MP3_DL_STATE) != "running":
        return
    for i in range(7200):
        state = context.user_data.get(_LINK_MP3_DL_STATE)
        if state != "running":
            break
        if progress:
            snap = get_link_mp3_progress(context)
            if snap:
                await progress.set_real(
                    int(snap.get("pct", 10)),
                    str(snap.get("label") or prog("downloading_audio_only", lang)),
                    str(snap.get("sub") or ""),
                    force=(i % 2 == 0),
                )
            elif i % 2 == 0:
                await progress.set_real(
                    min(45, 8 + i // 4),
                    prog("downloading_audio_only", lang),
                    prog("link_starting", lang),
                    force=True,
                )
        await asyncio.sleep(1)
    if context.user_data.get(_LINK_MP3_DL_STATE) == "error":
        context.user_data.pop("link_mp3_dl_error", None)
        context.user_data.pop(_LINK_MP3_DL_STATE, None)


def _cancel_link_mp3_prefetch(context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.services.mp3_meta import cancel_link_mp3_prefetch

    cancel_link_mp3_prefetch(context)


async def _start_link_mp3_download_bg(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    *,
    occupy_heavy: bool = True,
) -> None:
    from bot.services.mp3_meta import (
        clear_stale_link_mp3_session,
        get_link_mp3_generation,
        link_mp3_session_matches,
        set_link_mp3_prefetch_cancel_event,
    )

    if link_mp3_session_matches(context, url):
        if context.user_data.get(_LINK_MP3_DL_STATE) == "done":
            return
    else:
        clear_stale_link_mp3_session(context, url)

    if context.user_data.get(_LINK_MP3_DL_STATE) == "running":
        return

    context.user_data[_LINK_MP3_DL_STATE] = "running"
    gen_at_start = get_link_mp3_generation(context)

    async def _run() -> None:
        from bot.services.mp3_meta import (
            bind_link_mp3_session,
            clear_pending_link_mp3_url,
            get_link_mp3_generation,
            set_link_mp3_ready_url,
            store_mp3_default_title,
        )
        from bot.services.session_audio import clear_session_audio, store_session_audio_source

        if occupy_heavy:
            cancel_ev = begin_heavy_job(context)
            job_id = get_heavy_job_id(context)
        else:
            cancel_ev = threading.Event()
            set_link_mp3_prefetch_cancel_event(context, cancel_ev)
            job_id = None
        chat = update.effective_chat
        lang = get_lang(context)
        path = None
        try:
            null_prog = _NullProgress()
            null_prog._lang = lang
            path, meta = await _download_link_file(
                update,
                context,
                url,
                null_prog,
                cancel_ev,
                lang,
                mp3_stages=True,
            )
            if cancel_ev.is_set() or gen_at_start != get_link_mp3_generation(context):
                return
            store_mp3_default_title(context, meta.get("title", ""))
            await asyncio.to_thread(
                store_session_audio_source, context, chat.id, path, None
            )
            if gen_at_start != get_link_mp3_generation(context):
                clear_session_audio(context)
                return
            bind_link_mp3_session(context, url, source_id=meta.get("id"))
            set_link_mp3_ready_url(context, url)
            clear_pending_link_mp3_url(context)
            context.user_data[_LINK_MP3_DL_STATE] = "done"
        except Exception as e:
            if cancel_ev.is_set() or gen_at_start != get_link_mp3_generation(context):
                return
            logger.exception("Descarga MP3 en segundo plano")
            context.user_data[_LINK_MP3_DL_STATE] = "error"
            context.user_data["link_mp3_dl_error"] = str(e)[:400]
        finally:
            if occupy_heavy:
                end_heavy_job(context, job_id)
            set_link_mp3_prefetch_cancel_event(context, None)
            if context.user_data.get(_LINK_MP3_DL_STATE) == "running":
                context.user_data.pop(_LINK_MP3_DL_STATE, None)

    asyncio.create_task(_run())


async def handle_link_mp3_direct_now(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    """MP3 directo: descargar y enviar sin preguntar título/artista."""
    from bot.services.mp3_meta import (
        apply_mp3_direct_defaults,
        clear_stale_link_mp3_session,
        set_pending_link_mp3_url,
    )

    store_media_source(context, url)
    set_pending_link_mp3_url(context, url)
    clear_stale_link_mp3_session(context, url)
    context.user_data["mp3_link_only"] = True
    apply_mp3_direct_defaults(context)
    query = update.callback_query
    lang = get_lang(context)
    status = await query.message.reply_text(t("preparing", lang))
    progress = ProgressReporter.mp3_only(status, lang=lang)
    set_active_progress(context, progress)
    fake_update = Update(update.update_id, message=query.message)
    await _fulfill_link_mp3_download(fake_update, context, progress=progress)


async def handle_link_mp3_mode_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    """Tras elegir solo audio: pedir título/artista antes de descargar."""
    from bot.services.mp3_meta import set_pending_link_mp3_url

    store_media_source(context, url)
    set_pending_link_mp3_url(context, url)
    asyncio.create_task(_prefetch_link_title(context, url))
    asyncio.create_task(_start_link_mp3_download_bg(update, context, url))
    query = update.callback_query
    fake_update = Update(update.update_id, message=query.message)
    await handle_mp3_title_prompt(fake_update, context, link_only=True)


async def _prefetch_link_title(context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    from bot.services.metadata import _fetch_ytdlp_title
    from bot.services.mp3_meta import store_mp3_default_title

    try:
        title = await asyncio.to_thread(_fetch_ytdlp_title, url)
        if title:
            store_mp3_default_title(context, title)
    except Exception:
        logger.debug("Prefetch título enlace falló", exc_info=True)


async def _fulfill_link_mp3_download(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    progress: ProgressReporter | None = None,
) -> None:
    from bot.services.mp3_meta import (
        bind_link_mp3_session,
        clear_pending_link_mp3_url,
        clear_stale_link_mp3_session,
        get_link_mp3_generation,
        get_pending_link_mp3_url,
        link_mp3_session_matches,
        set_link_mp3_ready_url,
        store_mp3_default_title,
    )
    from bot.services.session_audio import store_session_audio_source

    url = get_pending_link_mp3_url(context)
    lang = get_lang(context)
    chat = update.effective_chat

    clear_stale_link_mp3_session(context, url)

    if url and link_mp3_session_matches(context, url):
        context.user_data.pop(_LINK_MP3_DL_STATE, None)
        context.user_data.pop("link_mp3_dl_error", None)
        if progress is None:
            status = await chat.send_message(t("preparing", lang))
            progress = ProgressReporter.mp3_only(status, lang=lang)
        await _deliver_resolved_mp3(
            chat.id,
            context,
            progress,
            show_transcript=False,
            user_id=_effective_user_id(update),
        )
        return

    if not url:
        raise ValueError(t("no_session_audio", lang))

    if progress is None:
        status = await chat.send_message(t("preparing", lang))
        progress = ProgressReporter.mp3_only(status, lang=lang)
        set_active_progress(context, progress)

    gen_at_start = get_link_mp3_generation(context)
    await _wait_link_mp3_background(context, progress, lang)
    if url and link_mp3_session_matches(context, url):
        context.user_data.pop(_LINK_MP3_DL_STATE, None)
        clear_pending_link_mp3_url(context)
        await _deliver_resolved_mp3(
            chat.id,
            context,
            progress,
            show_transcript=False,
            user_id=_effective_user_id(update),
        )
        return

    if await reject_if_heavy_busy(update, context):
        return

    cancel_ev = begin_heavy_job(context)
    job_id = get_heavy_job_id(context)
    path = None
    try:
        path, meta = await _download_link_file(
            update,
            context,
            url,
            progress,
            cancel_ev,
            lang,
            mp3_stages=True,
        )
        if gen_at_start != get_link_mp3_generation(context):
            raise JobCancelled()
        store_mp3_default_title(context, meta.get("title", ""))
        _raise_if_cancelled(context)

        await asyncio.to_thread(
            store_session_audio_source, context, chat.id, path, None
        )
        bind_link_mp3_session(context, url, source_id=meta.get("id"))
        set_link_mp3_ready_url(context, url)
        clear_pending_link_mp3_url(context)

        await _deliver_resolved_mp3(
            chat.id, context, progress, show_transcript=False,
            user_id=_effective_user_id(update),
        )
    except JobCancelled:
        from bot.services.job_cancel import terminate_all

        terminate_all()
        if progress:
            await progress.cancelled()
    except Exception as e:
        err_lower = str(e).lower()
        if "cancelad" in err_lower or "cancel" in err_lower:
            from bot.services.job_cancel import terminate_all

            terminate_all()
            if progress:
                await progress.cancelled()
            return
        logger.exception("Error descarga MP3 enlace")
        err = str(e)
        if progress:
            await progress.fail("No pude procesar el enlace.", err[:1500], markdown=False)
        else:
            await chat.send_message(f"❌ No pude procesar el enlace.\n\n{err}"[:4000])
    finally:
        end_heavy_job(context, job_id)
        if path:
            _cleanup(path)
        await asyncio.to_thread(cleanup_old_files)


async def handle_link_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    mode: str = "transcribe",
    url: str | None = None,
) -> None:
    if await reject_if_heavy_busy(update, context):
        return
    cancel_ev = begin_heavy_job(context)
    job_id = get_heavy_job_id(context)
    msg = update.message
    text = msg.text or ""
    lang = get_lang(context)
    path = None
    meta: dict[str, str] = {}
    progress: ProgressReporter | None = None
    try:
        url = url or extract_social_url(text)
        if not url:
            await msg.reply_text(prog("link_hint", get_lang(context)))
            return

        store_media_source(context, url)
        yt = is_youtube_url(url)
        status = await msg.reply_text(t("preparing", lang))
        progress = ProgressReporter.link(status, youtube=yt, lang=lang)
        set_active_progress(context, progress)

        # YouTube: Shorts y vídeos sin subtítulos MANUALES → Whisper
        # (los auto-subs cortan el final y meten puntos/apartes falsos).
        if yt:
            from bot.services.youtube_captions import try_fetch_youtube_captions
            from bot.services.transcript_lang import get_transcript_lang
            from bot.services.media import is_youtube_shorts_url

            tx_mode = get_transcript_lang(context)
            if is_youtube_shorts_url(url):
                logger.info("YouTube Short → Whisper %s", url)
                await progress.set_real(40, progress.p("extracting_audio"), force=True)
            else:
                await progress.set_real(30, progress.p("youtube_captions"), force=True)
                caps = await asyncio.to_thread(try_fetch_youtube_captions, url, tx_mode)
                if caps:
                    logger.info("Usando subtítulos YouTube manuales %s (%s segs)", url, len(caps[0]))
                    await run_transcription(
                        update,
                        context,
                        None,
                        "YouTube",
                        progress,
                        cancel_event=cancel_ev,
                        precomputed=caps,
                    )
                    return
                logger.info("YouTube sin caps manuales → Whisper %s", url)
                await progress.set_real(40, progress.p("whisper_fallback"), force=True)

        path, meta = await _download_link_file(
            update, context, url, progress, cancel_ev, lang,
            for_telegram=False,
        )
        from bot.services.mp3_meta import store_mp3_default_title

        store_mp3_default_title(context, meta.get("title", ""))
        _raise_if_cancelled(context)

        await progress.set_real(50, progress.p("extracting_audio"), force=True)
        await run_transcription(
            update, context, path, "Enlace", progress, cancel_event=cancel_ev
        )
    except JobCancelled:
        from bot.services.job_cancel import terminate_all

        terminate_all()
        active_progress = get_active_progress(context)
        if active_progress:
            await active_progress.cancelled()
    except Exception as e:
        err_lower = str(e).lower()
        if "cancelad" in err_lower or "cancel" in err_lower:
            from bot.services.job_cancel import terminate_all

            terminate_all()
            prog_rep = get_active_progress(context)
            if prog_rep:
                await prog_rep.cancelled()
            return
        logger.exception("Error enlace")
        err = str(e)
        if progress:
            await progress.fail("No pude procesar el enlace.", err[:1500], markdown=False)
        else:
            await msg.reply_text(f"❌ No pude procesar el enlace.\n\n{err}"[:4000])
        if path:
            _cleanup(path)
    finally:
        end_heavy_job(context, job_id)
        await asyncio.to_thread(cleanup_old_files)


async def handle_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    formatted = get_active_formatted(context)
    if not formatted:
        await update.effective_chat.send_message(
            t("summary_need_transcript", get_lang(context)),
            parse_mode="Markdown",
        )
        return

    chat = update.effective_chat
    lang = get_lang(context)
    from bot.services.transcript_cache import get_cached_summary, store_summary_cache

    cached_summary = get_cached_summary(context)
    if cached_summary:
        await deliver_summary(chat.id, context, cached_summary)
        return

    status = await chat.send_message(t("preparing_summary", lang))
    progress = ProgressReporter.summary(status, lang=lang)
    try:
        await progress.set_real(10, progress.p("reading_transcript"), force=True)
        await progress.set_real(45, progress.p("creating_summary"), force=True)
        summary = await asyncio.to_thread(
            summarize_text, formatted, get_content_lang(context)
        )
        context.user_data["last_summary"] = summary
        store_summary_cache(context, summary)
        await progress.set_real(88, progress.p("sending_summary"), force=True)
        await deliver_summary(chat.id, context, summary)
        await progress.done(t("summary_done", lang))
    except Exception as e:
        await progress.fail(progress.p("fail_summarize"), str(e)[:400])
    finally:
        await asyncio.to_thread(cleanup_old_files)


def _export_content(context: ContextTypes.DEFAULT_TYPE, mode: str) -> tuple[str, str, str]:
    """Devuelve (contenido, file_kind, etiqueta usuario)."""
    formatted = get_active_formatted(context)
    segments = get_active_segments(context)
    content_lang = get_content_lang(context)
    ui_lang = get_lang(context)

    if mode == "txt":
        return formatted, mode, t("btn_txt", ui_lang)
    if mode == "pdf":
        return formatted, mode, t("btn_pdf", ui_lang)
    if mode in ("index_txt", "index_pdf", "moments_txt", "moments_pdf"):
        if not segments:
            raise ValueError(prog("no_timestamps", ui_lang))
        from bot.services.transcript_cache import get_cached_index_blocks, store_index_cache

        blocks, _ = get_cached_index_blocks(context)
        if not blocks:
            blocks = build_moment_blocks(segments, lang=content_lang)
            store_index_cache(context, blocks)
        body = format_moments_plain(blocks)
        kind = "pdf" if mode.endswith("_pdf") else "txt"
        return body, kind, prog("export_label_index", ui_lang)
    if mode in ("highlights_txt", "highlights_pdf"):
        if not segments:
            raise ValueError(prog("no_timestamps", ui_lang))
        from bot.services.transcript_cache import get_cached_highlights, store_highlights_cache

        items, _ = get_cached_highlights(context)
        if not items:
            items = build_highlights(segments, formatted, lang=content_lang)
            if items:
                store_highlights_cache(context, items)
        if not items:
            raise ValueError(prog("no_highlights_gen", ui_lang))
        body = format_highlights_plain(items)
        kind = "pdf" if mode.endswith("_pdf") else "txt"
        return body, kind, prog("export_label_highlights", ui_lang)
    raise ValueError(f"Modo desconocido: {mode}")


async def handle_index(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not get_active_segments_stored(context):
        await update.effective_chat.send_message(
            t("need_transcript_first", get_lang(context)),
            parse_mode="Markdown",
        )
        return

    chat = update.effective_chat
    lang = get_lang(context)
    from bot.services.transcript_cache import get_cached_index_blocks

    cached_blocks, _ = get_cached_index_blocks(context)
    if cached_blocks:
        status = await chat.send_message(t("index_opening", lang))
        progress = ProgressReporter.export(status, kind=t("progress_export_index", lang), lang=lang)
    else:
        status = await chat.send_message(t("index_creating", lang))
        progress = ProgressReporter.export(status, kind=t("progress_export_index", lang), lang=lang)
    try:
        await deliver_moments_index(
            chat.id,
            context,
            get_active_segments_stored(context),
            progress=progress,
        )
    except ValueError as e:
        await progress.fail(str(e))
    except Exception as e:
        logger.exception("handle_index")
        await progress.fail(prog("fail_index", lang), str(e)[:400])
    finally:
        await asyncio.to_thread(cleanup_old_files)


async def handle_highlights(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not get_active_segments_stored(context):
        await update.effective_chat.send_message(
            t("need_transcript_first", get_lang(context)),
            parse_mode="Markdown",
        )
        return

    chat = update.effective_chat
    lang = get_lang(context)
    from bot.services.transcript_cache import get_cached_highlights

    if get_cached_highlights(context)[0]:
        status = await chat.send_message(t("highlights_opening", lang))
    else:
        status = await chat.send_message(t("highlights_creating", lang))
    progress = ProgressReporter.export(status, kind=t("progress_export_highlights", lang), lang=lang)
    try:
        await deliver_highlights(
            chat.id,
            context,
            get_active_segments_stored(context),
            progress=progress,
        )
    except ValueError as e:
        await progress.fail(str(e))
    except Exception as e:
        logger.exception("handle_highlights")
        await progress.fail(prog("fail_highlights", lang), str(e)[:400])
    finally:
        await asyncio.to_thread(cleanup_old_files)


async def handle_search_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    lang = get_lang(context)
    if not get_active_segments_stored(context):
        await query.answer(t("no_transcript_saved", lang), show_alert=True)
        return
    context.user_data["awaiting_search"] = True
    await query.message.reply_text(t("search_prompt", lang), parse_mode="Markdown")


async def try_handle_search_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if not context.user_data.get("awaiting_search"):
        return False
    msg = update.message
    if not msg or not msg.text:
        return False

    lang = get_lang(context)
    query_text = msg.text.strip()

    from bot.keyboards import search_empty_keyboard
    from bot.services.transcript_search import (
        find_search_hits,
        fold_text,
        hits_to_stored,
    )
    from bot.services.search_nav import send_search_results

    empty_kb = search_empty_keyboard(lang)

    if len(fold_text(query_text)) < 2:
        await msg.reply_text(
            t("search_too_short", lang),
            parse_mode="Markdown",
            reply_markup=empty_kb,
        )
        return True

    segments = get_active_segments(context)
    if not segments:
        context.user_data.pop("awaiting_search", None)
        await msg.reply_text(t("no_transcript_saved", lang))
        return True

    hits = find_search_hits(segments, query_text)
    if not hits:
        q_safe = query_text[:80].replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")
        await msg.reply_text(
            t("search_no_results", lang, query=q_safe),
            parse_mode="Markdown",
            reply_markup=empty_kb,
        )
        return True

    context.user_data.pop("awaiting_search", None)
    await send_search_results(
        context, msg.chat_id, query_text, hits_to_stored(hits)
    )
    if len(hits) > 1:
        await msg.reply_text(
            t("search_many_results", lang, total=len(hits)),
            parse_mode="Markdown",
        )
    return True


async def handle_read_telegram(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if not get_active_segments_stored(context):
        await update.effective_chat.send_message(
            t("no_transcript_saved", get_lang(context))
        )
        return
    chat = update.effective_chat
    lang = get_lang(context)
    status = await chat.send_message(f"⏳ {t('progress_read_tg', lang)}…")
    progress = ProgressReporter.export(status, kind=t("progress_read_tg", lang), lang=lang)
    try:
        await deliver_telegraph_read(chat.id, context, progress=progress)
    except ValueError as e:
        await progress.fail(str(e))
    except Exception as e:
        logger.exception("handle_read_telegram")
        await progress.fail(t("read_tg_fail", lang), str(e)[:400])
    finally:
        await asyncio.to_thread(cleanup_old_files)


async def handle_mp3_title_prompt(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    link_only: bool = False,
) -> None:
    from bot.keyboards import mp3_meta_prompt_keyboard
    from bot.services.metadata import get_document_metadata
    from bot.services.mp3_meta import (
        get_pending_link_mp3_url,
        is_mp3_link_only,
        start_mp3_title_prompt,
        store_mp3_default_title,
    )
    from bot.services.session_audio import has_session_audio

    lang = get_lang(context)
    chat = update.effective_chat
    pending = get_pending_link_mp3_url(context)
    if not has_session_audio(context) and not (link_only and pending):
        await chat.send_message(t("no_session_audio", lang))
        return
    context.user_data.pop("awaiting_search", None)
    if not link_only:
        doc = get_document_metadata(context).get("title", "")
        if isinstance(doc, str) and doc.strip():
            store_mp3_default_title(context, doc.strip())
    start_mp3_title_prompt(context, link_only=link_only)
    await chat.send_message(
        t("mp3_prompt_title", lang),
        parse_mode="Markdown",
        reply_markup=mp3_meta_prompt_keyboard(
            lang, link_only=link_only or is_mp3_link_only(context)
        ),
    )


async def try_handle_mp3_meta_query(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    from bot.keyboards import mp3_meta_prompt_keyboard
    from bot.services.mp3_meta import (
        clear_mp3_meta_flow,
        get_pending_link_mp3_url,
        try_handle_mp3_meta_text,
    )
    from bot.services.session_audio import has_session_audio

    if not context.user_data.get("awaiting_mp3_title") and not context.user_data.get(
        "awaiting_mp3_author"
    ):
        return False

    msg = update.message
    if not msg or msg.text is None:
        return False

    lang = get_lang(context)
    step = try_handle_mp3_meta_text(context, msg.text)
    if step is None:
        return False

    link_only = bool(context.user_data.get("mp3_link_only"))
    pending = get_pending_link_mp3_url(context)

    if step == "need_author":
        await msg.reply_text(
            t("mp3_prompt_author", lang),
            parse_mode="Markdown",
            reply_markup=mp3_meta_prompt_keyboard(lang, link_only=link_only),
        )
        return True

    if pending:
        status = await msg.reply_text(t("preparing", lang))
        progress = ProgressReporter.mp3_only(status, lang=lang)
        try:
            await _fulfill_link_mp3_download(update, context, progress=progress)
        except ValueError as e:
            await progress.fail(str(e), "")
        except Exception as e:
            logger.exception("mp3 meta link download")
            await progress.fail(
                prog("file_create_fail", lang, label=t("btn_mp3", lang)), str(e)[:400]
            )
        return True

    if not has_session_audio(context):
        clear_mp3_meta_flow(context)
        await msg.reply_text(t("no_session_audio", lang))
        return True

    chat = update.effective_chat
    status = await chat.send_message(t("preparing_file", lang))
    progress = ProgressReporter.mp3_only(status, lang=lang)
    try:
        await _deliver_resolved_mp3(
            chat.id,
            context,
            progress,
            show_transcript=not link_only,
            user_id=_effective_user_id(update),
        )
    except ValueError as e:
        await progress.fail(str(e), "")
    except Exception as e:
        from bot.services.upload_router import UserLimitError

        if isinstance(e, UserLimitError):
            await progress.fail(t("mp3_external_limit", lang, detail=str(e)), "")
            return True
        logger.exception("mp3 meta export")
        await progress.fail(
            prog("file_create_fail", lang, label=t("btn_mp3", lang)), str(e)[:400]
        )
    finally:
        await asyncio.to_thread(cleanup_old_files)
    return True


async def handle_export(
    update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str
) -> None:
    if mode == "mp3_direct":
        from bot.services.mp3_meta import (
            apply_mp3_direct_defaults,
            get_pending_link_mp3_url,
            is_mp3_link_only,
        )
        from bot.services.session_audio import has_session_audio

        link_only = is_mp3_link_only(context)
        pending = get_pending_link_mp3_url(context)
        apply_mp3_direct_defaults(context)
        chat = update.effective_chat
        lang = get_lang(context)
        label = t("btn_mp3_direct", lang)

        if pending:
            status = await chat.send_message(t("preparing", lang))
            progress = ProgressReporter.mp3_only(status, lang=lang)
            try:
                await _fulfill_link_mp3_download(update, context, progress=progress)
            except ValueError as e:
                await progress.fail(str(e), "")
            except Exception as e:
                logger.exception("mp3_direct link download")
                await progress.fail(
                    prog("file_create_fail", lang, label=label), str(e)[:400]
                )
            return

        if not has_session_audio(context):
            await chat.send_message(t("no_session_audio", lang))
            return
        status = await chat.send_message(t("preparing_file", lang))
        progress = ProgressReporter.mp3_only(status, lang=lang)
        try:
            await _deliver_resolved_mp3(
                chat.id,
                context,
                progress,
                show_transcript=not link_only,
                user_id=_effective_user_id(update),
            )
        except ValueError as e:
            await progress.fail(str(e), "")
        except Exception as e:
            from bot.services.upload_router import UserLimitError

            if isinstance(e, UserLimitError):
                await progress.fail(t("mp3_external_limit", lang, detail=str(e)), "")
                return
            logger.exception("mp3_direct export")
            await progress.fail(
                prog("file_create_fail", lang, label=label), str(e)[:400]
            )
        finally:
            await asyncio.to_thread(cleanup_old_files)
        return

    if mode == "mp3":
        await handle_mp3_title_prompt(update, context)
        return

    if not get_active_formatted(context):
        await update.effective_chat.send_message(t("export_need_transcript", get_lang(context)))
        return

    chat = update.effective_chat
    lang = get_lang(context)
    status = await chat.send_message(t("preparing_file", lang))
    progress = ProgressReporter.export(status, kind=t("progress_export_file", lang), lang=lang)
    label = ""
    try:
        content, file_kind, label = _export_content(context, mode)
        await deliver_file(
            chat.id, context, content, file_kind, progress=progress, label=label
        )
    except ValueError as e:
        await progress.fail(str(e), "")
    except Exception as e:
        logger.exception("handle_export")
        await progress.fail(prog("file_create_fail", lang, label=label or "?"), str(e)[:400])
    finally:
        await asyncio.to_thread(cleanup_old_files)


def _variant_display_label(context: ContextTypes.DEFAULT_TYPE, variant: str, ui_lang: str) -> str:
    from bot.services.transcript_active import get_variant

    if variant == VARIANT_ORIGINAL:
        return variant_button_label(context, VARIANT_ORIGINAL, ui_lang).replace(" ✓", "")
    label = LANG_MENU.get(variant, variant.upper())
    if get_variant(context) == variant:
        return label
    return label


async def handle_translate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    lang = get_lang(context)
    await query.answer()
    from bot.keyboards import translate_target_keyboard

    source = get_source_lang(context).upper()
    await query.message.reply_text(
        t("translate_menu_title", lang, source=source),
        parse_mode="Markdown",
        reply_markup=translate_target_keyboard(context, lang),
    )


async def handle_variant_switch(
    update: Update, context: ContextTypes.DEFAULT_TYPE, variant: str
) -> None:
    query = update.callback_query
    lang = get_lang(context)
    set_variant(context, variant)
    from bot.services.transcript_active import get_variant

    current = get_variant(context)
    label = _variant_display_label(context, current, lang)
    chat = update.effective_chat

    await deliver_transcript_view(chat.id, context, force_new=False, reset_page=True)
    await query.answer(t("translate_switched", lang, label=label))


async def handle_translate_to(
    update: Update, context: ContextTypes.DEFAULT_TYPE, target_lang: str
) -> None:
    query = update.callback_query
    lang = get_lang(context)
    target = target_lang.strip().lower()[:2]
    target_label = LANG_MENU.get(target, target.upper())

    if has_translation(context, target):
        set_variant(context, target)
        chat = update.effective_chat
        await deliver_transcript_view(chat.id, context, force_new=True, reset_page=True)
        label = LANG_MENU.get(target, target.upper())
        await query.answer(t("translate_switched", lang, label=label))
        return

    from bot.config import GROQ_API_KEYS

    if not (GROQ_API_KEY or GROQ_API_KEYS):
        await query.answer(t("translate_no_groq", lang), show_alert=True)
        return

    await query.answer()
    chat = update.effective_chat
    status = await chat.send_message(
        t("translate_working", lang, target=target_label)
    )
    progress = ProgressReporter.export(
        status, kind=t("progress_translate", lang), lang=lang
    )
    try:
        source = get_source_lang(context)
        original = segments_from_stored(context.user_data.get("last_segments") or [])
        if not original:
            raise ValueError(t("no_transcript_saved", lang))

        await progress.set_real(12, progress.p("translating"), force=True)
        loop = asyncio.get_running_loop()
        push_progress = thread_safe_callback(loop, progress)

        def _run():
            # Texto completo = mejor contexto/slang que trozos línea a línea
            from bot.services.transcript_active import get_active_formatted

            src_text = (
                context.user_data.get("last_formatted")
                or get_active_formatted(context)
                or ""
            )

            def _on_chunk(pct: int, cur, total=None) -> None:
                # cur int = trozo N/M; cur str = mensaje de espera/cuota
                if isinstance(cur, str):
                    push_progress(pct, cur, str(total or ""))
                    return
                push_progress(
                    pct,
                    progress.p("translating"),
                    f"{cur}/{total}" if total and total > 1 else "",
                )

            tr_text = translate_formatted_text(
                src_text,
                source_lang=source,
                target_lang=target,
                ui_lang=lang,
                progress_cb=_on_chunk,
            )
            if not original:
                return [TranscriptSegment(0.0, 0.0, tr_text)], tr_text
            return (
                [
                    TranscriptSegment(
                        original[0].start,
                        original[-1].end,
                        tr_text,
                    )
                ],
                tr_text,
            )

        translated, formatted = await asyncio.to_thread(_run)
        await progress.set_real(78, progress.p("formatting"), force=True)
        stored = segments_to_stored(translated)
        store_translation(context, target, stored, formatted)
        set_variant(context, target)

        await deliver_transcript_view(
            chat.id, context, formatted, force_new=True, reset_page=True
        )
        await progress.done(
            t("translate_done_short", lang, target=target_label)
        )
    except TranslationError as e:
        await progress.fail(str(e), "")
    except Exception as e:
        logger.exception("handle_translate_to")
        await progress.fail(t("translate_fail", lang), str(e)[:400])
    finally:
        await asyncio.to_thread(cleanup_old_files)


def _text_is_social_link(text: str) -> bool:
    return extract_social_url(text) is not None


async def handle_cookies_upload(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Desactivado: no guardar sesiones de cuenta (Instagram/YouTube)."""
    msg = update.message
    if not msg:
        return
    await msg.reply_text(
        "🚫 *Subida de cookies desactivada.*\n\n"
        "No se guarda ni usa login automático de Instagram/cuenta "
        "para evitar flags de automatización.",
        parse_mode="Markdown",
    )

async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.handlers.common import handle_menu_text
    from bot.services.audit_log import audit_message_in

    ensure_user_lang(update, context)
    audit_message_in(update)
    if await handle_menu_text(update, context):
        return

    msg = update.message
    if not msg:
        return

    if msg.text and _text_is_social_link(msg.text):
        context.user_data.pop("awaiting_search", None)
        if await reject_if_heavy_busy(update, context):
            return
        url = extract_social_url(msg.text)
        if url:
            await prompt_link_mode(update, context, url)
            return
        await handle_link_text(update, context)
        return

    if msg.text and await try_handle_search_query(update, context):
        return

    from bot.services.mp3_meta import is_awaiting_mp3_meta

    if is_awaiting_mp3_meta(context) and await try_handle_mp3_meta_query(update, context):
        return

    if msg.document and msg.document.file_name:
        from bot.config import is_admin

        if (
            is_admin(msg.from_user.id if msg.from_user else 0)
            and msg.document.file_name.lower() in ("cookies.txt", "cookies.txt.txt")
        ):
            await handle_cookies_upload(update, context)
            return

    if telegram_message_is_audio(msg):
        await handle_audio(update, context)
        return

    if msg.video or msg.video_note or (
        msg.document and (msg.document.mime_type or "").startswith("video/")
    ):
        await handle_video(update, context)
        return

    if msg.text and not await reject_if_heavy_busy(update, context):
        await send_main_menu(update, context)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.services.audit_log import audit_command

    audit_command(update, "/start")
    await send_start(update, context)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.services.audit_log import audit_command

    audit_command(update, "/help")
    await send_help(update, context)


async def cmd_idioma(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.handlers.common import send_idioma_picker
    from bot.services.audit_log import audit_command

    audit_command(update, "/idioma")
    await send_idioma_picker(update, context)


async def callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_user_lang(update, context)
    query = update.callback_query
    data = query.data or ""
    from bot.services.audit_log import audit_callback

    audit_callback(update, data)
    lang = get_lang(context)

    if data == "action:cancel":
        await handle_cancel(update, context)
        return
    if data.startswith("ui_lang:"):
        new_lang = data.split(":", 1)[1]
        if new_lang in SUPPORTED:
            await query.answer()
            await apply_ui_lang_change(update, context, new_lang)
        else:
            await query.answer()
        return
    if data.startswith("audio_lang:"):
        from bot.keyboards import job_mode_keyboard
        from bot.services.transcript_lang import AUTO_LANG, set_transcript_lang

        choice = data.split(":", 1)[1]
        await query.answer()
        if choice == "cancel":
            context.user_data.pop("pending_job", None)
            context.user_data.pop("pending_link_url", None)
            from bot.services.mp3_meta import clear_link_mp3_state

            clear_link_mp3_state(context)
            _cancel_link_mp3_prefetch(context)
            try:
                await query.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await query.message.reply_text(t("audio_lang_cancelled", lang))
            return
        if choice not in SUPPORTED and choice != AUTO_LANG:
            return
        set_transcript_lang(context, choice)
        label = LANG_MENU.get(choice) or active_lang_label(choice)
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.message.reply_text(
            t("job_choose_mode", lang, label=label),
            parse_mode="Markdown",
            reply_markup=job_mode_keyboard(lang),
        )
        return
    if data.startswith("job_mode:") or data.startswith("link_mode:"):
        mode = data.split(":", 1)[1]
        await query.answer()
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        job = context.user_data.pop("pending_job", None) or {}
        url = context.user_data.get("pending_link_url") or job.get("url")
        if mode == "cancel":
            context.user_data.pop("pending_link_url", None)
            from bot.services.mp3_meta import clear_link_mp3_state

            clear_link_mp3_state(context)
            _cancel_link_mp3_prefetch(context)
            await query.message.reply_text(t("audio_lang_cancelled", lang))
            return
        kind = job.get("kind")
        if kind == "telegram":
            if mode == "mp3":
                await _run_pending_telegram_mp3(update, context, job)
            else:
                await _run_pending_telegram_transcribe(update, context, job)
            return
        # Link (or legacy link_mode)
        if not url:
            context.user_data.pop("pending_link_url", None)
            return
        context.user_data.pop("pending_link_url", None)
        if mode == "mp3":
            await handle_link_mp3_mode_choice(update, context, url)
            return
        if mode == "mp3_now":
            await handle_link_mp3_direct_now(update, context, url)
            return
        _cancel_link_mp3_prefetch(context)
        fake_update = Update(update.update_id, message=query.message)
        await handle_link_text(fake_update, context, mode="transcribe", url=url)
        return
    if data.startswith("tx_nav:"):
        from bot.services.transcript_nav import handle_transcript_nav

        await handle_transcript_nav(update, context, data.split(":", 1)[1])
        return
    if data.startswith("sum_nav:"):
        from bot.services.summary_nav import handle_summary_nav

        await handle_summary_nav(update, context, data.split(":", 1)[1])
        return
    if data.startswith("mom_nav:"):
        from bot.services.moments_nav import handle_moments_nav

        await handle_moments_nav(update, context, data.split(":", 1)[1])
        return
    if data.startswith("hi_nav:"):
        from bot.services.highlights_nav import handle_highlights_nav

        await handle_highlights_nav(update, context, data.split(":", 1)[1])
        return
    if data.startswith("search_nav:"):
        from bot.services.search_nav import handle_search_nav

        await handle_search_nav(update, context, data.split(":", 1)[1])
        return

    await query.answer()

    if data == "home":
        from bot.services.mp3_meta import clear_link_mp3_state

        clear_link_mp3_state(context)
        await send_main_menu(update, context)
        return
    if data == "help":
        await send_main_menu(update, context)
        return

    if should_block_callback(data, context):
        msg = (
            busy_message(lang).replace("*", "")
            if not has_cached_transcript(context)
            else t("busy_new_file", lang)
        )
        await query.message.reply_text(msg)
        return

    if data == "action:search":
        await handle_search_prompt(update, context)
        return
    if data == "action:summary":
        await handle_summary(update, context)
        return
    if data == "action:translate_menu":
        await handle_translate_menu(update, context)
        return
    if data.startswith("action:translate_to:"):
        await handle_translate_to(update, context, data.split(":", 2)[2])
        return
    if data.startswith("action:variant:"):
        await handle_variant_switch(update, context, data.split(":", 2)[2])
        return
    if data == "fmt_back":
        from bot.keyboards import after_transcript_keyboard
        from bot.services.mp3_meta import clear_mp3_meta_flow

        context.user_data.pop("awaiting_search", None)
        clear_mp3_meta_flow(context)
        await query.message.reply_text(
            t("transcript_actions", lang),
            reply_markup=after_transcript_keyboard(lang, context=context),
        )
        return
    if data == "fmt_get:read_tg":
        await handle_read_telegram(update, context)
        return
    if data in ("fmt_get:index", "fmt_get:moments"):
        await handle_index(update, context)
        return
    if data == "fmt_get:highlights":
        await handle_highlights(update, context)
        return
    if data.startswith("fmt_get:"):
        mode = data.split(":", 1)[1]
        if mode == "mp3":
            await handle_mp3_title_prompt(update, context)
            return
        if mode == "mp3_direct":
            await handle_export(update, context, "mp3_direct")
            return
        if mode in (
            "txt",
            "pdf",
            "index_txt",
            "index_pdf",
            "moments_txt",
            "moments_pdf",
            "highlights_txt",
            "highlights_pdf",
        ):
            await handle_export(update, context, mode)
        return
    if data.startswith("mode:"):
        await send_main_menu(update, context)
