"""Búsqueda inteligente en la transcripción activa (sin tildes, frases y palabras)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from bot.services.format_timestamps import format_timestamp
from bot.services.transcribe import TranscriptSegment

_EXCERPT_RADIUS = 140
_MAX_EXCERPT = 360


@dataclass(frozen=True)
class SearchHit:
    segment_index: int
    start: float
    end: float
    text: str
    match_start: int
    match_end: int


def fold_text(text: str) -> str:
    """Minúsculas sin diacríticos para comparar."""
    s = unicodedata.normalize("NFD", text or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.casefold()


def _fold_with_map(text: str) -> tuple[str, list[int]]:
    folded: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(text):
        base = unicodedata.normalize("NFD", ch)
        base = "".join(c for c in base if unicodedata.category(c) != "Mn")
        chunk = base.casefold() if base else ch.casefold()
        if not chunk and ch.isspace():
            chunk = " "
        for fc in chunk:
            folded.append(fc)
            index_map.append(i)
    return "".join(folded), index_map


def _span_in_original(text: str, folded: str, index_map: list[int], pos: int, length: int) -> tuple[int, int]:
    if not index_map or pos < 0:
        return 0, min(len(text), length)
    end_fold = min(pos + length - 1, len(index_map) - 1)
    start_orig = index_map[pos]
    end_orig = index_map[end_fold] + 1
    return max(0, start_orig), min(len(text), end_orig)


def _find_phrase_span(text: str, phrase: str) -> tuple[int, int] | None:
    phrase = phrase.strip()
    if not phrase:
        return None
    folded, index_map = _fold_with_map(text)
    fq = fold_text(phrase)
    if not fq:
        return None
    pos = folded.find(fq)
    if pos >= 0:
        return _span_in_original(text, folded, index_map, pos, len(fq))
    return None


def _find_words_span(text: str, words: list[str]) -> tuple[int, int] | None:
    if not words:
        return None
    folded, index_map = _fold_with_map(text)
    if not all(w in folded for w in words):
        return None
    first = words[0]
    pos = folded.find(first)
    if pos < 0:
        return None
    last = words[-1]
    pos_last = folded.rfind(last)
    if pos_last < 0:
        return _span_in_original(text, folded, index_map, pos, len(first))
    end_len = len(last)
    return _span_in_original(
        text,
        folded,
        index_map,
        pos,
        (pos_last - pos) + end_len,
    )


def _match_in_text(text: str, query: str) -> tuple[int, int] | None:
    q = (query or "").strip()
    if not q:
        return None
    span = _find_phrase_span(text, q)
    if span:
        return span
    words = [w for w in re.split(r"\s+", fold_text(q)) if len(w) >= 2]
    if len(words) >= 2:
        return _find_words_span(text, words)
    if len(words) == 1:
        folded, index_map = _fold_with_map(text)
        w = words[0]
        if len(w) < 2:
            return None
        pos = folded.find(w)
        if pos >= 0:
            return _span_in_original(text, folded, index_map, pos, len(w))
    return None


def _combined_text(segments: list[TranscriptSegment], i: int, n: int) -> str:
    parts = [(segments[j].text or "").strip() for j in range(i, min(i + n, len(segments)))]
    return " ".join(p for p in parts if p)


def find_search_hits(
    segments: list[TranscriptSegment],
    query: str,
    *,
    max_hits: int = 80,
) -> list[SearchHit]:
    q = (query or "").strip()
    if len(fold_text(q)) < 2:
        return []

    hits: list[SearchHit] = []
    seen: set[int] = set()

    for i, seg in enumerate(segments):
        text = (seg.text or "").strip()
        if not text:
            continue
        span = _match_in_text(text, q)
        if span:
            if i not in seen:
                seen.add(i)
                hits.append(
                    SearchHit(
                        segment_index=i,
                        start=seg.start,
                        end=seg.end,
                        text=text,
                        match_start=span[0],
                        match_end=span[1],
                    )
                )
            continue

        if " " in q:
            for window in (2, 3):
                if i + window > len(segments):
                    continue
                combined = _combined_text(segments, i, window)
                span = _match_in_text(combined, q)
                if span:
                    if i not in seen:
                        seen.add(i)
                        hits.append(
                            SearchHit(
                                segment_index=i,
                                start=seg.start,
                                end=segments[i + window - 1].end,
                                text=combined,
                                match_start=span[0],
                                match_end=span[1],
                            )
                        )
                    break

        if len(hits) >= max_hits:
            break

    return hits


def hits_to_stored(hits: list[SearchHit]) -> list[dict]:
    return [
        {
            "i": h.segment_index,
            "s": h.start,
            "e": h.end,
            "t": h.text,
            "ms": h.match_start,
            "me": h.match_end,
        }
        for h in hits
    ]


def hits_from_stored(raw: list | None) -> list[SearchHit]:
    out: list[SearchHit] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        out.append(
            SearchHit(
                segment_index=int(item.get("i", 0)),
                start=float(item.get("s", 0)),
                end=float(item.get("e", 0)),
                text=str(item.get("t", "")),
                match_start=int(item.get("ms", 0)),
                match_end=int(item.get("me", 0)),
            )
        )
    return out


def _md_escape(s: str) -> str:
    for ch in ("\\", "_", "*", "`", "["):
        s = s.replace(ch, "\\" + ch)
    return s


def _highlight_excerpt(text: str, start: int, end: int) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    start = max(0, min(start, len(raw)))
    end = max(start, min(end, len(raw)))
    lo = max(0, start - _EXCERPT_RADIUS)
    hi = min(len(raw), end + _EXCERPT_RADIUS)
    chunk = raw[lo:hi]
    ms = start - lo
    me = end - lo
    if len(chunk) > _MAX_EXCERPT:
        trim = len(chunk) - _MAX_EXCERPT
        if ms > trim // 2:
            drop = min(ms - 40, trim)
            chunk = chunk[drop:]
            ms -= drop
            me -= drop
        chunk = chunk[:_MAX_EXCERPT]
        me = min(me, len(chunk))

    before = _md_escape(chunk[:ms])
    mid = chunk[ms:me]
    after = _md_escape(chunk[me:])
    highlighted = f"*{_md_escape(mid)}*" if mid else ""
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(raw) else ""
    return f"{prefix}{before}{highlighted}{after}{suffix}"


def format_search_result_message(
    query: str,
    hit: SearchHit,
    *,
    page: int,
    total: int,
    lang: str,
) -> str:
    from bot.i18n import t

    ts_start = format_timestamp(hit.start)
    ts_end = format_timestamp(hit.end)
    excerpt = _highlight_excerpt(hit.text, hit.match_start, hit.match_end)
    q_disp = _md_escape(query.strip())
    lines = [
        t("search_result_title", lang, query=q_disp, cur=page + 1, total=total),
        "",
        t("search_result_time", lang, start=ts_start, end=ts_end),
        "",
        t("search_result_excerpt", lang),
        excerpt,
    ]
    return "\n".join(lines)
