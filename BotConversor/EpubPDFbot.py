"""Variante de emergencia: Calibre escribe en /tmp (tmpfs) cuando la MicroSD está llena.

En la Pi 3B (1 GB) /tmp vive en RAM. Sirve para no tumbar el disco; hay que
borrar el fichero en el finally o se come la memoria. El bot en producción
es BotConversor.py (temp en disco cuando la SD ya es de 128 GB).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys

import telebot
from telebot import types

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("conversor-tmp")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno.")
bot = telebot.TeleBot(TOKEN)

PATH_BASE = "/tmp/BotConversor"
PATH_LIBROS = os.path.join(PATH_BASE, "libros")

if os.path.exists(PATH_BASE):
    shutil.rmtree(PATH_BASE)
os.makedirs(PATH_LIBROS, exist_ok=True)

user_data = {}


def menu_principal():
    markup = types.InlineKeyboardMarkup(row_width=2)
    formatos = ["EPUB", "PDF", "MOBI", "DOCX", "ODT"]
    botones = [
        types.InlineKeyboardButton(f"📁 {f}", callback_data=f"in_{f.lower()}")
        for f in formatos
    ]
    markup.add(*botones)
    return markup


def menu_salida(formato_in):
    markup = types.InlineKeyboardMarkup(row_width=2)
    formatos = ["EPUB", "PDF", "MOBI", "DOCX", "ODT"]
    botones = [
        types.InlineKeyboardButton(f"➡️ {f}", callback_data=f"out_{f.lower()}")
        for f in formatos
        if f.lower() != formato_in
    ]
    markup.add(*botones)
    markup.add(types.InlineKeyboardButton("⬅️ Volver", callback_data="volver"))
    return markup


@bot.message_handler(commands=["start", "menu"])
def cmd_start(message):
    user_data[message.chat.id] = {}
    bot.send_message(
        message.chat.id,
        "Conversor de archivos (temp en RAM). Selecciona formato de entrada:",
        reply_markup=menu_principal(),
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if chat_id not in user_data:
        user_data[chat_id] = {}

    if call.data == "volver":
        bot.edit_message_text(
            "Selecciona entrada:",
            chat_id,
            call.message.message_id,
            reply_markup=menu_principal(),
        )
    elif call.data.startswith("in_"):
        f_in = call.data.split("_")[1]
        user_data[chat_id]["in"] = f_in
        bot.edit_message_text(
            f"De: {f_in.upper()}\n¿A qué formato lo paso?",
            chat_id,
            call.message.message_id,
            reply_markup=menu_salida(f_in),
        )
    elif call.data.startswith("out_"):
        user_data[chat_id]["out"] = call.data.split("_")[1]
        bot.edit_message_text(
            f"Envíame el archivo {user_data[chat_id]['in'].upper()} ahora.",
            chat_id,
            call.message.message_id,
        )


@bot.message_handler(content_types=["document"])
def handle_docs(message):
    chat_id = message.chat.id
    input_path = None
    output_path = None

    if chat_id not in user_data or "out" not in user_data[chat_id]:
        bot.reply_to(message, "Primero configura con /start")
        return

    try:
        f_out = user_data[chat_id]["out"]
        msg_espere = bot.reply_to(message, "Procesando en RAM...")
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        nombre_orig = message.document.file_name or f"entrada.{f_out}"
        input_path = os.path.join(PATH_LIBROS, nombre_orig)
        output_path = os.path.join(
            PATH_LIBROS, f"{os.path.splitext(nombre_orig)[0]}.{f_out}"
        )
        with open(input_path, "wb") as f:
            f.write(downloaded_file)
        bot.edit_message_text("Convirtiendo...", chat_id, msg_espere.message_id)
        resultado = subprocess.run(
            ["ebook-convert", input_path, output_path],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if resultado.returncode == 0 and os.path.isfile(output_path):
            bot.edit_message_text("Enviando...", chat_id, msg_espere.message_id)
            with open(output_path, "rb") as f:
                bot.send_document(chat_id, f)
        else:
            log.error("Calibre rc=%s stderr=%s", resultado.returncode, resultado.stderr[-400:])
            bot.send_message(chat_id, "Error de conversión. El archivo podría ser incompatible.")
    except subprocess.TimeoutExpired:
        log.error("Calibre timeout 600s")
        bot.reply_to(message, "La conversión superó 10 minutos y se abortó.")
    except Exception:
        log.exception("Fallo en conversión")
        bot.reply_to(message, "Fallo al convertir.")
    finally:
        for path in (input_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    log.warning("No se pudo borrar %s: %s", path, exc)


if __name__ == "__main__":
    log.info("Conversor RAM activo en %s", PATH_BASE)
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        log.exception("Polling detenido")
        sys.exit(1)
