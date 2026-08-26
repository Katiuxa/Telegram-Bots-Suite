"""Paginación de transcripciones largas en Telegram."""

from bot.config import TRANSCRIPT_BODY_MAX, TRANSCRIPT_BODY_MAX_FIRST
from bot.services.text_chunks import pack_into_pages, split_for_telegram


def pack_transcript_pages(
    parts: list[str],
    *,
    first_page_max: int = TRANSCRIPT_BODY_MAX_FIRST,
    page_max: int = TRANSCRIPT_BODY_MAX,
) -> list[str]:
    """
    Agrupa párrafos en el mínimo de pantallas posible, llenando cada mensaje
    hasta el límite seguro de Telegram.
    """
    return pack_into_pages(
        parts,
        first_page_max=first_page_max,
        page_max=page_max,
        oversized_split=lambda text: split_for_telegram(text, page_max),
    )


def page_body(
    flat_pages: list[str],
    page: int,
) -> str:
    if not flat_pages:
        return ""
    page = max(0, min(page, len(flat_pages) - 1))
    return flat_pages[page]


def store_transcript_pages(
    context,
    parts: list[str],
    *,
    engine: str,
) -> None:
    flat = pack_transcript_pages(parts)
    context.user_data["tx_parts"] = flat
    context.user_data["tx_page"] = 0
    context.user_data["tx_engine"] = engine
    context.user_data["tx_total_pages"] = max(1, len(flat))


def get_transcript_page(context) -> int:
    return int(context.user_data.get("tx_page", 0))


def set_transcript_page(context, page: int) -> None:
    total = int(context.user_data.get("tx_total_pages", 1))
    context.user_data["tx_page"] = max(0, min(page, total - 1))


def transcript_header(
    page: int,
    total: int,
    lang: str | None = None,
    context=None,
) -> str:
    """Sin prefijo: el texto del mensaje es solo la transcripción (paginación en botones)."""
    return ""
