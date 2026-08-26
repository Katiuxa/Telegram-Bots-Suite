"""Bot Telegram OnlyNews: extrae texto de artículos de prensa."""
from __future__ import annotations

import io
import logging
import os
import re
import sys
from pathlib import Path

# Usar dependencias del venv local aunque systemd arranque con python3 del sistema
_VENV_SITE = Path(__file__).resolve().parent / ".venv" / "lib"
if _VENV_SITE.is_dir():
    for site in _VENV_SITE.glob("python*/site-packages"):
        site_str = str(site)
        if site_str not in sys.path:
            sys.path.insert(0, site_str)

import telebot
from urllib.parse import urlparse, urlunparse

from article_extract import blocks_to_segments, extract_article_blocks, fetch_image_bytes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("onlynews")

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    raise SystemExit("Falta TELEGRAM_BOT_TOKEN en el entorno.")
TELEGRAM_LIMIT = 4096
CHUNK_SIZE = 4000

bot = telebot.TeleBot(TOKEN)


def _normalize_url(raw: str) -> str:
    url = raw.strip().rstrip(".,;)")
    parsed = urlparse(url)
    if not parsed.scheme:
        url = urlunparse(parsed._replace(scheme="https"))
    return url


def _split_long_paragraph(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    sentences = re.split(r"(?<=[.!?…»\"])\s+(?=[A-ZÁÉÍÓÚÑ«\"(])", text)
    buffer = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{buffer} {sentence}".strip() if buffer else sentence
        if len(candidate) <= limit:
            buffer = candidate
        else:
            if buffer:
                parts.append(buffer)
            buffer = sentence if len(sentence) <= limit else sentence[:limit].rsplit(" ", 1)[0]
    if buffer:
        parts.append(buffer)
    return parts or [text[:limit]]


def _split_message(text: str) -> list[str]:
    """Parte el texto respetando párrafos y frases (nunca a mitad de palabra)."""
    if len(text) <= CHUNK_SIZE:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        extra = len(para) + (2 if current else 0)

        if len(para) > CHUNK_SIZE:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            for piece in _split_long_paragraph(para, CHUNK_SIZE):
                chunks.append(piece)
            continue

        if current and current_len + extra > CHUNK_SIZE:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += extra

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if c]


def _segments_to_messages(segments: list[dict]) -> list[dict]:
    """Agrupa segmentos de texto en mensajes; deja imágenes sueltas."""
    out: list[dict] = []
    text_buf: list[str] = []
    text_len = 0

    def flush_text() -> None:
        nonlocal text_buf, text_len
        if not text_buf:
            return
        joined = "\n\n".join(text_buf)
        for chunk in _split_message(joined):
            out.append({"type": "text", "content": chunk})
        text_buf = []
        text_len = 0

    for seg in segments:
        if seg["type"] == "image":
            flush_text()
            out.append(seg)
            continue
        content = seg.get("content", "").strip()
        if not content:
            continue
        extra = len(content) + (2 if text_buf else 0)
        if text_buf and text_len + extra > CHUNK_SIZE:
            flush_text()
        text_buf.append(content)
        text_len += extra
    flush_text()
    return out


def _send_photo_native(
    chat_id: int,
    url: str,
    caption: str,
    *,
    reply_to: int | None = None,
) -> bool:
    """Envía foto para que se abra en el visor de Telegram (sin navegador)."""
    caption = caption[:1024]

    data = fetch_image_bytes(url)
    if data:
        try:
            bot.send_photo(
                chat_id,
                io.BytesIO(data),
                caption=caption,
                reply_to_message_id=reply_to,
            )
            return True
        except Exception as exc:
            log.warning("send_photo (bytes) falló: %s", exc)

    try:
        bot.send_photo(chat_id, url, caption=caption, reply_to_message_id=reply_to)
        return True
    except Exception as exc:
        log.warning("send_photo (url) falló: %s", exc)

    return False


def _send_segment(chat_id: int, seg: dict, *, reply_to: int | None = None) -> None:
    if seg["type"] == "image":
        url = seg.get("url", "")
        caption = seg.get("caption") or "Imagen del artículo"
        if url and _send_photo_native(chat_id, url, caption, reply_to=reply_to):
            return
        bot.send_message(
            chat_id,
            f"🖼 {caption}",
            reply_to_message_id=reply_to,
            disable_web_page_preview=True,
        )
        return
    content = seg.get("content", "")
    if content:
        bot.send_message(
            chat_id,
            content,
            reply_to_message_id=reply_to,
            disable_web_page_preview=True,
        )


def obtener_articulo_segmentos(url: str) -> list[dict] | None:
    try:
        result = extract_article_blocks(url)
        if not result:
            return None
        blocks, headline = result
        segments = blocks_to_segments(blocks, headline=headline)
        if not segments:
            return None
        return _segments_to_messages(segments)
    except Exception as exc:
        log.exception("Error extrayendo %s: %s", url, exc)
    return None


@bot.message_handler(commands=["start", "help"])
def start(message):
    bot.reply_to(
        message,
        "Envíame el enlace de una noticia y te devuelvo el texto del artículo.\n"
        "Intento extraer el contenido de cualquier web de noticias o artículos.",
    )


@bot.message_handler(func=lambda message: True)
def obtener_articulo(message):
    if not message.text:
        bot.reply_to(message, "Envía un enlace de noticia.")
        return

    url_match = re.search(r"(https?://\S+)", message.text)
    if not url_match:
        bot.reply_to(message, "No encuentro un enlace válido.")
        return

    url_articulo = _normalize_url(url_match.group(1))
    bot.send_chat_action(message.chat.id, "typing")

    segmentos = obtener_articulo_segmentos(url_articulo)
    if not segmentos:
        bot.reply_to(
            message,
            "No pude obtener el texto. Puede ser paywall real, enlace roto o web no soportada.",
        )
        return

    for i, seg in enumerate(segmentos):
        reply_to = message.message_id if i == 0 else None
        _send_segment(message.chat.id, seg, reply_to=reply_to)


if __name__ == "__main__":
    log.info("Bot OnlyNews en línea")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
