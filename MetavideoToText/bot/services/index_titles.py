"""Títulos editoriales para el índice (tema breve, nunca frases literales del audio)."""

from __future__ import annotations

import logging
import re
from collections import Counter

import httpx

from bot.config import (
    GROQ_API_KEY,
    INDEX_LLM_MODEL,
    INDEX_TITLE_EXCERPT_CHARS,
    INDEX_TITLE_WORDS_MAX,
    INDEX_TITLES_BATCH_SIZE,
)
from bot.services.format_timestamps import MomentBlock, format_timestamp
from bot.services.llm_locale import index_batch_system, index_single_system
from bot.services.summarize import GROQ_CHAT_URL
from bot.services.text_polish import polish_fragment, split_sentences
from bot.services.transcript_lang import normalize_transcript_lang

logger = logging.getLogger(__name__)

_STOP = frozenset(
    "de la el en y a que los las del un una por con para es al lo como su sus "
    "este esta esto pero más muy bien también cuando hay ser fue son era o sea "
    "entonces bueno vale pues eh em".split()
)

_TITLE_LINE = re.compile(r"^\s*(\d+)[.)]\s*(.+?)\s*$")
_BULLET_SPLIT = re.compile(r"\s*;\s*|\s*\|\s*")
_FILLER_START = re.compile(
    r"^(?:eh|em|bueno|vale|pues|entonces|o sea|y |pero |a ver|mira|es que)\b",
    re.I,
)


