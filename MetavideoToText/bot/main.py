import logging
import sys

from telegram.error import BadRequest, Conflict
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from bot.branding import BOT_PROFILE_BY_LANG, BOT_PROFILE_SHORT_BY_LANG
from bot.i18n import ensure_user_lang, lang_from_telegram, t
from bot.config import TELEGRAM_BOT_TOKEN
from bot.handlers.process import (
    callback_query,
    cmd_help,
    cmd_idioma,
    cmd_start,
    handle_cancel,
    route_message,
)
from bot.services.bot_commands import sync_default_commands
from bot.services.cleanup_temp import cleanup_old_files

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, Conflict):
        logger.warning(
            "409 Conflict: hay OTRA ventana con el bot abierta. "
            "Cierra todas y deja solo una (DETENER_BOT.cmd y luego LANZAR)."
        )
        return
    if isinstance(err, BadRequest) and "too big" in str(err).lower():
        chat = update.effective_chat if update else None
        if chat:
            lang = "es"
            user = getattr(update, "effective_user", None)
            if user and getattr(user, "language_code", None):
                lang = lang_from_telegram(user.language_code)
            elif context.user_data:
                ensure_user_lang(update, context)
                from bot.i18n import get_lang

                lang = get_lang(context)
            await chat.send_message(t("error_file_too_big", lang))
        return
    logger.exception("Error no controlado: %s", err)


async def _on_startup(app: Application) -> None:
    n = cleanup_old_files()
    if n:
        logger.info("Al arrancar: limpiados %s archivos viejos en temp/", n)
    try:
        for code, text in BOT_PROFILE_BY_LANG.items():
            await app.bot.set_my_description(text, language_code=code)
        for code, text in BOT_PROFILE_SHORT_BY_LANG.items():
            await app.bot.set_my_short_description(text, language_code=code)
        await app.bot.set_my_description(BOT_PROFILE_BY_LANG["es"])
        await app.bot.set_my_short_description(BOT_PROFILE_SHORT_BY_LANG["es"])
        logger.info("Descripción del bot actualizada (ES/EN/FR/RU + fallback ES).")
    except Exception as e:
        logger.warning("No se pudo actualizar la descripción del bot: %s", e)
    try:
        await sync_default_commands(app.bot)
        logger.info("Comandos por defecto en español; sin botón Menu lateral.")
    except Exception as e:
        logger.warning("No se pudieron registrar comandos: %s", e)


async def _periodic_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    cleanup_old_files()


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("Falta TELEGRAM_BOT_TOKEN en el archivo .env")
        sys.exit(1)

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .post_init(_on_startup)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("idioma", cmd_idioma))
    app.add_handler(CommandHandler("language", cmd_idioma))
    app.add_handler(CommandHandler("langue", cmd_idioma))
    app.add_handler(CommandHandler("cancel", handle_cancel))
    app.add_handler(CallbackQueryHandler(callback_query))
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            route_message,
        )
    )
    app.add_error_handler(error_handler)

    if app.job_queue:
        app.job_queue.run_repeating(_periodic_cleanup, interval=900, first=300)

    logger.info("MetavideoToText_bot en marcha (solo debe haber UNA ventana CMD)...")
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
