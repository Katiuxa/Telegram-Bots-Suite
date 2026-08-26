import telebot
from telebot import types
import sqlite3
import os
import unicodedata
import math
import requests
import re
import time

# --- CONFIGURACIÓN ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
USB_PATH = "/media/admin/KINGSTON"
# Ruta a la base de datos
DB_PATH = os.path.join(USB_PATH, "biblioteca.db")
# Ruta real donde están las carpetas con los epubs
RUTA_LIBROS = os.path.join(USB_PATH, "Biblioteca Ebooks Espanol")

LIBROS_POR_PAGINA = 10

bot = telebot.TeleBot(TOKEN)
user_results = {}
user_page = {}

def normalizar_busqueda(texto):
    if not texto: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', texto.lower().strip()) if unicodedata.category(c) != 'Mn')

def obtener_sinopsis(titulo, autor):
    t_api = "".join(c for c in unicodedata.normalize('NFD', titulo) if unicodedata.category(c) != 'Mn').replace('ñ', 'n')
    a_api = "".join(c for c in unicodedata.normalize('NFD', autor) if unicodedata.category(c) != 'Mn').replace('ñ', 'n')
    sinopsis = "No se ha encontrado un resumen para esta obra en las bases de datos externas."
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{t_api}+inauthor:{a_api}&langRestrict=es&maxResults=1"
        r = requests.get(url, timeout=5).json()
        if "items" in r:
            v = r["items"][0]["volumeInfo"]
            desc = v.get("description", "")
            if desc:
                limpio = re.sub(r'<.*?>', '', desc).strip()
                sinopsis = limpio[:1500] + "..." if len(limpio) > 1500 else limpio
    except:
        pass
    return sinopsis

# --- FUNCIONES DE BASE DE DATOS ---
def buscar_en_db(query_text):
    palabras = normalizar_busqueda(query_text).split()
    if not palabras: return []
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    sql = "SELECT titulo, autor, ruta FROM libros WHERE "
    condiciones = []
    params = []
    for p in palabras:
        condiciones.append("(titulo LIKE ? OR autor LIKE ?)")
        params.extend([f"%{p}%", f"%{p}%"])
    
    sql += " AND ".join(condiciones)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [{"t": r["titulo"], "a": r["autor"], "p": r["ruta"]} for r in rows]

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    mensaje_inicio = (
        "Este catálogo contiene una instantánea de la Biblioteca Secreta a día "
        "31 de Agosto de 2024. Contiene un total de 126.533 libros.\n\n"
        "📚 **Escribe el título o autor para buscar en la biblioteca.**"
    )
    bot.send_message(message.chat.id, mensaje_inicio, parse_mode="Markdown")

@bot.message_handler(func=lambda m: not m.text.startswith('/'))
def manejar_busqueda(message):
    encontrados = buscar_en_db(message.text)
    
    if not encontrados:
        bot.send_message(message.chat.id, "❌ No se encontró nada con ese nombre.")
    else:
        user_results[message.chat.id] = encontrados
        user_page[message.chat.id] = 0
        bot.send_message(message.chat.id, f"🔍 Resultados ({len(encontrados)}):", 
                         reply_markup=generar_markup_paginado(message.chat.id, 0))

def generar_markup_paginado(chat_id, pagina):
    encontrados = user_results.get(chat_id, [])
    total_paginas = math.ceil(len(encontrados) / LIBROS_POR_PAGINA)
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    inicio = pagina * LIBROS_POR_PAGINA
    for i, libro in enumerate(encontrados[inicio:inicio + LIBROS_POR_PAGINA]):
        idx = inicio + i
        markup.add(types.InlineKeyboardButton(text=f"📖 {libro['t'][:25]} | {libro['a'][:15]}", callback_data=f"pre_{idx}"))
    
    nav = []
    if pagina > 0: nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"pag_{pagina-1}"))
    nav.append(types.InlineKeyboardButton(f"📄 {pagina+1}/{total_paginas}", callback_data="ignore"))
    if pagina < total_paginas - 1: nav.append(types.InlineKeyboardButton("➡️", callback_data=f"pag_{pagina+1}"))
    markup.row(*nav)
    
    markup.add(types.InlineKeyboardButton("🔍 Realizar otra búsqueda", callback_data="nueva_busqueda"))
    return markup

