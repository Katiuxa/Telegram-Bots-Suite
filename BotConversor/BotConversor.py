import logging
import os
import re
import select
import subprocess
import threading
import time
import uuid

import telebot
from telebot import types

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("too-epub2pdf")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno.")
bot = telebot.TeleBot(TOKEN)

PATH_BASE = "/home/admin/temp_conversor"
PATH_LIBROS = os.path.join(PATH_BASE, "libros")
TIMEOUT_CONVERSION = 600
INTERVALO_BARRA = 2

if not os.path.exists(PATH_LIBROS):
    os.makedirs(PATH_LIBROS, exist_ok=True)

FORMATOS_SOPORTADOS = ["epub", "pdf", "mobi", "docx", "odt"]

MIME_A_FORMATO = {
    "application/epub+zip": "epub",
    "application/pdf": "pdf",
    "application/x-mobipocket-ebook": "mobi",
    "application/vnd.amazon.ebook": "mobi",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.oasis.opendocument.text": "odt",
}

user_data = {}
busy_lock = threading.Lock()
busy_chats = set()
cancel_events = {}   # chat_id -> threading.Event
active_procs = {}    # chat_id -> subprocess.Popen


def teclado_fijo():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("MENÚ PRINCIPAL"))
    return markup


def menu_salida(formato_in):
    markup = types.InlineKeyboardMarkup(row_width=2)
    botones = [
        types.InlineKeyboardButton(f"➡️ {f.upper()}", callback_data=f"out_{f}")
        for f in FORMATOS_SOPORTADOS
        if f != formato_in
    ]
    markup.add(*botones)
    markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="volver"))
    return markup


def boton_cancelar():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancelar", callback_data="volver"))
    return markup


def barra_progreso(porcentaje, ancho=14):
    p = max(0, min(100, int(porcentaje)))
    lleno = round(ancho * p / 100)
    vacio = ancho - lleno
    return f"[{'█' * lleno}{'░' * vacio}] {p}%"


def extraer_porcentaje(texto, actual=0):
    """Calibre escribe el progreso con \\r en la misma línea, no solo con saltos de línea."""
    for fragmento in re.split(r"[\r\n]+", texto):
        for match in re.finditer(r"(?<!\d)(\d{1,3})\s*%", fragmento):
            actual = max(actual, int(match.group(1)))
    return min(actual, 100)


def limpiar_nombre(nombre):
    nombre = nombre.replace(" ", "_")
    nombre = re.sub(r"[^\w.\-]", "_", nombre, flags=re.UNICODE)
    return nombre or "archivo"


def detectar_formato_entrada(document):
    nombre = document.file_name or ""
    _, ext = os.path.splitext(nombre)
    f_in = ext.lower().lstrip(".")
    if f_in in FORMATOS_SOPORTADOS:
        return f_in

    mime = (document.mime_type or "").lower()
    if mime in MIME_A_FORMATO:
        return MIME_A_FORMATO[mime]

    return None


def nombre_archivo_seguro(document, f_in):
    nombre = document.file_name
    if nombre:
        base, ext = os.path.splitext(limpiar_nombre(nombre))
        if not ext:
            return f"{base}.{f_in}"
        return limpiar_nombre(nombre)

    stamp = int(time.time())
    return f"documento_{stamp}.{f_in}"


def marcar_ocupado(chat_id):
    with busy_lock:
        if chat_id in busy_chats:
            return False
        busy_chats.add(chat_id)
        return True


def iniciar_trabajo(chat_id):
    cancel_events[chat_id] = threading.Event()


def esta_cancelado(chat_id):
    evento = cancel_events.get(chat_id)
    return evento is not None and evento.is_set()


def solicitar_cancelacion(chat_id):
    evento = cancel_events.get(chat_id)
    if evento:
        evento.set()
    proc = active_procs.get(chat_id)
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def finalizar_trabajo(chat_id):
    cancel_events.pop(chat_id, None)
    active_procs.pop(chat_id, None)
    with busy_lock:
        busy_chats.discard(chat_id)
    user_data.pop(chat_id, None)


def limpiar_seleccion(chat_id):
    user_data.pop(chat_id, None)


def editar_seguro(chat_id, message_id, texto, **kwargs):
    try:
        bot.edit_message_text(texto, chat_id, message_id, **kwargs)
    except Exception:
        pass


