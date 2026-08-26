"""Traducción de calidad (Groq) + respaldo gratuito si Groq satura."""

from __future__ import annotations

import logging
import re
import time

import httpx

from bot.config import (
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_CHAT_URL,
    TRANSLATE_CHUNK_PAUSE_SEC,
    TRANSLATE_LLM_CHUNK_CHARS,
    TRANSLATE_LLM_FALLBACK,
    TRANSLATE_LLM_MODEL,
    TRANSLATE_LLM_MODELS,
)
from bot.i18n_progress import prog
from bot.services.llm_locale import language_name_en, translate_batch_system
from bot.services.transcript_lang import normalize_source_lang, normalize_transcript_lang
from bot.services.transcribe import TranscriptSegment

logger = logging.getLogger(__name__)

_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.+)$", re.MULTILINE)
_TRANSLATE_TEMPERATURE = 0.35
_TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}


class TranslationError(Exception):
    """Fallo de traducción (límite API, parseo, etc.)."""


class TranslationRateLimitError(TranslationError):
    """Todos los modelos Groq saturados."""


def _api_keys() -> list[str]:
    keys = list(GROQ_API_KEYS) if GROQ_API_KEYS else []
    if GROQ_API_KEY and GROQ_API_KEY not in keys:
        keys.insert(0, GROQ_API_KEY)
    return keys


def _unique_models() -> list[str]:
    from bot.services.groq_router import default_translate_cascade

    out: list[str] = []
    for m in list(TRANSLATE_LLM_MODELS or []) + [
        TRANSLATE_LLM_MODEL,
        *default_translate_cascade(),
        TRANSLATE_LLM_FALLBACK,
        "openai/gpt-oss-20b",
    ]:
        name = (m or "").strip()
        if name and name not in out:
            out.append(name)
    return out or ["openai/gpt-oss-20b"]


