"""Navegación del índice: listado, capítulos y fragmentos de texto."""

from telegram.ext import ContextTypes

from bot.i18n import get_lang, t
from bot.i18n_progress import prog
from bot.keyboards import index_toc_keyboard, moment_page_keyboard
from bot.services.source_links import (
    seek_button_label,
    seek_hint_markdown,
    seek_url_for_time,
)
from bot.services.moments_view import (
    format_index_toc,
    format_moment_telegram,
    get_mom_subpage,
    get_mom_toc_page,
    get_moments_page,
    get_stored_moment_blocks,
    load_moment_body_pages,
    set_mom_subpage,
    set_mom_toc_page,
    set_moments_page,
)


async def _edit_index_message(
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
            text=text.replace("*", "").replace("`", ""),
            reply_markup=markup,
        )


async def show_index_toc(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    msg_id: int,
    *,
    toc_page: int | None = None,
) -> None:
    blocks = get_stored_moment_blocks(context)
    if toc_page is not None:
        set_mom_toc_page(context, toc_page)
    lang = get_lang(context)
    tp = get_mom_toc_page(context)
    context.user_data["mom_mode"] = "toc"
    text = format_index_toc(blocks, tp, lang=lang)
    markup = index_toc_keyboard(blocks, tp, lang=lang)
    await _edit_index_message(context, chat_id, msg_id, text, markup)


async def show_index_part(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    msg_id: int,
    page: int,
    *,
    sub_page: int | None = None,
) -> None:
    blocks = get_stored_moment_blocks(context)
    total = len(blocks)
    if not blocks:
        return
    set_moments_page(context, page)
    page = get_moments_page(context)
    context.user_data["mom_mode"] = "part"
    block = blocks[page]
    body_pages = load_moment_body_pages(context, block)
    if sub_page is not None:
        set_mom_subpage(context, sub_page)
    sp = get_mom_subpage(context)
    seek_url = seek_url_for_time(context, block.start)
    seek_label = seek_button_label(context)
    text = format_moment_telegram(
        block,
        page,
        total,
        text_page=sp,
        text_total=len(body_pages),
        body_slice=body_pages[sp],
        seek_hint=seek_hint_markdown(context) if seek_url else "",
    )
    lang = get_lang(context)
    markup = moment_page_keyboard(
        page,
        total,
        text_page=sp,
        text_total=len(body_pages),
        seek_url=seek_url,
        seek_label=seek_label,
        lang=lang,
    )
    await _edit_index_message(context, chat_id, msg_id, text, markup)


async def handle_moments_nav(
    update, context: ContextTypes.DEFAULT_TYPE, action: str
) -> None:
    query = update.callback_query
    blocks = get_stored_moment_blocks(context)
    lang = get_lang(context)
    if not blocks:
        await query.answer(t("no_index_saved", lang), show_alert=True)
        return

    chat_id = context.user_data.get("mom_view_chat_id") or query.message.chat_id
    msg_id = context.user_data.get("mom_view_msg_id") or query.message.message_id

    if action == "noop":
        await query.answer()
        return

    if action == "toc":
        await show_index_toc(context, chat_id, msg_id)
        await query.answer(prog("chapter_list", lang))
        return

    if action.startswith("goto:"):
        try:
            page = int(action.split(":", 1)[1])
        except ValueError:
            await query.answer()
            return
        await show_index_part(context, chat_id, msg_id, page, sub_page=0)
        await query.answer(blocks[page].title[:60])
        return

    if action == "tocprev":
        await show_index_toc(
            context, chat_id, msg_id, toc_page=get_mom_toc_page(context) - 1
        )
        await query.answer()
        return

    if action == "tocnext":
        await show_index_toc(
            context, chat_id, msg_id, toc_page=get_mom_toc_page(context) + 1
        )
        await query.answer()
        return

    page = get_moments_page(context)
    body_pages = context.user_data.get("mom_body_pages") or []

    if action == "subnext":
        await show_index_part(
            context, chat_id, msg_id, page, sub_page=get_mom_subpage(context) + 1
        )
        await query.answer()
        return

    if action == "subprev":
        await show_index_part(
            context, chat_id, msg_id, page, sub_page=get_mom_subpage(context) - 1
        )
        await query.answer()
        return

    total = len(blocks)
    if action == "next":
        await show_index_part(context, chat_id, msg_id, page + 1, sub_page=0)
    elif action == "prev":
        await show_index_part(context, chat_id, msg_id, page - 1, sub_page=0)
    else:
        await query.answer()
        return
    page = get_moments_page(context)
    sp = get_mom_subpage(context)
    hint = f"Cap. {page + 1}/{total}"
    if len(body_pages) > 1:
        hint += f" · frag. {sp + 1}/{len(body_pages)}"
    await query.answer(hint)