@bot.message_handler(func=lambda message: message.text == "MENÚ PRINCIPAL")
@bot.message_handler(commands=["start", "menu"])
def cmd_start(message):
    solicitar_cancelacion(message.chat.id)
    finalizar_trabajo(message.chat.id)
    bot.send_message(
        message.chat.id,
        "⚙️ **CONVERSOR DE ARCHIVOS**\n\n"
        "Formatos compatibles: EPUB, PDF, MOBI, DOCX, ODT\n\n"
        "Envíame el documento que deseas convertir (también reenviado).",
        parse_mode="Markdown",
        reply_markup=teclado_fijo(),
    )


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id

    if call.data == "volver":
        bot.answer_callback_query(call.id, "Cancelado")
        if chat_id in busy_chats:
            solicitar_cancelacion(chat_id)
            editar_seguro(
                chat_id,
                call.message.message_id,
                "❌ Cancelado. Deteniendo conversión...",
            )
        else:
            limpiar_seleccion(chat_id)
            editar_seguro(
                chat_id,
                call.message.message_id,
                "Se ha cancelado la operación.\n\nEnvíame el archivo que deseas convertir:",
            )
        return

    if call.data.startswith("out_"):
        if chat_id not in user_data or "in" not in user_data[chat_id]:
            bot.answer_callback_query(call.id, "Sesión expirada.")
            editar_seguro(
                chat_id,
                call.message.message_id,
                "El estado de la conversión expiró. Vuelve a enviar el archivo.",
            )
            return

        if not marcar_ocupado(chat_id):
            bot.answer_callback_query(call.id, "Ya hay una conversión en curso.")
            return

        iniciar_trabajo(chat_id)

        f_out = call.data.split("_", 1)[1]
        user_data[chat_id]["out"] = f_out

        f_in = user_data[chat_id]["in"]
        bot.answer_callback_query(call.id, f"Convirtiendo a {f_out.upper()}")
        editar_seguro(
            chat_id,
            call.message.message_id,
            f"Configurado: **{f_in.upper()}** ➡️ **{f_out.upper()}**\n\n"
            f"⬇️ Descargando...\n{barra_progreso(0)}",
            parse_mode="Markdown",
            reply_markup=boton_cancelar(),
        )

        thread = threading.Thread(
            target=procesar_conversion,
            args=(chat_id, call.message.message_id),
            daemon=True,
        )
        thread.start()


@bot.message_handler(content_types=["document"])
def handle_docs(message):
    chat_id = message.chat.id

    if chat_id in busy_chats:
        bot.reply_to(
            message,
            "Ya hay una conversión en curso. Espera a que termine o pulsa Cancelar.",
            reply_markup=teclado_fijo(),
        )
        return

    document = message.document
    f_in = detectar_formato_entrada(document)

    if not f_in:
        formatos_txt = ", ".join(f.upper() for f in FORMATOS_SOPORTADOS)
        bot.reply_to(
            message,
            f"❌ Formato no reconocido.\n\nFormatos válidos: {formatos_txt}",
            reply_markup=teclado_fijo(),
        )
        return

    user_data[chat_id] = {
        "in": f_in,
        "file_id": document.file_id,
        "file_name": nombre_archivo_seguro(document, f_in),
    }

    bot.reply_to(
        message,
        f"📄 Archivo detectado: **{f_in.upper()}**\n\n¿A qué formato deseas convertirlo?",
        parse_mode="Markdown",
        reply_markup=menu_salida(f_in),
    )


