"""Groq Llama — meta descripción breve para documentos."""

from __future__ import annotations

import json
import re

import httpx

from bot.config import GROQ_API_KEY, GROQ_CHAT_URL
from bot.services.formatter import MAX_WORDS_DESCRIPTION, plain_for_document
from bot.services.llm_locale import language_name
from bot.services.transcript_lang import normalize_transcript_lang

_MAX_BODY = 14_000


async def generate_meta_description(
    title: str,
    body: str,
    *,
    lang: str = "es",
) -> str | None:
    """Descripción corta (~40 palabras) a partir del título y la transcripción."""
    if not GROQ_API_KEY:
        return None
    sample = plain_for_document(body)
    if not sample:
        return None
    if len(sample) > _MAX_BODY:
        sample = sample[: int(_MAX_BODY * 0.6)] + "\n\n[…]\n\n" + sample[-4000:]

    code = normalize_transcript_lang(lang)
    ln = language_name(code)
    payload = {
        "model": "openai/gpt-oss-20b",
        "temperature": 0.25,
        "max_tokens": 160,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"Editor en {ln}. Una descripción corta del contenido (máx. "
                    f"{MAX_WORDS_DESCRIPTION} palabras). "
                    'Responde JSON: {{"description":"..."}}. Sin emojis; no inventes hechos.'
                ),
            },
            {
                "role": "user",
                "content": f'Título: "{title}"\n\nTranscripción:\n{sample}',
            },
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                GROQ_CHAT_URL,
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json=payload,
            )
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        content = (
            response.json()
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        data = json.loads(content) if content else {}
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    desc = str(data.get("description") or "").strip()
    if not desc:
        return None
    words = desc.split()
    if len(words) > MAX_WORDS_DESCRIPTION:
        desc = " ".join(words[:MAX_WORDS_DESCRIPTION]) + "..."
    return desc
