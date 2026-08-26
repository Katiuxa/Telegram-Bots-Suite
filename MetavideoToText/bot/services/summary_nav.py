"""Navegación del resumen (callbacks sum_nav)."""

from telegram.ext import ContextTypes

from bot.i18n import get_lang, t
from bot.keyboards import summary_page_keyboard
from bot.services.summary_pages import (
    get_summary_page,
    page_body,
    set_summary_page,
    summary_header,
)


async def handle_summary_nav(
    update, context: ContextTypes.DEFAULT_TYPE, action: str
) -> None:
    query = update.callback_query
    lang = get_lang(context)
    flat = context.user_data.get("sum_parts")
    if not flat:
        await query.answer(t("no_summary_saved", lang), show_alert=True)
        return

    if action == "noop":
        await query.answer()
        return

    page = get_summary_page(context)
    total = int(context.user_data.get("sum_total_pages", 1))
    if action == "next":
        set_summary_page(context, page + 1)
    elif action == "prev":
        set_summary_page(context, page - 1)
    page = get_summary_page(context)

    body = page_body(flat, page)
    text = summary_header(page, total, lang) + body
    markup = summary_page_keyboard(page, total, lang)
    chat_id = context.user_data.get("sum_view_chat_id") or query.message.chat_id
    msg_id = context.user_data.get("sum_view_msg_id") or query.message.message_id

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=markup,
        )
    except Exception:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text.replace("*", "").replace("_", ""),
            reply_markup=markup,
        )
    await query.answer(t("page_toast", lang, cur=page + 1, total=total))
