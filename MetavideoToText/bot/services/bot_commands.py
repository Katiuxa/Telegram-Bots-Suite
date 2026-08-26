"""Comandos del menú / de Telegram, localizados por chat."""

from __future__ import annotations

import logging

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonDefault,
)
from telegram.ext import ExtBot

from bot.i18n import normalize_lang

logger = logging.getLogger(__name__)

# Solo start + idioma (sin help ni cancel). Por defecto español.
_COMMANDS: dict[str, list[tuple[str, str]]] = {
    "es": [
        ("start", "Menú"),
        ("idioma", "Idioma"),
    ],
    "en": [
        ("start", "Menu"),
        ("language", "Language"),
    ],
    "fr": [
        ("start", "Menu"),
        ("langue", "Langue"),
    ],
    "ru": [
        ("start", "Меню"),
        ("language", "Язык"),
    ],
}


def bot_commands_for_lang(lang: str | None) -> list[BotCommand]:
    code = normalize_lang(lang)
    pairs = _COMMANDS.get(code) or _COMMANDS["es"]
    return [BotCommand(cmd, desc) for cmd, desc in pairs]


async def hide_menu_button(bot: ExtBot, chat_id: int | None = None) -> None:
    """Quita el botón Menu (sidebar) junto al clip; los comandos siguen con /."""
    try:
        if chat_id is not None:
            await bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonDefault(),
            )
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    except Exception as e:
        logger.warning("No se pudo ocultar MenuButton: %s", e)


async def sync_default_commands(bot: ExtBot) -> None:
    """Solo español por defecto (no seguir el idioma del cliente Telegram)."""
    await bot.set_my_commands(
        bot_commands_for_lang("es"),
        scope=BotCommandScopeDefault(),
    )
    await hide_menu_button(bot)


async def sync_chat_commands(bot: ExtBot, chat_id: int, lang: str | None) -> None:
    """Fuerza el menú / de este chat al idioma de la app elegido."""
    try:
        await bot.set_my_commands(
            bot_commands_for_lang(lang),
            scope=BotCommandScopeChat(chat_id=chat_id),
        )
        await hide_menu_button(bot, chat_id)
    except Exception as e:
        logger.warning("No se pudieron sincronizar comandos del chat %s: %s", chat_id, e)