def ejecutar_conversion_con_progreso(chat_id, message_id, input_path, output_path, f_in, f_out):
    proc = subprocess.Popen(
        ["ebook-convert", input_path, output_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    active_procs[chat_id] = proc

    porcentaje = 15
    ultima_actualizacion = 0.0
    buffer = b""

    def actualizar_barra(forzar=False):
        nonlocal ultima_actualizacion
        ahora = time.time()
        if not forzar and ahora - ultima_actualizacion < INTERVALO_BARRA:
            return
        if esta_cancelado(chat_id):
            return
        editar_seguro(
            chat_id,
            message_id,
            f"⏳ Convirtiendo **{f_in.upper()}** ➡️ **{f_out.upper()}**\n\n{barra_progreso(porcentaje)}",
            parse_mode="Markdown",
            reply_markup=boton_cancelar(),
        )
        ultima_actualizacion = ahora

    try:
        while True:
            if esta_cancelado(chat_id):
                return None, "cancelled"

            if proc.poll() is not None:
                resto = proc.stdout.read()
                if resto:
                    buffer += resto
                break

            listo, _, _ = select.select([proc.stdout], [], [], 0.4)
            if listo:
                chunk = proc.stdout.read(4096)
                if chunk:
                    buffer += chunk
                    if len(buffer) > 16384:
                        buffer = buffer[-8192:]
                    texto = buffer.decode("utf-8", errors="replace")
                    nuevo = extraer_porcentaje(texto, porcentaje)
                    if nuevo > porcentaje:
                        porcentaje = nuevo
                        actualizar_barra(forzar=True)

            actualizar_barra()

        if esta_cancelado(chat_id):
            return None, "cancelled"

        texto_final = buffer.decode("utf-8", errors="replace")
        porcentaje = extraer_porcentaje(texto_final, porcentaje)
        if porcentaje < 100:
            porcentaje = 100
            actualizar_barra(forzar=True)

        return proc.returncode, texto_final
    finally:
        if chat_id in active_procs and active_procs[chat_id] is proc:
            active_procs.pop(chat_id, None)
        if proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass


def procesar_conversion(chat_id, message_id):
    input_path = None
    output_path = None
    cancelado = False

    try:
        datos = user_data.get(chat_id)
        if not datos or "out" not in datos or esta_cancelado(chat_id):
            cancelado = True
            return

        f_in = datos["in"]
        f_out = datos["out"]
        file_id = datos["file_id"]
        nombre_orig = datos["file_name"]

        editar_seguro(
            chat_id,
            message_id,
            f"Configurado: **{f_in.upper()}** ➡️ **{f_out.upper()}**\n\n"
            f"⬇️ Descargando...\n{barra_progreso(5)}",
            parse_mode="Markdown",
            reply_markup=boton_cancelar(),
        )

        if esta_cancelado(chat_id):
            cancelado = True
            return

        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        if esta_cancelado(chat_id):
            cancelado = True
            return

        nombre_limpio = limpiar_nombre(nombre_orig)
        if not os.path.splitext(nombre_limpio)[1]:
            nombre_limpio = f"{nombre_limpio}.{f_in}"

        base = os.path.splitext(nombre_limpio)[0]
        input_path = os.path.join(PATH_LIBROS, f"{base}_{uuid.uuid4().hex[:8]}.{f_in}")
        output_path = os.path.join(PATH_LIBROS, f"{base}_{uuid.uuid4().hex[:8]}.{f_out}")

        with open(input_path, "wb") as f:
            f.write(downloaded_file)

        if esta_cancelado(chat_id):
            cancelado = True
            return

        detectado = detectar_formato_por_contenido(input_path)
        if detectado and detectado != f_in and detectado in FORMATOS_SOPORTADOS:
            f_in = detectado
            user_data[chat_id]["in"] = f_in
            nuevo_input = os.path.join(PATH_LIBROS, f"{base}_{uuid.uuid4().hex[:8]}.{f_in}")
            os.rename(input_path, nuevo_input)
            input_path = nuevo_input

        editar_seguro(
            chat_id,
            message_id,
            f"⏳ Convirtiendo **{f_in.upper()}** ➡️ **{f_out.upper()}**\n\n{barra_progreso(10)}",
            parse_mode="Markdown",
            reply_markup=boton_cancelar(),
        )

        returncode, stderr = ejecutar_conversion_con_progreso(
            chat_id, message_id, input_path, output_path, f_in, f_out
        )

        if stderr == "cancelled" or esta_cancelado(chat_id):
            cancelado = True
            return

        if returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            editar_seguro(
                chat_id,
                message_id,
                f"✅ Conversión completada\n\n{barra_progreso(100)}\n\n📤 Enviando resultado...",
                parse_mode="Markdown",
            )
            with open(output_path, "rb") as f:
                bot.send_document(chat_id, f, visible_file_name=f"{base}.{f_out}")

            try:
                bot.delete_message(chat_id, message_id)
            except Exception:
                pass

            bot.send_message(
                chat_id,
                "✅ Conversión finalizada con éxito.\n\nEnvíame otro archivo cuando quieras.",
                reply_markup=teclado_fijo(),
            )
        else:
            detalle = (stderr or "").strip()
            if len(detalle) > 300:
                detalle = detalle[-300:]
            texto_error = "❌ Error en la conversión. El archivo podría estar corrupto o protegido."
            if detalle:
                texto_error += f"\n\n`{detalle}`"
            editar_seguro(chat_id, message_id, texto_error, parse_mode="Markdown")

    except Exception:
        if not esta_cancelado(chat_id):
            log.exception("Error en el procesamiento chat_id=%s", chat_id)
            editar_seguro(chat_id, message_id, "Hubo un problema técnico al procesar el archivo.")
    finally:
        if cancelado or esta_cancelado(chat_id):
            editar_seguro(
                chat_id,
                message_id,
                "❌ Conversión cancelada.\n\nEnvíame otro archivo cuando quieras.",
            )
        if input_path and os.path.exists(input_path):
            os.remove(input_path)
        if output_path and os.path.exists(output_path):
            os.remove(output_path)
        finalizar_trabajo(chat_id)


def detectar_formato_por_contenido(path):
    try:
        with open(path, "rb") as f:
            cabecera = f.read(8)
        if cabecera.startswith(b"%PDF"):
            return "pdf"
        if cabecera.startswith(b"PK"):
            return "epub"
        if cabecera[:4] == b"BOOK":
            return "mobi"
    except Exception:
        pass
    return None


if __name__ == "__main__":
    log.info("Conversor Calibre operativo PATH_BASE=%s", PATH_BASE)
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception:
        log.exception("Polling detenido")
        raise
