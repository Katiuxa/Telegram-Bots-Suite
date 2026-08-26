"""Reutiliza índice, highlights y resumen de la misma transcripción."""

from __future__ import annotations

import hashlib

from telegram.ext import ContextTypes

from bot.services.format_timestamps import MomentBlock, segments_from_stored
from bot.services.highlights import HighlightItem
from bot.services.highlights_view import items_from_stored, items_to_stored
from bot.services.moments_view import blocks_from_stored, blocks_to_stored

_CACHE_KEYS = (
    "cache_index_blocks",
    "cache_index_iv",
    "cache_highlights",
    "cache_highlights_iv",
    "cache_highlights_ver",
    "cache_index_ver",
    "cache_summary",
    "cache_telegraph_url",
)

# Sube al cambiar la lógica derivada (títulos, highlights, etc.)
INDEX_CACHE_VERSION = "v4"
HIGHLIGHTS_CACHE_VERSION = "v3"


def fingerprint(segments_stored: list | None) -> str:
    if not segments_stored:
        return ""
    h = hashlib.sha256()
    h.update(str(len(segments_stored)).encode())
    sample = segments_stored[:5] + segments_stored[-5:]
    for item in sample:
        if isinstance(item, dict):
            h.update(
                f"{item.get('s')}|{item.get('e')}|{(item.get('t') or '')[:120]}".encode(
                    "utf-8", errors="replace"
                )
            )
    return h.hexdigest()[:20]


def _cache_scope(context: ContextTypes.DEFAULT_TYPE) -> str:
    from bot.services.transcript_active import get_active_segments_stored, get_variant

    stored = get_active_segments_stored(context)
    if not stored:
        return ""
    return f"{fingerprint(stored)}:{get_variant(context)}"


def _fp_matches(context: ContextTypes.DEFAULT_TYPE) -> bool:
    scope = _cache_scope(context)
    if not scope:
        return False
    return context.user_data.get("cache_scope") == scope


def _touch_cache_scope(context: ContextTypes.DEFAULT_TYPE) -> None:
    scope = _cache_scope(context)
    if scope:
        context.user_data["cache_scope"] = scope


def invalidate_derived_cache(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in _CACHE_KEYS:
        context.user_data.pop(key, None)
    context.user_data.pop("mom_blocks", None)
    context.user_data.pop("hi_blocks", None)
    context.user_data.pop("mom_view_msg_id", None)
    context.user_data.pop("hi_view_msg_id", None)
    context.user_data.pop("mom_view_chat_id", None)
    context.user_data.pop("hi_view_chat_id", None)
    from bot.services.search_nav import clear_search_state

    clear_search_state(context)


def on_new_transcript(
    context: ContextTypes.DEFAULT_TYPE, segments_stored: list
) -> None:
    fp = fingerprint(segments_stored)
    if context.user_data.get("cache_fp") == fp:
        return
    invalidate_derived_cache(context)
    context.user_data["cache_fp"] = fp
    _touch_cache_scope(context)


def get_cached_index_blocks(
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[list[MomentBlock] | None, str | None]:
    if not _fp_matches(context):
        return None, None
    if context.user_data.get("cache_index_ver") != INDEX_CACHE_VERSION:
        return None, None
    raw = context.user_data.get("cache_index_blocks")
    if not raw:
        return None, None
    return blocks_from_stored(raw), context.user_data.get("cache_index_iv")


def store_index_cache(
    context: ContextTypes.DEFAULT_TYPE,
    blocks: list[MomentBlock],
    iv_url: str | None = None,
) -> None:
    context.user_data["cache_index_blocks"] = blocks_to_stored(blocks)
    context.user_data["cache_index_ver"] = INDEX_CACHE_VERSION
    if iv_url:
        context.user_data["cache_index_iv"] = iv_url
    _touch_cache_scope(context)


def get_cached_highlights(
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[list[HighlightItem] | None, str | None]:
    if not _fp_matches(context):
        return None, None
    if context.user_data.get("cache_highlights_ver") != HIGHLIGHTS_CACHE_VERSION:
        return None, None
    raw = context.user_data.get("cache_highlights")
    if not raw:
        return None, None
    return items_from_stored(raw), context.user_data.get("cache_highlights_iv")


def store_highlights_cache(
    context: ContextTypes.DEFAULT_TYPE,
    items: list[HighlightItem],
    iv_url: str | None = None,
) -> None:
    context.user_data["cache_highlights"] = items_to_stored(items)
    context.user_data["cache_highlights_ver"] = HIGHLIGHTS_CACHE_VERSION
    if iv_url:
        context.user_data["cache_highlights_iv"] = iv_url
    _touch_cache_scope(context)


def store_summary_cache(context: ContextTypes.DEFAULT_TYPE, summary: str) -> None:
    context.user_data["cache_summary"] = summary
    _touch_cache_scope(context)


def get_cached_telegraph_url(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not _fp_matches(context):
        return None
    url = context.user_data.get("cache_telegraph_url")
    return url if isinstance(url, str) and url.startswith("http") else None


def get_cached_summary(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    if not _fp_matches(context):
        return None
    s = context.user_data.get("cache_summary")
    return s if isinstance(s, str) and s.strip() else None


def store_telegraph_cache(context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    context.user_data["cache_telegraph_url"] = url
    _touch_cache_scope(context)