@bot.callback_query_handler(func=lambda c: c.data.startswith('pag_'))
def callback_paginar(call):
    p = int(call.data.split('_')[1])
    user_page[call.message.chat.id] = p
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, 
                                  reply_markup=generar_markup_paginado(call.message.chat.id, p))

@bot.callback_query_handler(func=lambda c: c.data.startswith('pre_'))
def callback_detalles(call):
    idx = int(call.data.split('_')[1])
    libro = user_results[call.message.chat.id][idx]
    
    texto = (
        f"📘 *TÍTULO:* {libro['t']}\n\n"
        f"👤 *AUTOR:* {libro['a']}\n\n"
        f"📂 *FORMATO:* EPUB"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📖 Intentar obtener resumen", callback_data=f"sinop_{idx}"))
    markup.add(types.InlineKeyboardButton("📥 Descargar", callback_data=f"get_{idx}"))
    markup.add(types.InlineKeyboardButton("🔙 Volver", callback_data="volver"))
    
    bot.edit_message_text(texto, call.message.chat.id, call.message.message_id, 
                          parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('sinop_'))
def callback_sinopsis(call):
    idx = int(call.data.split('_')[1])
    libro = user_results[call.message.chat.id][idx]
    
    bot.answer_callback_query(call.id, "Buscando información...")
    resumen = obtener_sinopsis(libro['t'], libro['a'])
    
    texto = (
        f"📖 *{libro['t']}*\n\n"
        f"📝 *RESUMEN:*\n_{resumen}_\n\n"
        f"📂 *FORMATO:* EPUB"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📥 Confirmar Descarga", callback_data=f"get_{idx}"))
    markup.add(types.InlineKeyboardButton("🔙 Volver a detalles", callback_data=f"pre_{idx}"))
    
    bot.edit_message_text(texto, call.message.chat.id, call.message.message_id, 
                          parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "volver")
def callback_volver(call):
    p = user_page.get(call.message.chat.id, 0)
    bot.edit_message_text("🔍 Resultados:", call.message.chat.id, call.message.message_id, 
                          reply_markup=generar_markup_paginado(call.message.chat.id, p))

@bot.callback_query_handler(func=lambda c: c.data.startswith('get_'))
def callback_descargar(call):
    idx = int(call.data.split('_')[1])
    libro = user_results[call.message.chat.id][idx]
    
    # IMPORTANTE: Corregimos la ruta. 
    # Quitamos 'biblioteca/' (que está en la DB) para que coincida con tu carpeta real
    ruta_relativa = libro['p'].replace('biblioteca/', '', 1)
    ruta_completa = os.path.join(RUTA_LIBROS, ruta_relativa)
    nombre_archivo = os.path.basename(ruta_completa)

    if os.path.exists(ruta_completa):
        bot.send_message(call.message.chat.id, f"🚀 Enviando: *{libro['t']}*...")
        try:
            with open(ruta_completa, 'rb') as f:
                bot.send_document(call.message.chat.id, f, visible_file_name=nombre_archivo)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error al leer el archivo: {e}")
    else:
        # Si no lo encuentra, te muestra la ruta que ha intentado usar para depurar
        bot.send_message(call.message.chat.id, f"⚠️ Archivo no encontrado.\nIntenté leer:\n`{ruta_completa}`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == "nueva_busqueda")
def callback_nueva(call):
    bot.send_message(call.message.chat.id, "📚 Busca por título del libro y/o autor:")
    bot.answer_callback_query(call.id)

# --- BUCLE DE EJECUCIÓN ROBUSTO ---
print("Bot con SQLite funcionando en Raspberry Pi...")
while True:
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        print(f"Error de conexión, reintentando en 5 segundos... ({e})")
        time.sleep(5)