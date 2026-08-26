"""Paginación del resumen en un solo mensaje editable."""

from bot.config import SUMMARY_BODY_MAX, SUMMARY_BODY_MAX_FIRST
from bot.i18n import t
from bot.services.text_chunks import pack_into_pages, split_for_telegram


def pack_summary_pages(parts: list[str]) -> list[str]:
    return pack_into_pages(
        parts,
        first_page_max=SUMMARY_BODY_MAX_FIRST,
        page_max=SUMMARY_BODY_MAX,
        oversized_split=lambda text: split_for_telegram(text, SUMMARY_BODY_MAX),
    )


def page_body(flat_pages: list[str], page: int) -> str:
    if not flat_pages:
        return ""
    page = max(0, min(page, len(flat_pages) - 1))
    return flat_pages[page]


def store_summary_pages(context, summary: str) -> None:
    parts = split_for_telegram(summary, SUMMARY_BODY_MAX)
    flat = pack_summary_pages(parts)
    context.user_data["sum_parts"] = flat
    context.user_data["sum_page"] = 0
    context.user_data["sum_total_pages"] = max(1, len(flat))


def get_summary_page(context) -> int:
    return int(context.user_data.get("sum_page", 0))


def set_summary_page(context, page: int) -> None:
    total = int(context.user_data.get("sum_total_pages", 1))
    context.user_data["sum_page"] = max(0, min(page, total - 1))


def summary_header(page: int, total: int, lang: str | None = None) -> str:
    code = lang or "es"
    if total <= 1:
        return t("summary_header_single", code)
    return t("summary_header", code, cur=page + 1, total=total)
