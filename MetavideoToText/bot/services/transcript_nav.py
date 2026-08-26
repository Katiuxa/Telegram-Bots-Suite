"""Navegación de bloques de transcripción (callbacks tx_nav)."""

from telegram.ext import ContextTypes

from bot.i18n import get_lang, t
from bot.keyboards import transcript_page_keyboard
from bot.services.transcript_pages import (
    get_transcript_page,
    page_body,
    set_transcript_page,
    transcript_header,
)


async def handle_transcript_nav(
    update, context: ContextTypes.DEFAULT_TYPE, action: str
) -> None:
    query = update.callback_query
    lang = get_lang(context)
    flat = context.user_data.get("tx_parts")
    if not flat:
        await query.answer(t("no_transcript_saved", lang), show_alert=True)
        return

    if action == "noop":
        await query.answer()
        return

    page = get_transcript_page(context)
    total = int(context.user_data.get("tx_total_pages", 1))
    if action == "next":
        set_transcript_page(context, page + 1)
    elif action == "prev":
        set_transcript_page(context, page - 1)
    page = get_transcript_page(context)

    body = page_body(flat, page)
    text = transcript_header(page, total, lang, context=context) + body
    markup = transcript_page_keyboard(page, total, lang, context=context)
    chat_id = context.user_data.get("tx_view_chat_id") or query.message.chat_id
    msg_id = context.user_data.get("tx_view_msg_id") or query.message.message_id

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
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
