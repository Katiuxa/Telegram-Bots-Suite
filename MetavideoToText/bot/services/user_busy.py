import threading

from telegram import Update
from telegram.ext import ContextTypes

from bot.i18n import get_lang, t

# Tras cancelar, los job_id antiguos quedan invalidados
_JOB_INVALID = -1


def busy_message(lang: str | None = None) -> str:
    return t("busy_message", lang)


def cancelled_message(lang: str | None = None) -> str:
    return t("cancelled", lang)


BUSY_MESSAGE = busy_message()
CANCELLED_MESSAGE = cancelled_message()


def is_heavy_busy(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("heavy_busy"))


def is_busy(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return is_heavy_busy(context)


def has_cached_transcript(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("last_formatted"))


def get_heavy_job_id(context: ContextTypes.DEFAULT_TYPE) -> int | None:
    jid = context.user_data.get("heavy_job_id")
    return jid if isinstance(jid, int) else None


def begin_heavy_job(context: ContextTypes.DEFAULT_TYPE) -> threading.Event:
    seq = int(context.user_data.get("heavy_job_seq", 0)) + 1
    context.user_data["heavy_job_seq"] = seq
    context.user_data["heavy_job_id"] = seq
    ev = threading.Event()
    context.user_data["cancel_event"] = ev
    context.user_data["heavy_busy"] = True
    return ev


def end_heavy_job(
    context: ContextTypes.DEFAULT_TYPE, job_id: int | None = None
) -> None:
    """Solo limpia si job_id coincide (evita que un trabajo cancelado bloquee el siguiente)."""
    current = get_heavy_job_id(context)
    if current == _JOB_INVALID:
        return
    if job_id is not None and current != job_id:
        return
    context.user_data["heavy_busy"] = False
    context.user_data.pop("heavy_job_id", None)
    context.user_data.pop("active_progress", None)
    ev = context.user_data.pop("cancel_event", None)
    if isinstance(ev, threading.Event):
        ev.clear()


def force_end_heavy_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tras Cancelar: libera de inmediato; invalida trabajos en segundo plano."""
    ev = get_cancel_event(context)
    if isinstance(ev, threading.Event):
        ev.set()
    context.user_data["heavy_busy"] = False
    context.user_data["heavy_job_id"] = _JOB_INVALID
    context.user_data.pop("active_progress", None)


def get_cancel_event(context: ContextTypes.DEFAULT_TYPE) -> threading.Event | None:
    ev = context.user_data.get("cancel_event")
    return ev if isinstance(ev, threading.Event) else None


def set_active_progress(context: ContextTypes.DEFAULT_TYPE, progress: object | None) -> None:
    if progress is None:
        context.user_data.pop("active_progress", None)
    else:
        context.user_data["active_progress"] = progress


def get_active_progress(context: ContextTypes.DEFAULT_TYPE):
    return context.user_data.get("active_progress")


def request_cancel(context: ContextTypes.DEFAULT_TYPE) -> None:
    ev = get_cancel_event(context)
    if isinstance(ev, threading.Event):
        ev.set()


async def reject_if_heavy_busy(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    if not is_heavy_busy(context):
        return False
    chat = update.effective_chat
    if not chat:
        return True
    lang = get_lang(context)
    try:
        await chat.send_message(busy_message(lang), parse_mode="Markdown")
    except Exception:
        await chat.send_message(busy_message(lang).replace("*", ""))
    return True


def should_block_callback(data: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Bloquea solo lo que compite con un trabajo pesado en curso."""
    if not is_heavy_busy(context):
        return False
    if data == "action:cancel":
        return False
    if data in ("home", "help", "fmt_back") or data.startswith(
        ("tx_nav:", "sum_nav:", "mom_nav:", "hi_nav:", "search_nav:")
    ):
        return False
    if data.startswith("mode:"):
        return False
    if data in ("fmt_get:mp3", "fmt_get:mp3_direct"):
        return False
    if data.startswith(("link_mode:", "job_mode:", "audio_lang:", "ui_lang:")):
        return False
    if data.startswith(
        ("fmt_get:", "action:summary", "action:translate", "action:variant:", "action:search")
    ):
        return not has_cached_transcript(context)
    if data.startswith("action:"):
        return True
    return False

