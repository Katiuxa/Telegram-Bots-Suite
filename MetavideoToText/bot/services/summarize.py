import logging
import re

import httpx

from bot.config import GROQ_API_KEY, SUMMARY_INPUT_CHARS, SUMMARY_LLM_CHUNK_CHARS
from bot.services.llm_locale import (
    language_name,
    summary_chunk_system,
    summary_merge_system,
    summary_system,
)
from bot.i18n_progress import prog
from bot.services.transcript_lang import normalize_transcript_lang

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_INPUT_CHARS = SUMMARY_INPUT_CHARS


def _plain(text: str) -> str:
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    return t.strip()


def _strip_summary_header(text: str) -> str:
    t = text.strip()
    for prefix in (
        "📝 *Resumen*",
        "📝 Resumen",
        "📝 *Resumen breve*",
        "Resumen breve",
        "Resumen",
    ):
        if t.startswith(prefix):
            t = t[len(prefix) :].lstrip(":\n* ").strip()
            break
    return t


def _split_plain_chunks(plain: str, chunk_size: int) -> list[str]:
    if len(plain) <= chunk_size:
        return [plain]
    chunks: list[str] = []
    start = 0
    while start < len(plain):
        end = min(start + chunk_size, len(plain))
        if end < len(plain):
            brk = plain.rfind("\n\n", start, end)
            if brk <= start + chunk_size // 3:
                brk = plain.rfind(". ", start, end)
            if brk > start + 400:
                end = brk + 1
        piece = plain[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks


def _fallback_summary(text: str, lang: str | None = None) -> str:
    code = normalize_transcript_lang(lang)
    plain = _plain(text)
    sentences = re.split(r"(?<=[.!?…])\s+", plain)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if not sentences:
        return plain[:1200] if plain else prog("no_text_summarize", code)

    n = len(sentences)
    if n <= 10:
        picked = sentences
    else:
        idx = {0, n // 4, n // 2, (3 * n) // 4, n - 1}
        for i in range(1, n - 1):
            if len(idx) >= 8:
                break
            if i % max(1, n // 8) == 0:
                idx.add(i)
        picked = [sentences[i] for i in sorted(idx)]
        mid = sentences[n // 3 : 2 * n // 3]
        if mid:
            picked.append(" ".join(mid[:2]))
    body = "\n\n".join(f"• {s}" for s in picked[:10])
    return body


def _groq_chat(
    messages: list[dict],
    *,
    max_tokens: int = 1200,
    temperature: float = 0.3,
) -> str | None:
    if not GROQ_API_KEY:
        return None
    payload = {
        "model": "openai/gpt-oss-20b",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    try:
        r = httpx.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=90.0,
        )
        if r.status_code != 200:
            logger.warning("Groq resumen %s: %s", r.status_code, r.text[:200])
            return None
        return (
            r.json().get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except Exception as e:
        logger.warning("Resumen Groq falló: %s", e)
        return None


def _summarize_chunk(
    plain_chunk: str, *, part: int, total: int, lang: str
) -> str:
    ln = language_name(lang)
    intro = (
        f"Fragment {part} of {total} of a long transcript. "
        f"Summarize ONLY this part: key ideas, facts and conclusions. "
        f"Do not invent anything. Write in {ln}."
    )
    content = _groq_chat(
        [
            {"role": "system", "content": summary_chunk_system(lang)},
            {"role": "user", "content": f"{intro}\n\n{plain_chunk}"},
        ],
        max_tokens=900,
    )
    return content or plain_chunk[:2000]


def _summarize_once(plain: str, lang: str) -> str:
    content = _groq_chat(
        [
            {"role": "system", "content": summary_system(lang)},
            {
                "role": "user",
                "content": f"Summarize this full text:\n\n{plain[:MAX_INPUT_CHARS]}",
            },
        ],
        max_tokens=2048,
    )
    if content:
        return _strip_summary_header(content)
    return _fallback_summary(plain, lang)


def _merge_partial_summaries(partials: list[str], lang: str) -> str:
    joined = "\n\n---\n\n".join(partials)
    if len(joined) <= MAX_INPUT_CHARS:
        content = _groq_chat(
            [
                {"role": "system", "content": summary_merge_system(lang)},
                {"role": "user", "content": joined},
            ],
            max_tokens=2048,
        )
        if content:
            return _strip_summary_header(content)
    bullets: list[str] = []
    for p in partials:
        for line in p.splitlines():
            line = line.strip()
            if line and line not in bullets:
                bullets.append(line)
    return "\n".join(bullets[:40])


def summarize_text(text: str, lang: str | None = None) -> str:
    code = normalize_transcript_lang(lang)
    plain = _plain(text)
    if not plain:
        raise ValueError(prog("no_text_summarize", code))
    if len(plain) < 80:
        return (
            f"{plain}\n\n_(El texto es muy corto; aquí va casi íntegro.)_"
        )

    if not GROQ_API_KEY:
        return _fallback_summary(plain, lang)

    chunks = _split_plain_chunks(plain, SUMMARY_LLM_CHUNK_CHARS)
    if len(chunks) == 1:
        return _summarize_once(chunks[0], code)

    partials = [
        _summarize_chunk(c, part=i + 1, total=len(chunks), lang=code)
        for i, c in enumerate(chunks)
    ]
    return _merge_partial_summaries(partials, code)
