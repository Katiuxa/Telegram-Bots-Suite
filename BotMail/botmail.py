import logging
import os
import random
import re
import sqlite3
import string
from datetime import datetime, timedelta

import requests
import telebot
from telebot import types

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("meta-mailbox")

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno.")
bot = telebot.TeleBot(TOKEN)
API_URL = "https://api.mail.tm"
DB_PATH = os.environ.get("DB_PATH", "correos_bot.db")

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cuentas (
            user_id INTEGER,
            email TEXT,
            password TEXT,
            token TEXT,
            mote TEXT
        )
    ''')
    conn.commit()
    conn.close()

def guardar_cuenta(user_id, email, password, token, mote):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO cuentas VALUES (?, ?, ?, ?, ?)", (user_id, email, password, token, mote))
    conn.commit()
    conn.close()

def actualizar_mote(user_id, email, nuevo_mote):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE cuentas SET mote = ? WHERE user_id = ? AND email = ?", (nuevo_mote, user_id, email))
    conn.commit()
    conn.close()

def actualizar_token(user_id, email, nuevo_token):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE cuentas SET token = ? WHERE user_id = ? AND email = ?", (nuevo_token, user_id, email))
    conn.commit()
    conn.close()

def obtener_cuentas(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT email, password, token, mote FROM cuentas WHERE user_id = ?", (user_id,))
    filas = cursor.fetchall()
    conn.close()
    return [{"email": f[0], "password": f[1], "token": f[2], "mote": f[3]} for f in filas]

def borrar_cuenta_especifica(user_id, email):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cuentas WHERE user_id = ? AND email = ?", (user_id, email))
    conn.commit()
    conn.close()

# --- UTILIDADES ---
def generar_string(n):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def formatear_fecha_local(fecha_iso):
    try:
        dt_utc = datetime.fromisoformat(fecha_iso.replace('Z', '+00:00'))
        dt_espana = dt_utc + timedelta(hours=2)
        return dt_espana
    except Exception:
        return datetime.now()

def extraer_enlaces_html(html_content):
    """Extrae enlaces únicos y limpios de etiquetas HTML."""
    if not html_content:
        return []
    enlaces_raw = re.findall(r'href=["\'](https?://[^"\'>\s]+)["\']', html_content)
    vistos = set()
    enlaces_limpios = []
    for url in enlaces_raw:
        url = url.strip()
        if url not in vistos:
            vistos.add(url)
            enlaces_limpios.append(url)
    return enlaces_limpios

def renovar_token(cuenta):
    """Intenta renovar el token de autenticación de una cuenta."""
    try:
        login_res = requests.post(
            f"{API_URL}/token",
            json={"address": cuenta['email'], "password": cuenta['password']},
            timeout=10
        ).json()
        return login_res.get('token')
    except Exception:
        return None

def obtener_headers_validos(user_id, cuenta):
    """Devuelve headers con token válido, renovándolo si es necesario."""
    headers = {"Authorization": f"Bearer {cuenta['token']}"}
    # Prueba rápida de validez
    test = requests.get(f"{API_URL}/me", headers=headers, timeout=10)
    if test.status_code == 401:
        nuevo_token = renovar_token(cuenta)
        if nuevo_token:
            actualizar_token(user_id, cuenta['email'], nuevo_token)
            headers = {"Authorization": f"Bearer {nuevo_token}"}
        else:
            return None
    return headers

def escapar_markdown(texto):
    """Escapa caracteres especiales de Markdown para evitar errores de parse."""
    caracteres = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for c in caracteres:
        texto = texto.replace(c, f'\\{c}')
    return texto

def nombre_mostrado(mote):
    """Si el mote está vacío o es 'Sin nombre', devuelve cadena vacía."""
    if not mote or mote.strip() in ("Sin nombre", ""):
        return ""
    return mote.strip()

def etiqueta_bandeja(cuenta):
    """Construye la etiqueta del botón de bandeja."""
    nombre = nombre_mostrado(cuenta['mote'])
    if nombre:
        return f"📬 {nombre}  ·  {cuenta['email']}"
    return f"📬 {cuenta['email']}"

def enviar_menu_principal(chat_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("✉️ Crear Correo"),
        types.KeyboardButton("📂 Ver Bandejas"),
        types.KeyboardButton("🏠 Inicio")
    )
    texto = (
        "📮 *Meta Mail Bot*\n\n"
        "Gestiona correos temporales y desechables directamente desde Telegram\\.\n\n"
        "⚠️ _No uses estas cuentas para servicios críticos\\. Los dominios pueden cambiar sin aviso\\._"
    )
    bot.send_message(chat_id, texto, reply_markup=markup, parse_mode="MarkdownV2")

# --- MANEJADORES PRINCIPALES ---
@bot.message_handler(commands=['start'])
def bienvenida(message):
    enviar_menu_principal(message.chat.id)

@bot.message_handler(func=lambda m: m.text in ("🏠 Inicio", "Reiniciar", "✏️ Redactar Correo"))
def boton_reiniciar_texto(message):
    enviar_menu_principal(message.chat.id)

# --- CREAR CORREO ---
@bot.message_handler(func=lambda m: m.text == "✉️ Crear Correo")
def crear_directo(message):
    user_id = message.from_user.id
    cuentas = obtener_cuentas(user_id)
    if len(cuentas) >= 8:
        bot.reply_to(message, "⚠️ Límite de 8 cuentas alcanzado. Elimina alguna antes de crear otra.")
        return

    msg_espera = bot.send_message(message.chat.id, "⏳ Creando cuenta...")
    try:
        res_dominios = requests.get(f"{API_URL}/domains", timeout=10).json()
        dominio = res_dominios['hydra:member'][0]['domain']
        email = f"{generar_string(10)}@{dominio}"
        password = generar_string(14)
        payload = {"address": email, "password": password}

        reg_res = requests.post(f"{API_URL}/accounts", json=payload, timeout=10)
        if reg_res.status_code not in [200, 201]:
            bot.edit_message_text("❌ Error al registrar la cuenta. Inténtalo de nuevo.", message.chat.id, msg_espera.message_id)
            return

        login_res = requests.post(f"{API_URL}/token", json=payload, timeout=10).json()
        token = login_res.get('token')
        if not token:
            bot.edit_message_text("❌ Error al obtener token de acceso.", message.chat.id, msg_espera.message_id)
            return

        guardar_cuenta(user_id, email, password, token, "")

        # Mostramos el email como código para que sea fácil de copiar
        texto = (
            f"✅ *Cuenta creada correctamente*\n\n"
            f"📧 Dirección:\n`{email}`\n\n"
            f"_Toca el correo para copiarlo al portapapeles_"
        )
        bot.edit_message_text(texto, message.chat.id, msg_espera.message_id, parse_mode="Markdown")

    except requests.exceptions.Timeout:
        bot.edit_message_text("❌ La API tardó demasiado en responder. Inténtalo de nuevo.", message.chat.id, msg_espera.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Error inesperado: {str(e)[:100]}", message.chat.id, msg_espera.message_id)

# --- VER BANDEJAS ---
@bot.message_handler(func=lambda m: m.text == "📂 Ver Bandejas")
def listar(message):
    cuentas = obtener_cuentas(message.from_user.id)
    if not cuentas:
        bot.reply_to(message, "📭 No tienes cuentas activas. Crea una primero con ✉️ Crear Correo.")
        return

    markup = types.InlineKeyboardMarkup()
    for c in cuentas:
        markup.add(types.InlineKeyboardButton(etiqueta_bandeja(c), callback_data=f"ver_{c['email']}"))
    markup.add(types.InlineKeyboardButton("🏠 Inicio", callback_data="reset_start"))

    bot.send_message(message.chat.id, "📂 *Tus bandejas de entrada:*", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "reset_start")
def callback_reinicio(call):
    bot.answer_callback_query(call.id)
    enviar_menu_principal(call.message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "volver_lista")
def volver(call):
    bot.answer_callback_query(call.id)
    cuentas = obtener_cuentas(call.from_user.id)
    if not cuentas:
        bot.edit_message_text("📭 No tienes cuentas activas.", call.message.chat.id, call.message.message_id)
        return
    markup = types.InlineKeyboardMarkup()
    for c in cuentas:
        markup.add(types.InlineKeyboardButton(etiqueta_bandeja(c), callback_data=f"ver_{c['email']}"))
    markup.add(types.InlineKeyboardButton("🏠 Inicio", callback_data="reset_start"))
    try:
        bot.edit_message_text("📂 *Tus bandejas de entrada:*", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    except Exception:
        pass

# --- VER BANDEJA INDIVIDUAL ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('ver_'))
def ver_bandeja(call):
    bot.answer_callback_query(call.id, "🔄 Cargando bandeja...")
    email = call.data[4:]  # evitamos split('_') que rompe emails con guiones
    user_id = call.from_user.id
    cuentas = obtener_cuentas(user_id)
    cuenta = next((c for c in cuentas if c['email'] == email), None)

    if not cuenta:
        bot.answer_callback_query(call.id, "❌ Cuenta no encontrada.")
        return

    try:
        headers = obtener_headers_validos(user_id, cuenta)
        if not headers:
            bot.edit_message_text(
                "❌ No se pudo autenticar con esta cuenta. El token ha expirado y no se pudo renovar.",
                call.message.chat.id, call.message.message_id
            )
            return

        res = requests.get(f"{API_URL}/messages", headers=headers, timeout=10).json()
        mensajes = res.get('hydra:member', [])
        markup = types.InlineKeyboardMarkup()

        nombre = nombre_mostrado(cuenta['mote'])
        cabecera_nombre = f"*{nombre}*\n" if nombre else ""
        cabecera_email = f"`{email}`"

        if not mensajes:
            texto = f"📭 Bandeja vacía\n\n{cabecera_nombre}{cabecera_email}"
        else:
            texto = f"📬 *Mensajes recibidos*\n\n{cabecera_nombre}{cabecera_email}"
            for m in mensajes:
                dt_local = formatear_fecha_local(m['createdAt'])
                hora = dt_local.strftime("%d/%m %H:%M")
                remitente = m['from']['address'].split('@')[0]
                asunto = m.get('subject') or "(Sin asunto)"
                texto_boton = f"[{hora}] {remitente}: {asunto}"
                if len(texto_boton) > 56:
                    texto_boton = texto_boton[:53] + "…"
                # Usamos separador | en callback para evitar conflictos con _ del email
                markup.add(types.InlineKeyboardButton(
                    f"📩 {texto_boton}",
                    callback_data=f"msg|{email}|{m['id']}"
                ))

        markup.add(types.InlineKeyboardButton("🔄 Actualizar", callback_data=f"ver_{email}"))
        markup.add(types.InlineKeyboardButton("✏️ Poner nombre", callback_data=f"setmote|{email}"))
        markup.add(types.InlineKeyboardButton("🗑️ Eliminar cuenta", callback_data=f"del|{email}"))
        markup.add(types.InlineKeyboardButton("◀️ Volver", callback_data="volver_lista"))
        markup.add(types.InlineKeyboardButton("🏠 Inicio", callback_data="reset_start"))

        try:
            bot.edit_message_text(
                texto, call.message.chat.id, call.message.message_id,
                reply_markup=markup, parse_mode="Markdown"
            )
        except Exception:
            pass

    except requests.exceptions.Timeout:
        try:
            bot.edit_message_text(
                "⏱️ La API tardó demasiado. Pulsa 🔄 Actualizar para reintentar.",
                call.message.chat.id, call.message.message_id
            )
        except Exception:
            pass
    except Exception as e:
        try:
            bot.edit_message_text(
                f"❌ Error al cargar la bandeja: {str(e)[:120]}",
                call.message.chat.id, call.message.message_id
            )
        except Exception:
            pass

# --- PONER NOMBRE (MOTE) ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('setmote|'))
def solicitar_nuevo_mote(call):
    bot.answer_callback_query(call.id)
    email = call.data.split('|')[1]
    msg = bot.send_message(
        call.message.chat.id,
        f"✏️ Escribe el nombre que quieres darle a esta bandeja:\n\n`{email}`",
        parse_mode="Markdown"
    )
    bot.register_next_step_handler(msg, procesar_mote, email)

def procesar_mote(message, email):
    nuevo_mote = message.text.strip()
    actualizar_mote(message.from_user.id, email, nuevo_mote)
    bot.send_message(message.chat.id, f"✅ Nombre actualizado a: *{nuevo_mote}*", parse_mode="Markdown")
    # Reenviamos la vista de bandejas
    cuentas = obtener_cuentas(message.from_user.id)
    markup = types.InlineKeyboardMarkup()
    for c in cuentas:
        markup.add(types.InlineKeyboardButton(etiqueta_bandeja(c), callback_data=f"ver_{c['email']}"))
    markup.add(types.InlineKeyboardButton("🏠 Inicio", callback_data="reset_start"))
    bot.send_message(message.chat.id, "📂 *Tus bandejas:*", reply_markup=markup, parse_mode="Markdown")

# --- ELIMINAR CUENTA ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('del|'))
def eliminar_una(call):
    email = call.data.split('|')[1]
    borrar_cuenta_especifica(call.from_user.id, email)
    bot.answer_callback_query(call.id, "🗑️ Cuenta eliminada.")
    volver(call)

# --- LEER MENSAJE ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('msg|'))
def leer_mensaje(call):
    bot.answer_callback_query(call.id, "📨 Cargando mensaje...")
    partes = call.data.split('|')
    if len(partes) < 3:
        bot.answer_callback_query(call.id, "❌ Datos inválidos.")
        return

    email = partes[1]
    msg_id = partes[2]
    user_id = call.from_user.id
    cuentas = obtener_cuentas(user_id)
    cuenta = next((c for c in cuentas if c['email'] == email), None)

    if not cuenta:
        bot.answer_callback_query(call.id, "❌ Cuenta no encontrada.")
        return

    try:
        headers = obtener_headers_validos(user_id, cuenta)
        if not headers:
            bot.edit_message_text(
                "❌ No se pudo autenticar. Token expirado y no renovable.",
                call.message.chat.id, call.message.message_id
            )
            return

        res = requests.get(f"{API_URL}/messages/{msg_id}", headers=headers, timeout=10)
        if res.status_code == 404:
            bot.edit_message_text(
                "❌ Mensaje no encontrado. Puede que haya sido eliminado.",
                call.message.chat.id, call.message.message_id
            )
            return
        if res.status_code != 200:
            bot.edit_message_text(
                f"❌ Error al cargar el mensaje (HTTP {res.status_code}).",
                call.message.chat.id, call.message.message_id
            )
            return

        m = res.json()
        dt_local = formatear_fecha_local(m['createdAt'])
        f_bonita = dt_local.strftime("%d/%m/%Y %H:%M")

        remitente = m['from']['address']
        asunto = m.get('subject') or "(Sin asunto)"
        cuerpo = m.get('text') or ""

        # Construimos el texto con formato limpio
        texto = (
            f"📨 *Nuevo mensaje*\n\n"
            f"👤 *De:* `{remitente}`\n"
            f"📋 *Asunto:* {asunto}\n"
            f"🕐 *Fecha:* {f_bonita}\n"
            f"{'─' * 30}\n\n"
            f"{cuerpo}"
        )

        # Extraemos enlaces del HTML si los hay
        html_content = m.get('html', '')
        if isinstance(html_content, list):
            html_content = ' '.join(html_content)
        enlaces = extraer_enlaces_html(html_content)

        if enlaces:
            texto += f"\n\n{'─' * 30}\n🔗 *Enlaces detectados:*\n"
            for idx, url in enumerate(enlaces[:10], start=1):
                texto += f"\n{idx}\\. [Enlace {idx}]({url})"

        # Limitamos a 4000 chars para no superar el límite de Telegram
        if len(texto) > 4000:
            texto = texto[:3950] + "\n\n_\\[Mensaje recortado por longitud\\]_"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 Actualizar bandeja", callback_data=f"ver_{email}"))
        markup.add(types.InlineKeyboardButton("◀️ Volver a bandeja", callback_data=f"ver_{email}"))
        markup.add(types.InlineKeyboardButton("🏠 Inicio", callback_data="reset_start"))

        try:
            bot.edit_message_text(
                texto, call.message.chat.id, call.message.message_id,
                reply_markup=markup, parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception:
            # Si Markdown falla (caracteres raros), enviamos sin parse
            texto_plano = (
                f"📨 Nuevo mensaje\n\n"
                f"👤 De: {remitente}\n"
                f"📋 Asunto: {asunto}\n"
                f"🕐 Fecha: {f_bonita}\n"
                f"{'─' * 30}\n\n"
                f"{cuerpo[:3500]}"
            )
            bot.edit_message_text(
                texto_plano, call.message.chat.id, call.message.message_id,
                reply_markup=markup, disable_web_page_preview=True
            )

    except requests.exceptions.Timeout:
        try:
            bot.edit_message_text(
                "⏱️ Tiempo de espera agotado al cargar el mensaje. Inténtalo de nuevo.",
                call.message.chat.id, call.message.message_id
            )
        except Exception:
            pass
    except Exception as e:
        try:
            bot.edit_message_text(
                f"❌ Error al cargar el mensaje: {str(e)[:120]}",
                call.message.chat.id, call.message.message_id
            )
        except Exception:
            pass

# --- ARRANQUE ---
if __name__ == "__main__":
    init_db()
    log.info("Meta Mail arrancado. DB=%s", DB_PATH)
    try:
        bot.infinity_polling(timeout=20, long_polling_timeout=20)
    except Exception:
        log.exception("Polling detenido")
        raise