def _excerpt_for_title_llm(body: str, bullets: list[str], max_len: int) -> str:
    """Contexto rico para el titular: inicio, medio, final y viñetas."""
    plain = polish_fragment(body or " ".join(bullets))
    if not plain:
        return ""

    parts: list[str] = []
    if bullets:
        bl = [polish_fragment(b)[:120] for b in bullets[:4] if b.strip()]
        if bl:
            parts.append("Ideas del tramo: " + " | ".join(bl))

    sentences = split_sentences(plain) or [plain]
    if len(sentences) > 1 and _FILLER_START.search(sentences[0]):
        sentences = sentences[1:]

    if sentences:
        picks: list[str] = []
        if len(sentences) >= 3:
            idxs = [0, len(sentences) // 2, len(sentences) - 1]
        elif len(sentences) == 2:
            idxs = [0, 1]
        else:
            idxs = [0]
        for i in idxs:
            s = sentences[i].strip()
            if len(s) < 10:
                continue
            if len(s) > 220:
                s = s[:217].rsplit(" ", 1)[0] + "…"
            picks.append(s)
        if picks:
            parts.append("Extracto: " + " · ".join(picks))

    if not parts:
        parts.append(plain[:max_len])
    return "\n".join(parts)[:max_len]


def editorial_fallback_title(body: str, bullets: list[str] | None = None) -> str:
    """Titular temático por palabras clave (nunca una frase del audio)."""
    text = polish_fragment(body or " ".join(bullets or []))
    words = re.findall(r"[a-záéíóúñü]{4,}", text.lower())
    kept = [w for w in words if w not in _STOP]
    if not kept:
        return "Tema del tramo"

    top = [w for w, _ in Counter(kept).most_common(6)][:4]
    label = " ".join(w.capitalize() for w in top)
    words_out = label.split()
    if len(words_out) > INDEX_TITLE_WORDS_MAX:
        label = " ".join(words_out[:INDEX_TITLE_WORDS_MAX])
    return label[:56] if len(label) > 56 else label


def _sanitize_title(raw: str) -> str:
    t = re.sub(r"\*+", "", raw or "").strip().strip('"').strip("'").strip("«»")
    t = re.sub(
        r"^(?:título|titulo|titular|capítulo|capitulo|tema)\s*:\s*",
        "",
        t,
        flags=re.I,
    )
    t = t.rstrip(".!?…")
    if not t:
        return ""
    words = t.split()
    if len(words) > INDEX_TITLE_WORDS_MAX:
        t = " ".join(words[:INDEX_TITLE_WORDS_MAX])
    if t and t[0].islower():
        t = t[0].upper() + t[1:]
    return t


def _title_looks_copied(title: str, body: str) -> bool:
    """Detecta titulares que son trozos del texto en lugar de tema."""
    title = _sanitize_title(title)
    if not title:
        return True
    if len(title) > 58 or len(title.split()) > INDEX_TITLE_WORDS_MAX + 1:
        return True
    if _FILLER_START.search(title):
        return True
    if title.endswith("…") and len(title) > 24:
        return True

    body_plain = polish_fragment(body)[:500].lower()
    title_l = title.lower()
    if len(title_l) >= 28 and title_l in body_plain:
        return True

    first = (split_sentences(body_plain) or [body_plain])[0][:140]
    if first and len(title_l) >= 24 and title_l in first:
        return True

    tw = title_l.split()
    if len(tw) >= 6:
        run = " ".join(tw[:6])
        if run in body_plain:
            return True
    return False


def _parse_batch_line(raw_line: str) -> tuple[int, str, list[str]] | None:
    line = raw_line.strip()
    m = _TITLE_LINE.match(line)
    if not m:
        return None
    idx = int(m.group(1))
    rest = m.group(2).strip()
    if "|" in rest:
        title_part, bullets_part = rest.split("|", 1)
    else:
        title_part, bullets_part = rest, ""
    title = _sanitize_title(title_part.strip())
    bullets: list[str] = []
    if bullets_part.strip():
        for part in _BULLET_SPLIT.split(bullets_part):
            b = polish_fragment(part.strip().strip("•").strip("-").strip())
            if len(b) >= 12 and not _title_looks_copied(b, title):
                bullets.append(b[:160])
    return idx, title, bullets[:3]


def _titles_batch_groq(blocks: list[MomentBlock], lang: str) -> tuple[dict[int, str], dict[int, list[str]]]:
    if not GROQ_API_KEY or not blocks:
        return {}, {}

    chunks: list[str] = []
    for b in blocks:
        ts0 = format_timestamp(b.start)
        ts1 = format_timestamp(b.end)
        excerpt = _excerpt_for_title_llm(
            b.body or "",
            b.bullets,
            INDEX_TITLE_EXCERPT_CHARS,
        )
        chunks.append(
            f"--- Capítulo {b.index} ({ts0}–{ts1}) ---\n{excerpt}"
        )

    material = "\n\n".join(chunks)
    n = len(blocks)
    payload = {
        "model": INDEX_LLM_MODEL,
        "temperature": 0.25,
        "max_tokens": min(3200, 200 + 120 * n),
        "messages": [
            {"role": "system", "content": index_batch_system(lang)},
            {
                "role": "user",
                "content": f"Capítulos del vídeo ({n} tramos):\n\n{material}",
            },
        ],
    }
    titles: dict[int, str] = {}
    bullets_out: dict[int, list[str]] = {}
    try:
        r = httpx.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=90.0,
        )
        if r.status_code != 200:
            return {}, {}
        content = (
            r.json().get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        for line in content.splitlines():
            parsed = _parse_batch_line(line)
            if not parsed:
                continue
            idx, title, bl = parsed
            if title:
                titles[idx] = title
            if bl:
                bullets_out[idx] = bl
        return titles, bullets_out
    except Exception as e:
        logger.warning("Títulos índice Groq (lote): %s", e)
        return {}, {}


def _title_single_groq(block: MomentBlock, lang: str) -> str:
    if not GROQ_API_KEY:
        return ""
    excerpt = _excerpt_for_title_llm(
        block.body or "",
        block.bullets,
        INDEX_TITLE_EXCERPT_CHARS,
    )
    payload = {
        "model": INDEX_LLM_MODEL,
        "temperature": 0.2,
        "max_tokens": 80,
        "messages": [
            {"role": "system", "content": index_single_system(lang)},
            {
                "role": "user",
                "content": f"Resumen del tramo:\n{excerpt}",
            },
        ],
    }
    try:
        r = httpx.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=25.0,
        )
        if r.status_code != 200:
            return ""
        raw = (
            r.json().get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        raw = raw.split("\n", 1)[0]
        return _sanitize_title(raw)
    except Exception as e:
        logger.warning("Título índice Groq (uno): %s", e)
        return ""


def _titles_via_groq(
    blocks: list[MomentBlock], lang: str
) -> tuple[dict[int, str], dict[int, list[str]]]:
    titles: dict[int, str] = {}
    bullets: dict[int, list[str]] = {}
    step = max(1, INDEX_TITLES_BATCH_SIZE)
    for i in range(0, len(blocks), step):
        chunk = blocks[i : i + step]
        t_chunk, b_chunk = _titles_batch_groq(chunk, lang)
        titles.update(t_chunk)
        bullets.update(b_chunk)
    return titles, bullets


def _editorial_bullets(body: str, *, max_items: int = 3) -> list[str]:
    sentences = split_sentences(polish_fragment(body))
    if not sentences:
        return []
    scored = sorted(
        ((len(s.split()), i, s) for i, s in enumerate(sentences)),
        key=lambda x: (-x[0], x[1]),
    )
    out: list[str] = []
    for _, _, sent in scored:
        s = sent.strip()
        if len(s) < 20 or _FILLER_START.search(s):
            continue
        if len(s) > 140:
            s = s[:137].rsplit(" ", 1)[0] + "…"
        if s not in out:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _resolve_title(
    block: MomentBlock,
    llm: dict[int, str],
    lang: str,
    *,
    used_titles: set[str],
) -> str:
    candidate = llm.get(block.index, "")
    if candidate and not _title_looks_copied(candidate, block.body or ""):
        key = candidate.lower()
        if key not in used_titles:
            used_titles.add(key)
            return _sanitize_title(candidate)

    single = _title_single_groq(block, lang)
    if single and not _title_looks_copied(single, block.body or ""):
        key = single.lower()
        if key not in used_titles:
            used_titles.add(key)
            return single

    fb = editorial_fallback_title(block.body or "", block.bullets)
    key = fb.lower()
    if key in used_titles and block.bullets:
        alt = editorial_fallback_title(" ".join(block.bullets), [])
        if alt.lower() not in used_titles:
            fb = alt
    used_titles.add(fb.lower())
    return fb


def assign_intelligent_titles(
    blocks: list[MomentBlock], lang: str | None = None
) -> list[MomentBlock]:
    """Titular breve e inteligente por capítulo (nunca frase literal del audio)."""
    code = normalize_transcript_lang(lang)
    llm_titles: dict[int, str] = {}
    llm_bullets: dict[int, list[str]] = {}
    if GROQ_API_KEY:
        llm_titles, llm_bullets = _titles_via_groq(blocks, code)
    used: set[str] = set()
    for b in blocks:
        b.title = _resolve_title(b, llm_titles, code, used_titles=used)
        if llm_bullets.get(b.index):
            b.bullets = llm_bullets[b.index]
        elif not b.bullets or _title_looks_copied(b.bullets[0], b.body or ""):
            b.bullets = _editorial_bullets(b.body or "", max_items=4) or b.bullets
    return blocks


# Compatibilidad
_keyword_title = editorial_fallback_title
