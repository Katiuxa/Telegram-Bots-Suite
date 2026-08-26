import logging
import math
import os
import re
import sqlite3
import time
import unicodedata

import requests
import telebot
from telebot import types

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("meta-biblioteca")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
USB_PATH = os.environ.get("USB_PATH", "/media/admin/KINGSTON")
DB_PATH = os.environ.get("DB_PATH", os.path.join(USB_PATH, "biblioteca.db"))
RUTA_LIBROS = os.environ.get(
    "RUTA_LIBROS",
    os.path.join(USB_PATH, "Biblioteca Ebooks Espanol", "biblioteca"),
)

if not TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno.")

bot = telebot.TeleBot(TOKEN)
user_results = {}
user_page = {}
LIBROS_POR_PAGINA = 10

def normalizar(t):
    if not t: return ""
    t = str(t).lower()
    t = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn')
    return t.replace('ñ', 'n').strip()

def obtener_sinopsis(titulo, autor):
    t_api = normalizar(titulo)
    a_api = normalizar(autor)
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=intitle:{t_api}+inauthor:{a_api}&langRestrict=es&maxResults=1"
        r = requests.get(url, timeout=5).json()
        if "items" in r:
            desc = r["items"][0]["volumeInfo"].get("description", "")
            if desc:
                limpio = re.sub(r'<.*?>', '', desc).strip()
                return limpio[:1000] + "..." if len(limpio) > 1000 else limpio
        return "No hay resumen disponible para esta obra en Google Books."
    except requests.RequestException as exc:
        log.warning("Google Books no disponible: %s", exc)
        return "No hay resumen disponible para esta obra en Google Books."
    except Exception:
        log.exception("Fallo inesperado al pedir sinopsis")
        return "No hay resumen disponible para esta obra en Google Books."

def buscar_en_db(query_text):
    query_norm = normalizar(query_text)
    palabras = query_norm.split()
    if not palabras:
        return []
    if not os.path.isfile(DB_PATH):
        log.error("SQLite no encontrado: %s (¿USB montado?)", DB_PATH)
        return []

    sql = "SELECT titulo, autor, ruta FROM libros WHERE "
    condiciones = []
    params = []
    for pal in palabras:
        condiciones.append("(titulo LIKE ? OR autor LIKE ?)")
        params.extend([f"%{pal}%", f"%{pal}%"])
    sql += " AND ".join(condiciones) + " LIMIT 300"

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        log.exception("Error SQLite al buscar %r", query_text)
        return []
    
    # Refinado con Python para precision total con tildes
    encontrados = []
    for r in rows:
        texto_comparar = normalizar(f"{r['titulo']} {r['autor']}")
        if all(p in texto_comparar for p in palabras):
            encontrados.append({"t": r["titulo"], "a": r["autor"], "p": r["ruta"]})
            
    return encontrados[:100]

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def welcome(m):
    texto = (
        "📚 **Buscador de Biblioteca**\n\n"
        "Catálogo SQLite de epubs en un USB montado en la Raspberry Pi. "
        "Escribe un **título** o un **autor** para buscar:"
    )
    bot.reply_to(m, texto, parse_mode="Markdown")

@bot.message_handler(func=lambda m: not m.text.startswith('/'))
def manejar_busqueda(m):
    encontrados = buscar_en_db(m.text)
    if not encontrados:
        bot.send_message(m.chat.id, "❌ No se encontró nada. Prueba con otras palabras.")
    else:
        user_results[m.chat.id] = encontrados
        user_page[m.chat.id] = 0
        bot.send_message(m.chat.id, f"📖 Resultados para '{m.text}':", 
                         reply_markup=generar_markup(m.chat.id, 0))

