"""Navegación de highlights: listado, momentos y fragmentos."""

from telegram.ext import ContextTypes

from bot.i18n import get_lang, t
from bot.i18n_progress import prog
from bot.keyboards import highlight_page_keyboard, highlights_toc_keyboard
from bot.services.source_links import (
    seek_button_label,
    seek_hint_markdown,
    seek_url_for_time,
)
from bot.services.highlights_view import (
    format_highlight_telegram,
    format_highlights_toc,
    get_hi_subpage,
    get_hi_toc_page,
    get_highlights_page,
    get_stored_highlights,
    load_highlight_quote_pages,
    set_hi_subpage,
    set_hi_toc_page,
    set_highlights_page,
)


async def _edit_highlight_message(
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
        )
    except Exception:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text.replace("*", "").replace("`", "").replace("_", ""),
            reply_markup=markup,
        )


async def show_highlights_toc(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    msg_id: int,
    *,
    toc_page: int | None = None,
) -> None:
    items = get_stored_highlights(context)
    if toc_page is not None:
        set_hi_toc_page(context, toc_page)
    lang = get_lang(context)
    tp = get_hi_toc_page(context)
    context.user_data["hi_mode"] = "toc"
    text = format_highlights_toc(items, tp, lang=lang)
    markup = highlights_toc_keyboard(items, tp, lang=lang)
    await _edit_highlight_message(context, chat_id, msg_id, text, markup)


async def show_highlight_part(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    msg_id: int,
    page: int,
    *,
    sub_page: int | None = None,
) -> None:
    items = get_stored_highlights(context)
    total = len(items)
    if not items:
        return
    set_highlights_page(context, page)
    page = get_highlights_page(context)
    context.user_data["hi_mode"] = "part"
    item = items[page]
    quote_pages = load_highlight_quote_pages(context, item)
    if sub_page is not None:
        set_hi_subpage(context, sub_page)
    sp = get_hi_subpage(context)
    seek_url = seek_url_for_time(context, item.start)
    seek_label = seek_button_label(context)
    text = format_highlight_telegram(
        item,
        page,
        total,
        text_page=sp,
        text_total=len(quote_pages),
        quote_slice=quote_pages[sp],
        seek_hint=seek_hint_markdown(context) if seek_url else "",
    )
    lang = get_lang(context)
    markup = highlight_page_keyboard(
        page,
        total,
        text_page=sp,
        text_total=len(quote_pages),
        seek_url=seek_url,
        seek_label=seek_label,
        lang=lang,
    )
    await _edit_highlight_message(context, chat_id, msg_id, text, markup)


async def handle_highlights_nav(
    update, context: ContextTypes.DEFAULT_TYPE, action: str
) -> None:
    query = update.callback_query
    items = get_stored_highlights(context)
    lang = get_lang(context)
    if not items:
        await query.answer(t("no_highlights_saved", lang), show_alert=True)
        return

    chat_id = context.user_data.get("hi_view_chat_id") or query.message.chat_id
    msg_id = context.user_data.get("hi_view_msg_id") or query.message.message_id

    if action == "noop":
        await query.answer()
        return

    if action == "toc":
        await show_highlights_toc(context, chat_id, msg_id)
        await query.answer(prog("highlights_list", lang))
        return

    if action.startswith("goto:"):
        try:
            page = int(action.split(":", 1)[1])
        except ValueError:
            await query.answer()
            return
        await show_highlight_part(context, chat_id, msg_id, page, sub_page=0)
        await query.answer(items[page].reason[:60])
        return

    if action == "tocprev":
        await show_highlights_toc(
            context, chat_id, msg_id, toc_page=get_hi_toc_page(context) - 1
        )
        await query.answer()
        return

    if action == "tocnext":
        await show_highlights_toc(
            context, chat_id, msg_id, toc_page=get_hi_toc_page(context) + 1
        )
        await query.answer()
        return

    page = get_highlights_page(context)
    quote_pages = context.user_data.get("hi_quote_pages") or []

    if action == "subnext":
        await show_highlight_part(
            context, chat_id, msg_id, page, sub_page=get_hi_subpage(context) + 1
        )
        await query.answer()
        return

    if action == "subprev":
        await show_highlight_part(
            context, chat_id, msg_id, page, sub_page=get_hi_subpage(context) - 1
        )
        await query.answer()
        return

    total = len(items)
    if action == "next":
        await show_highlight_part(context, chat_id, msg_id, page + 1, sub_page=0)
    elif action == "prev":
        await show_highlight_part(context, chat_id, msg_id, page - 1, sub_page=0)
    else:
        await query.answer()
        return
    page = get_highlights_page(context)
    sp = get_hi_subpage(context)
    hint = f"Highlight {page + 1}/{total}"
    if len(quote_pages) > 1:
        hint += f" · frag. {sp + 1}/{len(quote_pages)}"
    await query.answer(hint)
