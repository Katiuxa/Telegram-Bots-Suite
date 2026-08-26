"""Texto activo: original o traducción (resumen, índice, export, etc.)."""

from __future__ import annotations

from telegram.ext import ContextTypes

from bot.i18n import LANG_MENU, SUPPORTED
from bot.services.format_text import format_transcript
from bot.services.format_timestamps import segments_from_stored, store_segments
from bot.services.transcript_lang import (
    detected_language_label,
    normalize_source_lang,
    normalize_transcript_lang,
)
from bot.services.transcribe import TranscriptSegment

VARIANT_ORIGINAL = "original"


def get_source_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    raw = context.user_data.get("source_lang")
    if raw:
        return normalize_source_lang(raw)
    return normalize_transcript_lang(
        context.user_data.get("transcript_lang") or context.user_data.get("ui_lang")
    )


def get_variant(context: ContextTypes.DEFAULT_TYPE) -> str:
    v = context.user_data.get("transcript_variant", VARIANT_ORIGINAL)
    if v == VARIANT_ORIGINAL:
        return VARIANT_ORIGINAL
    code = normalize_transcript_lang(v)
    translations = context.user_data.get("translations") or {}
    return code if code in translations else VARIANT_ORIGINAL


def get_translations(context: ContextTypes.DEFAULT_TYPE) -> dict:
    raw = context.user_data.get("translations")
    return raw if isinstance(raw, dict) else {}


def has_translation(context: ContextTypes.DEFAULT_TYPE, lang: str) -> bool:
    code = normalize_transcript_lang(lang)
    return code in get_translations(context)


def list_translation_langs(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    return sorted(get_translations(context).keys())


def get_content_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Idioma del texto activo (para LLM: resumen, índice, highlights)."""
    variant = get_variant(context)
    if variant == VARIANT_ORIGINAL:
        return get_source_lang(context)
    return variant


def get_active_segments_stored(context: ContextTypes.DEFAULT_TYPE) -> list:
    variant = get_variant(context)
    if variant == VARIANT_ORIGINAL:
        return context.user_data.get("last_segments") or []
    tr = get_translations(context).get(variant)
    if tr and tr.get("segments"):
        return tr["segments"]
    return context.user_data.get("last_segments") or []


def get_active_segments(context: ContextTypes.DEFAULT_TYPE) -> list[TranscriptSegment]:
    return segments_from_stored(get_active_segments_stored(context))


def get_active_formatted(context: ContextTypes.DEFAULT_TYPE) -> str:
    variant = get_variant(context)
    if variant == VARIANT_ORIGINAL:
        return context.user_data.get("last_formatted") or ""
    tr = get_translations(context).get(variant)
    if tr and tr.get("formatted"):
        return tr["formatted"]
    return context.user_data.get("last_formatted") or ""


def translation_targets(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    source = get_source_lang(context)
    if source in SUPPORTED:
        return [code for code in SUPPORTED if code != source]
    return list(SUPPORTED)


def variant_button_label(context: ContextTypes.DEFAULT_TYPE, code: str, ui_lang: str) -> str:
    from bot.i18n import t

    active = get_variant(context)
    if code == VARIANT_ORIGINAL:
        src = get_source_lang(context)
        label = detected_language_label(src, ui_lang)
        short = t("variant_original_short", ui_lang, code=label)
        if active == VARIANT_ORIGINAL:
            short += " ✓"
        return short
    label = LANG_MENU.get(code, code.upper())
    if active == code:
        label += " ✓"
    if has_translation(context, code):
        label = f"{label}"
    return label


def set_variant(context: ContextTypes.DEFAULT_TYPE, variant: str) -> None:
    from bot.services.transcript_cache import invalidate_derived_cache

    if variant == VARIANT_ORIGINAL:
        new = VARIANT_ORIGINAL
    else:
        code = normalize_transcript_lang(variant)
        if not has_translation(context, code):
            return
        new = code

    old = get_variant(context)
    if old != new:
        invalidate_derived_cache(context)
    context.user_data["transcript_variant"] = new


def store_translation(
    context: ContextTypes.DEFAULT_TYPE,
    target_lang: str,
    segments_stored: list,
    formatted: str,
) -> None:
    from bot.services.transcript_cache import invalidate_derived_cache

    code = normalize_transcript_lang(target_lang)
    translations = get_translations(context)
    translations[code] = {"segments": segments_stored, "formatted": formatted}
    context.user_data["translations"] = translations
    invalidate_derived_cache(context)


def init_transcript_session(
    context: ContextTypes.DEFAULT_TYPE,
    segments_stored: list,
    formatted: str,
    source_lang: str,
) -> None:
    from bot.services.session_audio import clear_session_audio
    from bot.services.transcript_cache import on_new_transcript

    from bot.services.metadata import clear_document_metadata

    clear_session_audio(context)
    clear_document_metadata(context)
    context.user_data["last_segments"] = segments_stored
    context.user_data["last_formatted"] = formatted
    context.user_data["source_lang"] = normalize_source_lang(source_lang)
    context.user_data["translations"] = {}
    context.user_data["transcript_variant"] = VARIANT_ORIGINAL
    on_new_transcript(context, segments_stored)


def rebuild_formatted_from_segments(
    segments: list[TranscriptSegment], lang: str
) -> str:
    return format_transcript(segments, lang=lang)


def segments_to_stored(segments: list[TranscriptSegment]) -> list:
    return store_segments(segments)


def export_file_prefix(context: ContextTypes.DEFAULT_TYPE, base: str) -> str:
    """Nombre base del archivo exportado (incluye idioma si es traducción)."""
    variant = get_variant(context)
    if variant == VARIANT_ORIGINAL:
        return base
    return f"{base}_{variant}"
