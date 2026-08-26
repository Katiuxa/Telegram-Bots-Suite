# OnlyNoticias

Bot Telegram: pegas una URL de noticia y devuelve el texto (y las fotos del artículo). Corre como `mi_bot.service`.

## Problema y qué se hizo

- **Paywall de verdad:** si el medio no deja el cuerpo en el HTML, no hay artículo. No se rompe el paywall.
- **Muchos sitios sí traen el texto en el origen** (`<p>`, JSON-LD, selectores de dominio). Ahí extrae.
- Al principio solo salían párrafos `<p>`. Se amplió `article_extract.py` para **incluir las fotos** del artículo (`fetch_image_bytes` + envío a Telegram).

National Geographic y otros dominios tienen selectores propios; el resto va por lista universal + trafilatura si está instalada.

## Stack

Python · BeautifulSoup · requests · trafilatura (opcional) · pyTelegramBotAPI

## Ejecución

```bash
cd only-noticias
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
python3 mi_bot.py
```

## Qué demuestra

Distinguir “el HTML ya trae el texto” de “paywall real”, y ampliar el parser (imágenes) sin inventar contenido.