def _groq_chat(
    messages: list[dict],
    *,
    max_tokens: int = 4096,
    lang: str = "es",
    progress_note=None,
) -> str:
    from bot.services.groq_router import get_router, parse_retry_after_seconds

    keys = _api_keys()
    if not keys:
        raise TranslationError(prog("translate_no_key", lang))

    router = get_router()
    base_models = _unique_models()
    router.ensure(base_models)
    last_status = 0
    last_err = ""
    saw_rate_limit = False
    timeout = httpx.Timeout(120.0, connect=25.0)
    attempts_per_model = 2

    # Recorrer claves; en cada clave, modelos ordenados por router (calidad + cuota).
    for key_i, api_key in enumerate(keys):
        models = router.ordered_models(base_models)
        if not models:
            models = list(base_models)
        for model_i, model in enumerate(models):
            for attempt in range(attempts_per_model):
                # Reordenar en caliente si otros modelos se liberaron
                if attempt == 0 and model_i > 0:
                    refreshed = router.ordered_models(base_models)
                    if refreshed and refreshed[0] != model and refreshed[0] not in models[:model_i]:
                        # El primero fresco tiene prioridad: saltar a él en la próxima vuelta
                        pass
                payload = {
                    "model": model,
                    "temperature": _TRANSLATE_TEMPERATURE,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                try:
                    r = httpx.post(
                        GROQ_CHAT_URL,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                        timeout=timeout,
                    )
                    last_status = r.status_code
                    if r.status_code in _TRANSIENT_HTTP:
                        if r.status_code == 429:
                            saw_rate_limit = True
                            reset = parse_retry_after_seconds(r, attempt)
                            router.mark_rate_limited(model, reset)
                            has_more_models = model_i < len(models) - 1
                            has_more_keys = key_i < len(keys) - 1
                            has_alt = has_more_models or has_more_keys
                            wait = router.sleep_before_retry(
                                model=model,
                                reset_sec=reset,
                                has_alternative=has_alt,
                            )
                            logger.warning(
                                "Groq 429 model=%s key=%s → salto (%.2fs)",
                                model.split("/")[-1],
                                key_i + 1,
                                wait,
                            )
                            # Sin mensajes de «saturado» al usuario: magia intacta.
                            if progress_note:
                                progress_note(prog("translating", lang), "")
                            if has_more_models:
                                break  # siguiente modelo ya
                            if has_more_keys:
                                break  # siguiente clave
                            # Último recurso en este modelo: un reintento corto
                            continue
                        wait = min(2.5, 0.8 * (2**attempt))
                        logger.warning(
                            "Groq traducción %s %s, reintento en %.1fs",
                            model,
                            r.status_code,
                            wait,
                        )
                        time.sleep(wait)
                        continue
                    if r.status_code in (401, 403):
                        logger.warning(
                            "Groq traducción auth %s key=%s: %s",
                            r.status_code,
                            key_i + 1,
                            r.text[:200],
                        )
                        if key_i < len(keys) - 1:
                            break
                        raise TranslationError(prog("translate_auth_fail", lang))
                    if r.status_code == 400 and "model" in (r.text or "").lower():
                        last_err = r.text[:180]
                        router.mark_unavailable(model)
                        logger.warning(
                            "Groq modelo no disponible %s: %s", model, last_err
                        )
                        break
                    if r.status_code != 200:
                        last_err = r.text[:180]
                        logger.warning(
                            "Groq traducción %s %s: %s",
                            model,
                            r.status_code,
                            last_err,
                        )
                        break
                    content = (
                        r.json()
                        .get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        or ""
                    ).strip()
                    if content:
                        router.mark_ok(model)
                        if model_i > 0 or key_i > 0:
                            logger.info(
                                "Traducción OK con model=%s key=%s",
                                model,
                                key_i + 1,
                            )
                        return content
                    logger.warning(
                        "Groq traducción %s: respuesta vacía (intento %s)",
                        model,
                        attempt + 1,
                    )
                    break
                except TranslationError:
                    raise
                except httpx.TimeoutException as e:
                    last_err = f"timeout: {e}"
                    wait = min(3.0, 1.0 * (2**attempt))
                    logger.warning(
                        "Traducción Groq timeout (%s), reintento en %.1fs",
                        model,
                        wait,
                    )
                    time.sleep(wait)
                    continue
                except httpx.HTTPError as e:
                    last_err = str(e)
                    wait = min(3.0, 1.0 * (2**attempt))
                    logger.warning(
                        "Traducción Groq red (%s), reintento en %.1fs: %s",
                        model,
                        wait,
                        e,
                    )
                    time.sleep(wait)
                    continue
                except Exception as e:
                    last_err = str(e)
                    logger.warning("Traducción Groq falló (%s): %s", model, e)
                    break

    if saw_rate_limit or last_status == 429:
        raise TranslationRateLimitError(prog("translate_rate_limit", lang))
    if last_err:
        logger.error("Traducción Groq agotada: status=%s err=%s", last_status, last_err)
    raise TranslationError(prog("translate_api_fail", lang))


def _split_oversized(text: str, max_chars: int) -> list[str]:
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= max_chars:
        return [body]

    parts: list[str] = []
    start = 0
    n = len(body)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            window = body[start:end]
            cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
            if cut < max_chars // 3:
                cut = window.rfind(" ")
            if cut >= max_chars // 4:
                end = start + cut + 1
        piece = body[start:end].strip()
        if piece:
            parts.append(piece)
        start = end if end > start else start + max_chars
    return parts


def _chunk_formatted_text(body: str, max_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [body]

    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for para in paragraphs:
        pieces = _split_oversized(para, max_chars)
        for piece in pieces:
            plen = len(piece) + 2
            if buf and size + plen > max_chars:
                chunks.append("\n\n".join(buf))
                buf = []
                size = 0
            buf.append(piece)
            size += plen
    if buf:
        chunks.append("\n\n".join(buf))
    return chunks


def _lang_code(code: str | None) -> str:
    c = (code or "auto").strip().lower()[:2]
    if c in ("", "xx", "und"):
        return "auto"
    return c


def _google_translate(text: str, *, source: str, target: str) -> str | None:
    """Traducción gratis (Google gtx). Sin API key."""
    body = (text or "").strip()
    if not body:
        return body
    sl = _lang_code(source)
    tl = _lang_code(target)
    if tl == "auto":
        return None
    timeout = httpx.Timeout(60.0, connect=20.0)
    try:
        r = httpx.get(
            "https://translate.googleapis.com/translate_a/single",
            params={
                "client": "gtx",
                "sl": sl if sl != "auto" else "auto",
                "tl": tl,
                "dt": "t",
                "q": body,
            },
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 MetaMedia2Text/1.0"},
        )
        if r.status_code != 200:
            logger.warning("Google Translate HTTP %s", r.status_code)
            return None
        data = r.json()
        parts = []
        for row in data[0] or []:
            if row and row[0]:
                parts.append(row[0])
        out = "".join(parts).strip()
        return out or None
    except Exception as e:
        logger.warning("Google Translate falló: %s", e)
        return None


def _mymemory_translate(text: str, *, source: str, target: str) -> str | None:
    """Respaldo MyMemory (límite ~500 chars por petición)."""
    body = (text or "").strip()
    if not body:
        return body
    sl = _lang_code(source)
    tl = _lang_code(target)
    if tl in ("auto",):
        return None
    if sl == "auto":
        sl = "en"
    timeout = httpx.Timeout(45.0, connect=15.0)
    pieces = _split_oversized(body, 450)
    out: list[str] = []
    try:
        with httpx.Client(timeout=timeout) as client:
            for piece in pieces:
                r = client.get(
                    "https://api.mymemory.translated.net/get",
                    params={"q": piece, "langpair": f"{sl}|{tl}"},
                )
                if r.status_code != 200:
                    return None
                data = r.json()
                tr = (
                    (data.get("responseData") or {}).get("translatedText") or ""
                ).strip()
                if not tr or tr.lower().startswith("query length limit"):
                    return None
                out.append(tr)
                time.sleep(0.25)
        return " ".join(out).strip() or None
    except Exception as e:
        logger.warning("MyMemory falló: %s", e)
        return None


def _mt_translate_chunk(
    text: str,
    *,
    source_lang: str,
    target_lang: str,
) -> str:
    """Cascada gratuita: Google → MyMemory."""
    src = _lang_code(source_lang)
    tgt = _lang_code(target_lang)
    # Conservar párrafos: traducir por bloque
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()] or [text]
    translated: list[str] = []
    for para in paras:
        piece = None
        for chunk in _split_oversized(para, 3500):
            got = _google_translate(chunk, source=src, target=tgt)
            if not got:
                got = _mymemory_translate(chunk, source=src, target=tgt)
            if not got:
                raise TranslationError("mt_fail")
            if piece is None:
                piece = got
            else:
                piece = f"{piece} {got}"
            time.sleep(0.35)
        translated.append(piece or para)
    return "\n\n".join(translated)



def _parse_numbered_lines(content: str, expected: int) -> list[str] | None:
    found: dict[int, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if m:
            found[int(m.group(1))] = m.group(2).strip()
    if len(found) >= max(1, expected // 2):
        return [found.get(i, "") for i in range(1, expected + 1)]
    return None


def _llm_translate_chunk(
    chunk: str,
    *,
    source_lang: str,
    target_lang: str,
    ui_lang: str,
    progress_note=None,
) -> str:
    src = language_name_en(source_lang)
    tgt = language_name_en(target_lang)
    prompt = (
        f"Localize this spoken transcript excerpt from {src} to natural {tgt}.\n"
        "Rules:\n"
        "- Read the whole excerpt first; use context for slang, jokes and "
        "ambiguous phrases.\n"
        "- Same energy and register (slang, swearing, hype) — fluent native "
        "speech, not a dictionary calque.\n"
        "- Adapt idioms; vary swear intensity — do not stamp the same filler "
        "onto every clause.\n"
        "- Keep names, game titles, brands, URLs and numbers unchanged.\n"
        "- Preserve paragraph breaks exactly as in the source.\n"
        "- Output ONLY the translated text, no commentary or labels.\n\n"
        f"{chunk}"
    )
    return _groq_chat(
        [
            {
                "role": "system",
                "content": translate_batch_system(source_lang, target_lang),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=min(8192, max(800, len(chunk) * 2 + 600)),
        lang=ui_lang,
        progress_note=progress_note,
    )


def _translate_batch(
    lines: list[str],
    *,
    source_lang: str,
    target_lang: str,
    ui_lang: str = "es",
) -> list[str]:
    if not lines:
        return []
    src = language_name_en(source_lang)
    tgt = language_name_en(target_lang)
    numbered = "\n".join(f"[{i + 1}] {text}" for i, text in enumerate(lines))
    prompt = (
        f"Localize each numbered spoken line from {src} to natural {tgt}.\n"
        "Rules:\n"
        "- Same vibe as the speaker (hype, sarcasm, slang, swearing) — "
        "not a stiff or word-for-word calque.\n"
        "- Adapt idioms; do not paste the same filler swear on every line.\n"
        "- Keep names, game titles, brands, URLs and numbers unchanged.\n"
        "- Use surrounding lines as context so the rant flows as one speech.\n"
        "- Output ONLY lines in the form [N] translated text, same numbering.\n"
        "- Do not merge or skip lines.\n\n"
        f"{numbered}"
    )
    try:
        content = _groq_chat(
            [
                {
                    "role": "system",
                    "content": translate_batch_system(source_lang, target_lang),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=min(4096, 120 * len(lines) + 400),
            lang=ui_lang,
        )
    except TranslationRateLimitError:
        # Respaldo MT línea a línea
        out = []
        for line in lines:
            out.append(
                _mt_translate_chunk(
                    line, source_lang=source_lang, target_lang=target_lang
                )
            )
        return out
    parsed = _parse_numbered_lines(content, len(lines))
    if not parsed:
        logger.warning("Traducción: no se pudo parsear lote (%s líneas)", len(lines))
        raise TranslationError(prog("translate_parse_fail", ui_lang))
    out: list[str] = []
    for orig, trans in zip(lines, parsed):
        out.append(trans.strip() if trans.strip() else orig)
    return out


def _batch_segments(
    segments: list[TranscriptSegment], max_chars: int
) -> list[list[TranscriptSegment]]:
    batches: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    size = 0
    for seg in segments:
        tlen = len(seg.text or "")
        if current and size + tlen > max_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(seg)
        size += tlen
    if current:
        batches.append(current)
    return batches


def translate_formatted_text(
    text: str,
    *,
    source_lang: str,
    target_lang: str,
    ui_lang: str = "es",
    progress_cb=None,
) -> str:
    """Traduce el texto: Groq primero; si satura, termina con Google/MyMemory."""
    body = (text or "").strip()
    if not body:
        return body
    max_chunk = max(1400, min(TRANSLATE_LLM_CHUNK_CHARS, 2600))
    chunks = _chunk_formatted_text(body, max_chunk)
    if not chunks:
        return body

    pause = max(0.35, min(TRANSLATE_CHUNK_PAUSE_SEC, 1.2))
    translated_parts: list[str] = []
    total = len(chunks)
    use_mt = False

    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(pause if not use_mt else 0.35)
        pct = 12 + int(60 * i / max(1, total))
        if progress_cb:
            progress_cb(pct, prog("translating", ui_lang), f"{i + 1}/{total}")

        def _note(msg: str, detail: str = "") -> None:
            if progress_cb:
                # Nunca enseñar saturación/cuotas: solo «Traduciendo».
                progress_cb(pct, prog("translating", ui_lang), detail or f"{i + 1}/{total}")

        if use_mt:
            try:
                part = _mt_translate_chunk(
                    chunk, source_lang=source_lang, target_lang=target_lang
                )
            except TranslationError:
                raise TranslationError(prog("translate_mt_fail", ui_lang))
            translated_parts.append(part.strip())
            continue

        try:
            part = _llm_translate_chunk(
                chunk,
                source_lang=source_lang,
                target_lang=target_lang,
                ui_lang=ui_lang,
                progress_note=_note if progress_cb else None,
            )
            if not part.strip():
                raise TranslationError(prog("translate_parse_fail", ui_lang))
            translated_parts.append(part.strip())
        except TranslationRateLimitError:
            logger.warning(
                "Groq sin cuota útil en trozo %s/%s → MT silencioso",
                i + 1,
                total,
            )
            use_mt = True
            if progress_cb:
                progress_cb(pct, prog("translating", ui_lang), f"{i + 1}/{total}")
            try:
                part = _mt_translate_chunk(
                    chunk, source_lang=source_lang, target_lang=target_lang
                )
            except TranslationError:
                raise TranslationError(prog("translate_mt_fail", ui_lang))
            translated_parts.append(part.strip())
        except TranslationError:
            logger.warning("Groq falló en trozo %s → intento MT", i + 1)
            try:
                if progress_cb:
                    progress_cb(pct, prog("translating", ui_lang), f"{i + 1}/{total}")
                part = _mt_translate_chunk(
                    chunk, source_lang=source_lang, target_lang=target_lang
                )
                use_mt = True
                translated_parts.append(part.strip())
            except TranslationError:
                raise

    return "\n\n".join(translated_parts)


def translate_segments(
    segments: list[TranscriptSegment],
    *,
    source_lang: str,
    target_lang: str,
    ui_lang: str = "es",
    progress_cb=None,
) -> list[TranscriptSegment]:
    src = normalize_source_lang(source_lang)
    tgt = normalize_transcript_lang(target_lang)
    if src == tgt:
        return list(segments)

    batches = _batch_segments(segments, TRANSLATE_LLM_CHUNK_CHARS)
    translated: list[TranscriptSegment] = []
    done = 0
    total = len(segments)
    pause = max(0.5, TRANSLATE_CHUNK_PAUSE_SEC)

    for i, batch in enumerate(batches):
        if i > 0:
            time.sleep(pause)
        texts = [s.text for s in batch]
        out_texts = _translate_batch(
            texts,
            source_lang=src,
            target_lang=tgt,
            ui_lang=ui_lang,
        )
        for seg, new_text in zip(batch, out_texts):
            translated.append(
                TranscriptSegment(start=seg.start, end=seg.end, text=new_text)
            )
        done += len(batch)
        if progress_cb:
            progress_cb(done, total)

    return translated
