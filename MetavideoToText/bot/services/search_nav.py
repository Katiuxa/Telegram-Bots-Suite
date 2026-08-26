"""Navegación de resultados de búsqueda en la transcripción."""

from __future__ import annotations

import logging

from telegram.ext import ContextTypes

from bot.i18n import get_lang, t
from bot.keyboards import search_result_keyboard
from bot.services.source_links import seek_button_label, seek_url_for_time
from bot.services.transcript_search import (
    format_search_result_message,
    hits_from_stored,
)

logger = logging.getLogger(__name__)


def clear_search_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in (
        "search_hits",
        "search_page",
        "search_query",
        "search_view_msg_id",
        "search_view_chat_id",
        "awaiting_search",
    ):
        context.user_data.pop(key, None)


def store_search_results(
    context: ContextTypes.DEFAULT_TYPE, query: str, hits_stored: list[dict]
) -> None:
    context.user_data["search_hits"] = hits_stored
    context.user_data["search_query"] = query.strip()
    context.user_data["search_page"] = 0


def get_search_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        return max(0, int(context.user_data.get("search_page", 0)))
    except (TypeError, ValueError):
        return 0


def set_search_page(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    hits = hits_from_stored(context.user_data.get("search_hits"))
    total = len(hits)
    if total < 1:
        context.user_data["search_page"] = 0
        return
    context.user_data["search_page"] = max(0, min(page, total - 1))


async def _edit_search_message(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    msg_id: int,
    text: str,
    markup,
) -> None:
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception:
        plain = text.replace("*", "").replace("_", "").replace("`", "")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=plain,
            reply_markup=markup,
            disable_web_page_preview=True,
        )


async def show_search_result(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    msg_id: int,
    *,
    page: int | None = None,
) -> bool:
    hits = hits_from_stored(context.user_data.get("search_hits"))
    query = str(context.user_data.get("search_query") or "")
    lang = get_lang(context)
    if not hits or not query:
        return False

    if page is not None:
        set_search_page(context, page)
    page = get_search_page(context)
    hit = hits[page]
    seek_url = seek_url_for_time(context, hit.start)
    text = format_search_result_message(
        query, hit, page=page, total=len(hits), lang=lang
    )
    markup = search_result_keyboard(
        page,
        len(hits),
        seek_url=seek_url,
        seek_label=seek_button_label(context),
        lang=lang,
    )
    await _edit_search_message(context, chat_id, msg_id, text, markup)
    return True


async def send_search_results(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    query: str,
    hits_stored: list[dict],
) -> None:
    store_search_results(context, query, hits_stored)
    hits = hits_from_stored(hits_stored)
    lang = get_lang(context)
    page = 0
    hit = hits[page]
    seek_url = seek_url_for_time(context, hit.start)
    text = format_search_result_message(
        query, hit, page=page, total=len(hits), lang=lang
    )
    markup = search_result_keyboard(
        page,
        len(hits),
        seek_url=seek_url,
        seek_label=seek_button_label(context),
        lang=lang,
    )
    try:
        sent = await context.bot.send_message(
            chat_id,
            text,
            parse_mode="Markdown",
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    except Exception:
        sent = await context.bot.send_message(
            chat_id,
            text.replace("*", ""),
            reply_markup=markup,
            disable_web_page_preview=True,
        )
    context.user_data["search_view_msg_id"] = sent.message_id
    context.user_data["search_view_chat_id"] = chat_id


async def handle_search_nav(
    update, context: ContextTypes.DEFAULT_TYPE, action: str
) -> None:
    query = update.callback_query
    hits = hits_from_stored(context.user_data.get("search_hits"))
    lang = get_lang(context)
    if not hits:
        await query.answer(t("search_expired", lang), show_alert=True)
        return

    chat_id = context.user_data.get("search_view_chat_id") or query.message.chat_id
    msg_id = context.user_data.get("search_view_msg_id") or query.message.message_id

    if action == "noop":
        await query.answer()
        return

    page = get_search_page(context)
    total = len(hits)

    if action == "prev":
        await show_search_result(context, chat_id, msg_id, page=page - 1)
        page = get_search_page(context)
        await query.answer(t("search_nav_toast", lang, cur=page + 1, total=total))
        return

    if action == "next":
        await show_search_result(context, chat_id, msg_id, page=page + 1)
        page = get_search_page(context)
        await query.answer(t("search_nav_toast", lang, cur=page + 1, total=total))
        return

    if action == "new":
        context.user_data["awaiting_search"] = True
        await query.answer(t("search_again_toast", lang))
        await context.bot.send_message(
            chat_id,
            t("search_prompt", lang),
            parse_mode="Markdown",
        )
        return

    await query.answer()
