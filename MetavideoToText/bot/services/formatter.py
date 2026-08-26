"""Reglas de espaciado, título y descripción para documentos exportados."""

from __future__ import annotations

import re

MAX_CHARS_TITLE = 80
MAX_WORDS_DESCRIPTION = 40

_TIMESTAMP_SPLIT = re.compile(r"(?=\[\d{1,2}:\d{2}(?::\d{2})?\])")
_WHITESPACE = re.compile(r"\s+")


def _strip_markdown_light(text: str) -> str:
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    return t.strip()


def plain_for_document(text: str) -> str:
    return _strip_markdown_light(text)


def format_segmented_output(text: str) -> str:
    """Separa bloques cuando el texto ya incluye marcas [HH:MM:SS]."""
    if not text:
        return ""
    plain = _strip_markdown_light(text)
    parts = _TIMESTAMP_SPLIT.split(plain)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) > 1:
        return "\n\n".join(parts)
    return plain


def _truncate_title(title: str, max_chars: int = MAX_CHARS_TITLE) -> str:
    title = (title or "").strip()
    if len(title) <= max_chars:
        return title
    cut = title[: max_chars - 3].rsplit(" ", 1)[0]
    return (cut or title[: max_chars - 3]) + "..."


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def last_sentence_description(text: str, max_words: int = MAX_WORDS_DESCRIPTION) -> str:
    """Última frase del cuerpo como descripción de respaldo (~40 palabras)."""
    clean = _WHITESPACE.sub(" ", _strip_markdown_light(text))
    if not clean:
        return ""
    parts = re.split(r"(?<=[.!?…])\s+", clean)
    parts = [p.strip() for p in parts if p.strip()]
    if not parts:
        words = clean.split()
        if len(words) > max_words:
            return " ".join(words[:max_words]) + "..."
        return clean[:200]
    candidate = parts[-1]
    words = candidate.split()
    if len(words) > max_words:
        return " ".join(words[:max_words]) + "..."
    return candidate


def structure_document(
    text: str,
    title: str,
    description: str | None = None,
) -> tuple[str, str, str]:
    """
    Devuelve (título, descripción, cuerpo) listos para exportar.
    Si no hay descripción, usa la última frase del texto.
    """
    body = format_segmented_output(text).strip()
    title_out = _truncate_title(title) or "Transcripción"
    if description and description.strip():
        desc_out = description.strip()
        words = desc_out.split()
        if len(words) > MAX_WORDS_DESCRIPTION:
            desc_out = " ".join(words[:MAX_WORDS_DESCRIPTION]) + "..."
    else:
        desc_out = last_sentence_description(body)
    return title_out, desc_out, body
