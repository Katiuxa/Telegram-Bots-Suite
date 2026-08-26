from telegram import Update
from telegram.ext import ContextTypes

from bot.i18n import (
    ensure_user_lang,
    get_lang,
    t,
)
from bot.keyboards import reply_keyboard, ui_lang_keyboard
from bot.services.user_busy import is_heavy_busy


async def apply_ui_lang_change(
    update: Update, context: ContextTypes.DEFAULT_TYPE, new_lang: str
) -> None:
    """Cambia solo el idioma de la app (menú)."""
    from bot.services.bot_commands import sync_chat_commands
    from bot.services.transcript_lang import set_ui_lang

    chat = update.effective_chat
    if not chat:
        return

    context.user_data["lang_initialized"] = True
    context.user_data["ui_lang_manual"] = True
    code = set_ui_lang(context, new_lang)
    await sync_chat_commands(context.bot, chat.id, code)
    await chat.send_message(
        t("lang_changed", code),
        parse_mode="Markdown",
        reply_markup=reply_keyboard(code),
    )
    await send_main_menu(update, context)


async def send_idioma_picker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return
    lang = ensure_user_lang(update, context)
    await chat.send_message(
        t("idioma_prompt", lang),
        parse_mode="Markdown",
        reply_markup=ui_lang_keyboard(lang),
    )


async def send_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.services.bot_commands import sync_chat_commands

    chat = update.effective_chat
    if not chat:
        return

    lang = ensure_user_lang(update, context)
    await sync_chat_commands(context.bot, chat.id, lang)
    await send_main_menu(update, context)


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if not chat:
        return

    lang = ensure_user_lang(update, context)
    await chat.send_message(
        t("menu_main_text", lang, lang_label=t("lang_name", lang)),
        parse_mode="Markdown",
        reply_markup=reply_keyboard(lang),
    )


async def send_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ayuda retirada: mismo texto corto del menú."""
    await send_main_menu(update, context)


async def handle_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Ya no hay teclado inferior con Inicio/Ayuda."""
    if is_heavy_busy(context):
        return False
    return False


MODE_HINTS = {
    "audio": "mode_audio",
    "video": "mode_video",
    "link": "mode_link",
}


def mode_hint(mode: str, lang: str | None = None) -> str:
    key = MODE_HINTS.get(mode, "mode_default")
    return t(key, lang)


send_home = send_main_menu
