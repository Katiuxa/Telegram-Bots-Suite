"""Highlights: lo más importante y trascendente del vídeo (con tiempo)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from bot.config import (
    GROQ_API_KEY,
    HIGHLIGHT_LABEL_MAX_CHARS,
    HIGHLIGHTS_LLM_CHARS,
    INDEX_LLM_MODEL,
)
from bot.services.format_timestamps import format_timestamp, merge_segments
from bot.services.index_titles import (
    _sanitize_title,
    _title_looks_copied,
    editorial_fallback_title,
)
from bot.services.llm_locale import highlights_system
from bot.services.summarize import GROQ_CHAT_URL
from bot.services.text_polish import polish_fragment, split_sentences
from bot.services.transcript_lang import normalize_transcript_lang
from bot.services.transcribe import TranscriptSegment

logger = logging.getLogger(__name__)

HIGHLIGHTS_MIN = 4
HIGHLIGHTS_MAX = 8
MIN_GAP_SEC = 25.0

_GENERIC_LABELS = frozenset(
    {
        "idea clave",
        "punto importante",
        "pregunta relevante",
        "introducción",
        "cierre",
        "destacado",
        "fragmento representativo",
    }
)

_IMPORTANT = re.compile(
    r"\b(importante|clave|esencial|recuerda|nunca|siempre|problema|soluci[oó]n|"
    r"resultado|conclusi[oó]n|recomendaci[oó]n|advertencia|error|éxito|"
    r"fundamental|crucial|imprescindible|destaca|trascendente|significa|"
    r"aprend|descubr|revela|demuestra|consejo|tip|error grave|ojo con)\b",
    re.I,
)


@dataclass
class HighlightItem:
    index: int
    start: float
    end: float
    quote: str
    reason: str


def polish_highlight_label(raw: str, quote: str) -> str:
    """Titular breve del highlight (tema), no la cita ni muletillas."""
    label = _sanitize_title(
        re.sub(r"^(?:titular|tema|motivo)\s*:\s*", "", raw or "", flags=re.I).strip()
    )
    low = label.lower()
    quote_plain = polish_fragment(quote)
    if not label or low in _GENERIC_LABELS:
        label = editorial_fallback_title(quote, [])
    elif len(label) >= 14 and label.lower() in quote_plain.lower():
        label = editorial_fallback_title(quote, [])
    elif len(quote_plain) > 100 and _title_looks_copied(label, quote_plain):
        label = editorial_fallback_title(quote, [])
    if len(label) > HIGHLIGHT_LABEL_MAX_CHARS:
        label = label[: HIGHLIGHT_LABEL_MAX_CHARS - 1].rsplit(" ", 1)[0]
    return label or "Momento clave"


def _score_line(text: str, position_ratio: float) -> float:
    score = 0.0
    if _IMPORTANT.search(text):
        score += 2.8
    words = len(text.split())
    if 10 <= words <= 40:
        score += 1.8
    elif 6 <= words < 10:
        score += 0.8
    elif words < 5:
        score -= 2.5
    if "?" in text or "!" in text:
        score += 0.7
    if re.search(r"\d+", text):
        score += 0.6
    if position_ratio < 0.1 or position_ratio > 0.85:
        score += 1.2
    return score


def _pick_heuristic(segments: list[TranscriptSegment]) -> list[HighlightItem]:
    merged = merge_segments(segments, max_gap=0.6)
    if not merged:
        return []

    total_dur = max((s.end for s in merged), default=1.0) or 1.0
    candidates: list[tuple[float, TranscriptSegment, str, float]] = []

    for seg in merged:
        text = polish_fragment(seg.text.strip())
        if len(text) < 20:
            continue
        pos = seg.start / total_dur
        for sent in split_sentences(text) or [text]:
            s = sent.strip()
            if len(s) < 18:
                continue
            sc = _score_line(s, pos)
            if sc < 1.5:
                continue
            reason = polish_highlight_label("", s)
            if _IMPORTANT.search(s):
                reason = polish_highlight_label("Dato clave", s)
            if "?" in s:
                reason = polish_highlight_label("Pregunta al público", s)
            if pos < 0.1:
                reason = polish_highlight_label("Apertura del tema", s)
            elif pos > 0.85:
                reason = polish_highlight_label("Conclusión final", s)
            candidates.append((sc, seg, s[:280], reason))

    candidates.sort(key=lambda x: -x[0])
    picked: list[HighlightItem] = []
    used_times: list[float] = []

    for sc, seg, quote, reason in candidates:
        if len(picked) >= HIGHLIGHTS_MAX:
            break
        if any(abs(seg.start - t) < MIN_GAP_SEC for t in used_times):
            continue
        picked.append(
            HighlightItem(
                index=len(picked) + 1,
                start=seg.start,
                end=seg.end,
                quote=quote,
                reason=reason,
            )
        )
        used_times.append(seg.start)

    if len(picked) < HIGHLIGHTS_MIN and merged:
        for seg in merged[:: max(1, len(merged) // HIGHLIGHTS_MIN)]:
            if len(picked) >= HIGHLIGHTS_MIN:
                break
            text = polish_fragment(seg.text.strip())[:240]
            if not text or any(abs(seg.start - t) < MIN_GAP_SEC for t in used_times):
                continue
            picked.append(
                HighlightItem(
                    index=len(picked) + 1,
                    start=seg.start,
                    end=seg.end,
                    quote=text,
                    reason=polish_highlight_label("", text),
                )
            )
            used_times.append(seg.start)

    for h in picked:
        h.reason = polish_highlight_label(h.reason, h.quote)
    return picked[:HIGHLIGHTS_MAX]


def _parse_llm_highlights(
    content: str, segments: list[TranscriptSegment]
) -> list[HighlightItem]:
    merged = merge_segments(segments, max_gap=0.5)
    if not merged:
        return []

    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    items: list[HighlightItem] = []
    ts_re = re.compile(r"\[?(\d{1,2}):(\d{2})(?::(\d{2}))?\]?")

    for ln in lines:
        m = ts_re.search(ln)
        if not m:
            continue
        g = m.groups()
        if g[2]:
            sec = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2])
        else:
            sec = int(g[0]) * 60 + int(g[1])
        rest = ln[m.end() :].strip(" -—|:")
        quote, _, reason = rest.partition("|")
        if not quote.strip():
            parts = re.split(r"\s+—\s+|\s+-\s+", rest, maxsplit=1)
            quote = parts[0] if parts else rest
            reason = parts[1] if len(parts) > 1 else "Destacado"
        quote = quote.strip().strip('"').strip("«»")[:300]
        reason = polish_highlight_label(reason or "", quote)
        if len(quote) < 12:
            continue
        seg = min(merged, key=lambda s: abs(s.start - sec))
        items.append(
            HighlightItem(
                index=len(items) + 1,
                start=seg.start,
                end=seg.end,
                quote=quote,
                reason=reason,
            )
        )

    return items[:HIGHLIGHTS_MAX]


def _timed_transcript_sample(
    segments: list[TranscriptSegment],
    max_chars: int,
) -> tuple[str, float]:
    """
    Texto para el LLM repartido en el tiempo (inicio, medio y final).
    Antes se cortaba solo el principio (~min 11 en vídeos de 27 min).
    """
    merged = merge_segments(segments, max_gap=0.5)
    if not merged:
        return "", 0.0

    entries: list[tuple[float, str]] = []
    for seg in merged:
        t = polish_fragment(seg.text.strip())
        if not t:
            continue
        entries.append((seg.start, f"[{format_timestamp(seg.start)}] {t}"))

    if not entries:
        return "", 0.0

    duration = max(seg.end for seg in merged)
    total_len = sum(len(line) + 1 for _, line in entries)
    if total_len <= max_chars:
        return "\n".join(line for _, line in entries), duration

    n_buckets = min(48, max(16, max_chars // 400))
    bucket_budget = max(120, max_chars // n_buckets)
    bucket_sec = max(duration / n_buckets, 1.0)
    picked: list[str] = []

    for b in range(n_buckets):
        t0 = b * bucket_sec
        t1 = duration + 0.001 if b == n_buckets - 1 else (b + 1) * bucket_sec
        used = 0
        for start, line in entries:
            if not (t0 <= start < t1):
                continue
            add = len(line) + 1
            if used + add > bucket_budget:
                continue
            picked.append(line)
            used += add

    if len(picked) < 12:
        step = max(1, len(entries) // min(24, n_buckets))
        picked = [entries[i][1] for i in range(0, len(entries), step)]

    seen: set[str] = set()
    unique: list[str] = []
    for line in picked:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)

    return "\n".join(unique)[:max_chars], duration


def _merge_highlight_lists(
    primary: list[HighlightItem], secondary: list[HighlightItem]
) -> list[HighlightItem]:
    out = list(primary)
    used = [h.start for h in out]
    for h in secondary:
        if len(out) >= HIGHLIGHTS_MAX:
            break
        if any(abs(h.start - t) < MIN_GAP_SEC for t in used):
            continue
        out.append(
            HighlightItem(
                index=len(out) + 1,
                start=h.start,
                end=h.end,
                quote=h.quote,
                reason=h.reason,
            )
        )
        used.append(h.start)
    out.sort(key=lambda h: h.start)
    for i, h in enumerate(out[:HIGHLIGHTS_MAX], 1):
        h.index = i
    return out[:HIGHLIGHTS_MAX]


def _pick_groq(
    segments: list[TranscriptSegment], formatted: str, lang: str
) -> list[HighlightItem]:
    merged = merge_segments(segments, max_gap=0.5, lang=lang)
    if not merged or not GROQ_API_KEY:
        return []

    body, duration = _timed_transcript_sample(segments, HIGHLIGHTS_LLM_CHARS)
    if len(body) < 80:
        return []

    dur_label = format_timestamp(duration) if duration > 0 else "?"

    payload = {
        "model": INDEX_LLM_MODEL,
        "temperature": 0.3,
        "max_tokens": 1800,
        "messages": [
            {"role": "system", "content": highlights_system(lang)},
            {
                "role": "user",
                "content": (
                    f"Duración del vídeo: ~{dur_label}. "
                    "La transcripción siguiente incluye muestras repartidas en el tiempo "
                    "(no es solo el inicio):\n\n"
                    f"{body}"
                ),
            },
        ],
    }
    try:
        r = httpx.post(
            GROQ_CHAT_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json=payload,
            timeout=55.0,
        )
        if r.status_code != 200:
            return []
        content = (
            r.json().get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        parsed = _parse_llm_highlights(content, segments)
        return parsed if len(parsed) >= 2 else []
    except Exception as e:
        logger.warning("Highlights Groq: %s", e)
        return []


def build_highlights(
    segments: list[TranscriptSegment],
    formatted: str = "",
    lang: str | None = None,
) -> list[HighlightItem]:
    del formatted
    code = normalize_transcript_lang(lang)
    merged = merge_segments(segments, max_gap=0.5, lang=code)
    total_dur = max((s.end for s in merged), default=0.0) if merged else 0.0

    llm = _pick_groq(segments, "", code)
    if len(llm) >= 2:
        for i, h in enumerate(llm, 1):
            h.index = i
            h.reason = polish_highlight_label(h.reason, h.quote)
        if total_dur >= 900 and max(h.start for h in llm) < total_dur * 0.5:
            late = _pick_heuristic([s for s in merged if s.start >= total_dur * 0.4])
            llm = _merge_highlight_lists(llm, late)
        return llm
    return _pick_heuristic(segments)


def format_highlights_plain(items: list[HighlightItem]) -> str:
    lines = [
        "HIGHLIGHTS — LO MÁS IMPORTANTE",
        "Selección de ideas trascendentes con tiempo en el vídeo.",
        "",
    ]
    for h in items:
        ts = format_timestamp(h.start)
        lines.append(f"{h.index}. [{ts}] {h.reason}")
        lines.append(f"   «{h.quote}»")
        lines.append("")
    return "\n".join(lines).strip()


def highlights_to_telegraph_nodes(items: list[HighlightItem]) -> list[dict]:
    nodes: list[dict] = [
        {
            "tag": "p",
            "children": [
                "Highlights: lo más importante del vídeo. Salta al tiempo indicado."
            ],
        },
        {"tag": "hr"},
    ]
    for h in items:
        ts = format_timestamp(h.start)
        nodes.append(
            {"tag": "h4", "children": [f"⭐ {h.index}. {h.reason}"]}
        )
        nodes.append(
            {
                "tag": "p",
                "children": [{"tag": "strong", "children": [f"⏱ {ts}"]}],
            }
        )
        nodes.append({"tag": "p", "children": [h.quote]})
        nodes.append({"tag": "hr"})
    if nodes and nodes[-1].get("tag") == "hr":
        nodes.pop()
    return nodes
