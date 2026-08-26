import telebot
from telebot import types
import os
import unicodedata
import re

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
RUTA_BASE = "/media/admin/KINGSTON/Biblioteca Ebooks Espanol"
ARCHIVO_INDICE = os.path.join(RUTA_BASE, "indice.json")

bot = telebot.TeleBot(TOKEN)
user_results = {}

def normalizar(t):
    if not t: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(t).lower()) if unicodedata.category(c) != 'Mn')

@bot.message_handler(commands=['start'])
def welcome(m):
    bot.reply_to(m, "📚 Buscador activado. Escribe autor o titulo:")

@bot.message_handler(func=lambda m: True)
def buscar(m):
    query = normalizar(m.text)
    if not query: return
    
    espera = bot.reply_to(m, "🔍 Buscando...")
    encontrados = []
    
    try:
        # Busqueda por texto plano para evitar errores de JSON/UTF8
        with open(ARCHIVO_INDICE, 'r', encoding='utf-8', errors='ignore') as f:
            contenido = f.read()
            # Buscamos cada objeto del JSON de forma manual con expresiones regulares
            bloques = re.findall(r'\{"t":"[^"]+","a":"[^"]+","p":"[^"]+"\}', contenido)
            
            for b in bloques:
                if query in normalizar(b):
                    # Convertimos el texto del bloque en un diccionario de Python
                    # Usamos una limpieza manual para evitar que json.loads falle
                    t = re.search(r'"t":"([^"]+)"', b).group(1)
                    a = re.search(r'"a":"([^"]+)"', b).group(1)
                    p = re.search(r'"p":"([^"]+)"', b).group(1)
                    encontrados.append({'t': t, 'a': a, 'p': p})
                    
                if len(encontrados) >= 20: break
    except Exception as e:
        bot.edit_message_text(f"⚠️ Error: {e}", m.chat.id, espera.message_id)
        return

    if not encontrados:
        bot.edit_message_text("❌ No se encontro nada. Intenta con una sola palabra.", m.chat.id, espera.message_id)
    else:
        user_results[m.chat.id] = encontrados
        bot.delete_message(m.chat.id, espera.message_id)
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for i, l in enumerate(encontrados):
            markup.add(types.InlineKeyboardButton(f"{l['t'][:40]}", callback_data=f"get_{i}"))
        
        bot.send_message(m.chat.id, f"📖 Resultados para '{m.text}':", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('get_'))
def descargar(c):
    idx = int(c.data.split('_')[1])
    libro = user_results.get(c.message.chat.id, [])[idx]
    # Limpiamos posibles barras invertidas de Windows en la ruta
    ruta_limpia = libro['p'].replace('\\', '/')
    ruta_final = os.path.join(RUTA_BASE, ruta_limpia)
    
    if os.path.exists(ruta_final):
        with open(ruta_final, 'rb') as f:
            bot.send_document(c.message.chat.id, f)
    else:
        bot.answer_callback_query(c.id, f"No encontrado en: {ruta_limpia}")

bot.polling(non_stop=True)