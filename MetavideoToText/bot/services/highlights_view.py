"""Vista de highlights: listado + lectura por momento."""

from __future__ import annotations

import math

from telegram.ext import ContextTypes

from bot.config import HIGHLIGHT_QUOTE_MAX_CHARS
from bot.i18n import t
from bot.services.format_timestamps import format_timestamp
from bot.services.highlights import HighlightItem
from bot.services.text_chunks import split_for_telegram

HIGHLIGHTS_TOC_PAGE_SIZE = 10


def highlight_button_label(item: HighlightItem) -> str:
    reason = (item.reason or "Destacado").replace("\n", " ").strip()
    ts = format_timestamp(item.start)
    label = f"{item.index:02d} · {ts} — {reason}"
    if len(label) <= 64:
        return label
    room = 64 - len(f"{item.index:02d} · {ts} — ")
    if room > 10:
        short = reason[: room - 1].rsplit(" ", 1)[0] + "…"
        return f"{item.index:02d} · {ts} — {short}"
    return f"{item.index:02d}. {reason[:58]}…"


def split_highlight_quote(quote: str, lang: str | None = None) -> list[str]:
    text = (quote or "").strip()
    if not text:
        return [t("no_quote_saved", lang or "es")]
    return split_for_telegram(text, HIGHLIGHT_QUOTE_MAX_CHARS)


def items_to_stored(items: list[HighlightItem]) -> list[dict]:
    return [
        {
            "i": h.index,
            "s": h.start,
            "e": h.end,
            "q": h.quote,
            "r": h.reason,
        }
        for h in items
    ]


def items_from_stored(raw: list | None) -> list[HighlightItem]:
    out: list[HighlightItem] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        out.append(
            HighlightItem(
                index=int(item.get("i", len(out) + 1)),
                start=float(item.get("s", 0)),
                end=float(item.get("e", 0)),
                quote=str(item.get("q", "")),
                reason=str(item.get("r", "Destacado")),
            )
        )
    return out


def format_highlights_toc(
    items: list[HighlightItem],
    toc_page: int = 0,
    *,
    page_size: int = HIGHLIGHTS_TOC_PAGE_SIZE,
    lang: str | None = None,
) -> str:
    code = lang or "es"
    total = len(items)
    pages = max(1, math.ceil(total / page_size))
    toc_page = max(0, min(toc_page, pages - 1))
    start = toc_page * page_size
    chunk = items[start : start + page_size]

    lines = [
        t("highlights_toc_title", code, total=total),
        "",
        t("highlights_toc_hint", code),
        "",
    ]
    for h in chunk:
        ts = format_timestamp(h.start)
        reason = h.reason.replace("*", "").strip()
        lines.append(f"• `{ts}` · *{reason}*")
    if pages > 1:
        lines.append("")
        lines.append(t("index_toc_page", code, cur=toc_page + 1, total=pages))
    return "\n".join(lines)


def format_highlight_telegram(
    item: HighlightItem,
    item_page: int,
    item_total: int,
    *,
    text_page: int,
    text_total: int,
    quote_slice: str,
    seek_hint: str = "",
) -> str:
    ts = format_timestamp(item.start)
    reason = item.reason.replace("*", "").strip()
    lines = [
        f"⭐ *{reason}*",
        f"⏱ `{ts}` · _Highlight {item_page + 1} de {item_total}_",
    ]
    if text_total > 1:
        lines.append(f"_Fragmento {text_page + 1} de {text_total} de esta cita_")
    lines.extend(["", f"«{quote_slice}»"])
    if seek_hint:
        lines.append(seek_hint)
    return "\n".join(lines).strip()


def store_highlights_view(
    context: ContextTypes.DEFAULT_TYPE, items: list[HighlightItem]
) -> None:
    context.user_data["hi_blocks"] = items_to_stored(items)
    context.user_data["hi_page"] = 0
    context.user_data["hi_total"] = len(items)
    context.user_data["hi_mode"] = "toc"
    context.user_data["hi_toc_page"] = 0
    context.user_data["hi_subpage"] = 0
    context.user_data["hi_quote_pages"] = []


def get_highlights_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("hi_page", 0))


def set_highlights_page(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    total = max(1, int(context.user_data.get("hi_total", 1)))
    context.user_data["hi_page"] = max(0, min(page, total - 1))


def get_hi_toc_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("hi_toc_page", 0))


def set_hi_toc_page(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    items = get_stored_highlights(context)
    pages = max(1, math.ceil(len(items) / HIGHLIGHTS_TOC_PAGE_SIZE))
    context.user_data["hi_toc_page"] = max(0, min(page, pages - 1))


def get_hi_subpage(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("hi_subpage", 0))


def set_hi_subpage(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    pages = context.user_data.get("hi_quote_pages") or []
    total = max(1, len(pages))
    context.user_data["hi_subpage"] = max(0, min(page, total - 1))


def load_highlight_quote_pages(
    context: ContextTypes.DEFAULT_TYPE, item: HighlightItem
) -> list[str]:
    from bot.i18n import get_lang

    pages = split_highlight_quote(item.quote, get_lang(context))
    context.user_data["hi_quote_pages"] = pages
    context.user_data["hi_subpage"] = 0
    return pages


def get_stored_highlights(context: ContextTypes.DEFAULT_TYPE) -> list[HighlightItem]:
    return items_from_stored(context.user_data.get("hi_blocks"))
