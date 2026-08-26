import re

from bot.config import FAST_POLISH, PARAGRAPH_GAP_SEC
from bot.services.text_polish import (
    ensure_end_punctuation,
    group_paragraphs,
    infer_sentences,
    merge_segments,
    polish_fragment,
    sentences_from_segments,
)
from bot.services.transcript_lang import polish_lang
from bot.services.transcribe import TranscriptSegment

_PARA_MAX_SENTENCES = 3
_PARA_MAX_CHARS = 280
# Español: párrafos naturales (evitar trozos de 1 frase a mitad de idea).
_ES_PARA_MAX_SENTENCES = 4
_ES_PARA_MAX_CHARS = 420
_ES_PARA_GAP_SEC = 0.85


def _para_limits(lang: str) -> tuple[int, int]:
    if lang == "es":
        return _ES_PARA_MAX_SENTENCES, _ES_PARA_MAX_CHARS
    return _PARA_MAX_SENTENCES, _PARA_MAX_CHARS


def _paragraphs_from_segments(
    segs: list[TranscriptSegment],
    lang: str,
    *,
    fast: bool = False,
) -> list[str]:
    sentences: list[str] = []
    parts: list[str] = []
    prev_end: float | None = None
    gap_limit = _ES_PARA_GAP_SEC if lang == "es" else PARAGRAPH_GAP_SEC
    max_sent, max_chars = _para_limits(lang)

    def flush_parts() -> None:
        nonlocal parts
        if not parts:
            return
        chunk = polish_fragment(" ".join(parts), lang=lang, fast=fast)
        if not chunk:
            parts = []
            return
        if len(chunk) > 50:
            sentences.extend(infer_sentences(chunk, lang, fast=fast))
        else:
            sentences.append(ensure_end_punctuation(chunk, lang))
        parts = []

    for seg in segs:
        gap = (seg.start - prev_end) if prev_end is not None else 0.0
        if prev_end is not None and gap >= gap_limit and parts:
            flush_parts()
        if seg.text.strip():
            parts.append(seg.text.strip())
        prev_end = seg.end

    flush_parts()

    if not sentences:
        fallback = sentences_from_segments(segs, lang)
        return (
            group_paragraphs(
                fallback,
                max_sentences=max_sent,
                max_chars=max_chars,
            )
            if fallback
            else []
        )
    return group_paragraphs(
        sentences,
        max_sentences=max_sent,
        max_chars=max_chars,
    )


def _format_structured(
    segments: list[TranscriptSegment],
    lang: str,
    *,
    fast: bool = False,
) -> str:
    paras = _paragraphs_from_segments(segments, lang, fast=fast)
    if paras:
        return "\n\n".join(paras)

    merged = merge_segments(segments, lang=lang, fast=fast)
    text = polish_fragment(
        " ".join(s.text.strip() for s in merged if s.text.strip()),
        lang=lang,
        fast=fast,
    )
    if not text:
        return ""
    sentences = infer_sentences(text, lang, fast=fast)
    max_sent, max_chars = _para_limits(lang)
    paras = group_paragraphs(
        sentences,
        max_sentences=max_sent,
        max_chars=max_chars,
    )
    return "\n\n".join(paras) if paras else text


def format_transcript(
    segments: list[TranscriptSegment],
    lang: str | None = None,
    *,
    fast: bool | None = None,
) -> str:
    from bot.services.text_polish import (
        heal_false_sentence_breaks,
        pair_spanish_inverted_punctuation,
        repair_broken_paragraphs,
    )

    if not segments:
        return ""

    code = polish_lang(lang)
    if fast is None:
        fast = FAST_POLISH
    text = heal_false_sentence_breaks(
        _format_structured(segments, code, fast=fast), code
    )
    text = repair_broken_paragraphs(text, code)
    if code == "es":
        text = pair_spanish_inverted_punctuation(text)
    return text


def transcript_to_telegraph_nodes(
    segments: list[TranscriptSegment], lang: str | None = None
) -> list[dict]:
    text = format_transcript(segments, lang=lang)
    if not text:
        return []

    nodes: list[dict] = [{"tag": "hr"}]
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        if len(block) > 280:
            nodes.append({"tag": "blockquote", "children": [block]})
        else:
            nodes.append({"tag": "p", "children": [block]})
    return nodes
