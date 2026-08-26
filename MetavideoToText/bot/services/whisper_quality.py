"""Filtrar segmentos Whisper claramente vacíos o inventados.

Conservador: no tumbar vídeos largos. Solo métricas acústicas claras,
scripts ajenos y franco-árabe evidente. Sin LLM.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

logger = logging.getLogger(__name__)

# Umbrales alineados con Whisper; no tirar voz real por logprob moderado.
_MAX_NO_SPEECH = 0.6
_MAX_NO_SPEECH_HARD = 0.85
_MAX_COMPRESSION = 2.4
_MIN_AVG_LOGPROB = -1.0

_ARABIC_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]+"
)
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]+")
_CJK_RE = re.compile(r"[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]+")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ']+")
_CAPS_RUN_RE = re.compile(r"\b[A-Z]{4,}(?:\s+[A-Z]{4,}){2,}\b")

_PROMPT_ECHO = frozenset(
    {
        "español",
        "espanol",
        "espa",
        "spanish",
        "english",
        "français",
        "francais",
        "french",
        "russian",
        "русский",
        "transcripción",
        "transcripcion",
        "transcription",
        "literal",
    }
)

_AR_PATTERN = re.compile(
    r"(?i)(?:"
    r"kh|gh|dh|aa|iy[aueo]|iyan|iyu|iyya|"
    r"q(?!u)|'|"
    r"wa[a-z]{3,}|hu[ao]|ila|hua|hatha|"
    r"amal|adab|taaliq|mafhom|kuliy|muntlaq|"
    r"arifu|haqqa|khafiy|mutasam|ghamid|"
    r"sirfan|thirpant|bermak|rajul|yamina|yasarina"
    r")"
)

_LATIN_LANGS = frozenset({"es", "en", "fr"})
_CYRILLIC_LANGS = frozenset({"ru"})
_OK_W = frozenset({"wifi", "whatsapp", "web", "www", "washington", "software", "show"})


def _lang_code(lang: str | None) -> str:
    from bot.services.transcript_lang import is_auto_detect, normalize_transcript_lang

    if is_auto_detect(lang):
        return "auto"
    return normalize_transcript_lang(lang)


def _letter_count(text: str) -> int:
    return len(_LETTER.findall(text or ""))


def _norm_tok(tok: str) -> str:
    return tok.lower().strip(".,;:!?¿¡\"'«»()[]{}")


def _strip_wrong_scripts(text: str, lang: str) -> str:
    t = text or ""
    if lang in _LATIN_LANGS:
        t = _ARABIC_RE.sub(" ", t)
        t = _CJK_RE.sub(" ", t)
        t = _CYRILLIC_RE.sub(" ", t)
    elif lang in _CYRILLIC_LANGS:
        t = _ARABIC_RE.sub(" ", t)
        t = _CJK_RE.sub(" ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _prompt_echo_loop(text: str) -> bool:
    words = _WORD_RE.findall((text or "").lower())
    if len(words) < 5:
        return False
    echo = sum(1 for w in words if w in _PROMPT_ECHO or w.startswith("espa"))
    return echo >= 4 and echo / len(words) >= 0.55


def _looks_franco_arabic_token(tok: str) -> bool:
    t = _norm_tok(tok)
    if len(t) < 3 or t in _OK_W:
        return False
    if "'" in t or "’" in t:
        return True
    if "w" in t and t not in _OK_W:
        return True
    if _AR_PATTERN.search(t):
        return True
    if re.search(r"(.)\1{2,}", t):
        return True
    if len(t) >= 6 and re.search(r"(iyan|iyu|iyya)$", t):
        return True
    return False


def _franco_arabic_ratio(text: str) -> float:
    words = _WORD_RE.findall(text or "")
    if len(words) < 6:
        return 0.0
    return sum(1 for w in words if _looks_franco_arabic_token(w)) / len(words)


def _is_franco_arabic_blob(text: str) -> bool:
    words = _WORD_RE.findall(text or "")
    if len(words) < 10:
        return False
    ratio = _franco_arabic_ratio(text)
    apos = sum(1 for w in words if "'" in w or "’" in w)
    return ratio >= 0.35 or (apos >= 4 and ratio >= 0.2)


def _strip_caps_gibberish_runs(text: str) -> str:
    return re.sub(r"\s{2,}", " ", _CAPS_RUN_RE.sub(" ", text or "")).strip()


def _strip_franco_arabic_runs(text: str) -> str:
    tokens = re.findall(r"\S+", text or "")
    if len(tokens) < 4:
        return text
    fa = [_looks_franco_arabic_token(t) for t in tokens]
    bad = [False] * len(tokens)
    i = 0
    while i < len(tokens):
        if fa[i]:
            j = i
            while j < len(tokens) and fa[j]:
                j += 1
            if j - i >= 4:
                for k in range(i, j):
                    bad[k] = True
            i = j
        else:
            i += 1
    out = [t for t, drop in zip(tokens, bad) if not drop]
    return re.sub(r"\s{2,}", " ", " ".join(out)).strip()


def clean_segment_text(text: str, lang: str | None = None) -> str:
    if not (text or "").strip():
        return ""
    code = _lang_code(lang)
    t = _strip_wrong_scripts(text, code)
    if code in _LATIN_LANGS:
        if _is_franco_arabic_blob(t):
            return ""
        t = _strip_caps_gibberish_runs(t)
        t = _strip_franco_arabic_runs(t)
        if t and _is_franco_arabic_blob(t):
            return ""
    return re.sub(r"\s{2,}", " ", t).strip()


def scrub_hallucinated_text(text: str, lang: str | None = None) -> str:
    return clean_segment_text(text, lang)


def scrub_transcript_document(text: str, lang: str | None = None) -> str:
    if not (text or "").strip():
        return ""
    code = _lang_code(lang)
    blocks = re.split(r"\n{2,}", text)
    return "\n\n".join(c for b in blocks if (c := clean_segment_text(b, code)))


def segment_likely_hallucination(meta: dict, *, lang: str | None = None) -> bool:
    text = (meta.get("text") or "").strip()
    if not text:
        return True
    if _prompt_echo_loop(text):
        return True

    code = _lang_code(lang)
    if code in _LATIN_LANGS and _is_franco_arabic_blob(text):
        return True

    cleaned = clean_segment_text(text, code)
    if not cleaned:
        return True

    nsp = meta.get("no_speech_prob")
    nsp_v = float(nsp) if nsp is not None else None
    if nsp_v is not None and nsp_v > _MAX_NO_SPEECH_HARD:
        return True

    flags = 0
    if nsp_v is not None and nsp_v > _MAX_NO_SPEECH:
        flags += 1
    cr = meta.get("compression_ratio")
    if cr is not None and float(cr) > _MAX_COMPRESSION:
        flags += 1
    lp = meta.get("avg_logprob")
    if lp is not None and float(lp) < _MIN_AVG_LOGPROB:
        flags += 1
    return flags >= 2


def filter_segment_dicts(
    segments: list[dict], *, lang: str | None = None
) -> list[dict]:
    if not segments:
        return segments
    code = _lang_code(lang)
    kept: list[dict] = []
    for s in segments:
        if segment_likely_hallucination(s, lang=code):
            continue
        text = (s.get("text") or "").strip()
        cleaned = clean_segment_text(text, code)
        if not cleaned:
            continue
        if cleaned != text:
            s = {**s, "text": cleaned}
        kept.append(s)
    dropped = len(segments) - len(kept)
    if dropped:
        logger.info(
            "Whisper: descartados %s/%s segmentos lang=%s",
            dropped,
            len(segments),
            code,
        )
    # Si el filtro vació todo, conservar originales (mejor texto imperfecto que fallo total)
    if not kept and segments:
        logger.warning(
            "Whisper: filtro vació el trozo; se conservan segmentos originales lang=%s",
            code,
        )
        return segments
    return kept


def filter_transcript_segments(
    segments: Sequence,
    *,
    lang: str | None = None,
) -> list:
    if not segments:
        return list(segments)
    code = _lang_code(lang)
    kept: list = []
    for seg in segments:
        text = getattr(seg, "text", "") or ""
        if segment_likely_hallucination({"text": text}, lang=code):
            continue
        cleaned = clean_segment_text(text, code)
        if not cleaned:
            continue
        if cleaned != text:
            kept.append(type(seg)(seg.start, seg.end, cleaned))
        else:
            kept.append(seg)
    if not kept and segments:
        logger.warning(
            "Whisper: filtro post-ensamblado vació todo; se conserva original lang=%s",
            code,
        )
        return list(segments)
    dropped = len(segments) - len(kept)
    if dropped:
        logger.info(
            "Whisper: filtrados %s/%s segmentos post-ensamblado lang=%s",
            dropped,
            len(segments),
            code,
        )
    return kept