def generar_markup(chat_id, pagina):
    encontrados = user_results.get(chat_id, [])
    total = math.ceil(len(encontrados) / LIBROS_POR_PAGINA)
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # 1. Añadir los botones de los libros
    inicio = pagina * LIBROS_POR_PAGINA
    for i, l in enumerate(encontrados[inicio:inicio + LIBROS_POR_PAGINA]):
        idx = inicio + i
        markup.add(types.InlineKeyboardButton(f"{l['t'][:25]} | {l['a'][:15]}", callback_data=f"pre_{idx}"))
    
    # 2. Añadir la fila de navegación (flechas)
    nav = []
    if pagina > 0: 
        nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"pag_{pagina-1}"))
    nav.append(types.InlineKeyboardButton(f"{pagina+1}/{total}", callback_data="none"))
    if pagina < total - 1: 
        nav.append(types.InlineKeyboardButton("➡️", callback_data=f"pag_{pagina+1}"))
    markup.row(*nav)

    # 3. EL NUEVO BOTÓN: Justo debajo de las flechas
    markup.add(types.InlineKeyboardButton("🔍 Seguir buscando Autor o Libro", callback_data="nueva_busqueda"))
    
    return markup

@bot.callback_query_handler(func=lambda c: c.data.startswith('pag_'))
def callback_paginar(c):
    p = int(c.data.split('_')[1])
    user_page[c.message.chat.id] = p
    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=generar_markup(c.message.chat.id, p))

@bot.callback_query_handler(func=lambda c: c.data.startswith('pre_'))
def callback_antesala(c):
    idx = int(c.data.split('_')[1])
    l = user_results[c.message.chat.id][idx]
    texto = (
        f"📘 **TÍTULO:**\n{l['t']}\n\n"
        f"👤 **AUTOR:**\n{l['a']}\n\n"
        f"📂 **FORMATO:** EPUB"
    )
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📥 Descargar EPUB", callback_data=f"get_{idx}"),
        types.InlineKeyboardButton("📖 Buscar sinopsis", callback_data=f"sinop_{idx}"),
        types.InlineKeyboardButton("🔍 Seguir buscando", callback_data="nueva_busqueda"),
        types.InlineKeyboardButton("🔙 Volver al listado", callback_data="volver")
    )
    bot.edit_message_text(texto, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('sinop_'))
def callback_resumen(c):
    idx = int(c.data.split('_')[1])
    l = user_results[c.message.chat.id][idx]
    bot.answer_callback_query(c.id, "Buscando resumen...")
    resumen = obtener_sinopsis(l['t'], l['a'])
    
    texto = f"📘 **{l['t']}**\n\n📝 **Resumen:**\n_{resumen}_"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📥 Descargar EPUB", callback_data=f"get_{idx}"),
        types.InlineKeyboardButton("🔍 Seguir buscando", callback_data="nueva_busqueda"),
        types.InlineKeyboardButton("🔙 Volver", callback_data=f"pre_{idx}")
    )
    bot.edit_message_text(texto, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "nueva_busqueda")
def nueva_busqueda(c):
    bot.edit_message_text("🔍 Escribe el titulo o autor que quieres buscar ahora:", c.message.chat.id, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "volver")
def volver(c):
    p = user_page.get(c.message.chat.id, 0)
    bot.edit_message_text("🔍 Resultados:", c.message.chat.id, c.message.message_id, reply_markup=generar_markup(c.message.chat.id, p))

@bot.callback_query_handler(func=lambda c: c.data.startswith('get_'))
def descargar(c):
    idx = int(c.data.split('_')[1])
    l = user_results[c.message.chat.id][idx]
    ruta_relativa = l['p'].replace('biblioteca/', '', 1).replace('\\', '/')
    ruta_final = os.path.join(RUTA_LIBROS, ruta_relativa)

    if os.path.exists(ruta_final):
        bot.answer_callback_query(c.id, "🚀 Enviando...")
        with open(ruta_final, 'rb') as f:
            bot.send_document(c.message.chat.id, f, caption=f"📚 {l['t']} - {l['a']}")
        # Sugerencia tras descarga exitosa
        bot.send_message(c.message.chat.id, "✅ Descarga completada. ¿Buscas algo mas?", 
                         reply_markup=types.InlineKeyboardMarkup().add(
                             types.InlineKeyboardButton("🔍 Nueva busqueda", callback_data="nueva_busqueda")
                         ))
    else:
        bot.answer_callback_query(c.id, "❌ Error fisico en USB", show_alert=True)

if __name__ == "__main__":
    if not os.path.isdir(USB_PATH):
        log.error("USB no montado en %s", USB_PATH)
    log.info("Arranque. DB=%s USB=%s", DB_PATH, USB_PATH)
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception:
            log.exception("Polling caído; reintento en 5s")
            time.sleep(5)