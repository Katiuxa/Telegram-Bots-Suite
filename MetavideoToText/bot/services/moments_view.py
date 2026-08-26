"""Vista del índice inteligente: listado + transcripción por capítulo."""

from __future__ import annotations

import math

from telegram.ext import ContextTypes

from bot.config import MOMENT_BODY_MAX_CHARS
from bot.i18n import t
from bot.services.format_timestamps import MomentBlock, format_timestamp
from bot.services.text_chunks import split_for_telegram

INDEX_TOC_PAGE_SIZE = 10


def chapter_button_label(block: MomentBlock) -> str:
    title = (block.title or "Capítulo").replace("\n", " ").strip()
    ts = format_timestamp(block.start)
    label = f"{block.index:02d} · {ts} — {title}"
    if len(label) <= 64:
        return label
    room = 64 - len(f"{block.index:02d} · {ts} — ")
    if room > 12:
        short = title[: room - 1].rsplit(" ", 1)[0] + "…"
        return f"{block.index:02d} · {ts} — {short}"
    return f"{block.index:02d}. {title[:58]}…"


def split_moment_body(body: str, lang: str | None = None) -> list[str]:
    text = (body or "").strip()
    if not text:
        return [t("no_text_segment", lang or "es")]
    return split_for_telegram(text, MOMENT_BODY_MAX_CHARS)


def blocks_to_stored(blocks: list[MomentBlock]) -> list[dict]:
    return [
        {
            "i": b.index,
            "s": b.start,
            "e": b.end,
            "t": b.title,
            "b": list(b.bullets),
            "y": b.body,
        }
        for b in blocks
    ]


def blocks_from_stored(raw: list | None) -> list[MomentBlock]:
    out: list[MomentBlock] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        bullets = [str(x) for x in item.get("b") or []]
        body = str(item.get("y") or "")
        if not body and bullets:
            body = "\n\n".join(bullets)
        out.append(
            MomentBlock(
                index=int(item.get("i", len(out) + 1)),
                start=float(item.get("s", 0)),
                end=float(item.get("e", 0)),
                title=str(item.get("t", "Capítulo")),
                bullets=bullets,
                body=body,
            )
        )
    return out


def format_index_toc(
    blocks: list[MomentBlock],
    toc_page: int = 0,
    *,
    page_size: int = INDEX_TOC_PAGE_SIZE,
    lang: str | None = None,
) -> str:
    code = lang or "es"
    total = len(blocks)
    pages = max(1, math.ceil(total / page_size))
    toc_page = max(0, min(toc_page, pages - 1))
    start = toc_page * page_size
    chunk = blocks[start : start + page_size]

    lines = [
        t("index_toc_title", code, total=total),
        "",
        t("index_toc_hint", code),
        "",
    ]
    for b in chunk:
        title = b.title.replace("*", "").strip()
        ts = format_timestamp(b.start)
        lines.append(f"• `{ts}` · *{title}*")
    if pages > 1:
        lines.append("")
        lines.append(t("index_toc_page", code, cur=toc_page + 1, total=pages))
    return "\n".join(lines)


def format_moment_telegram(
    block: MomentBlock,
    chapter_page: int,
    chapter_total: int,
    *,
    text_page: int,
    text_total: int,
    body_slice: str,
    seek_hint: str = "",
) -> str:
    ts0 = format_timestamp(block.start)
    ts1 = format_timestamp(block.end)
    title = block.title.replace("*", "").strip()
    lines = [
        f"📑 *{title}*",
        f"⏱ `{ts0}` – `{ts1}` · _Capítulo {chapter_page + 1} de {chapter_total}_",
    ]
    if text_total > 1:
        lines.append(f"_Fragmento {text_page + 1} de {text_total} de este capítulo_")
    lines.extend(["", body_slice])
    if seek_hint:
        lines.append(seek_hint)
    return "\n".join(lines).strip()


def store_moments_view(context: ContextTypes.DEFAULT_TYPE, blocks: list[MomentBlock]) -> None:
    context.user_data["mom_blocks"] = blocks_to_stored(blocks)
    context.user_data["mom_page"] = 0
    context.user_data["mom_total"] = len(blocks)
    context.user_data["mom_mode"] = "toc"
    context.user_data["mom_toc_page"] = 0
    context.user_data["mom_subpage"] = 0
    context.user_data["mom_body_pages"] = []


def get_moments_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("mom_page", 0))


def set_moments_page(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    total = max(1, int(context.user_data.get("mom_total", 1)))
    context.user_data["mom_page"] = max(0, min(page, total - 1))


def get_mom_toc_page(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("mom_toc_page", 0))


def set_mom_toc_page(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    blocks = get_stored_moment_blocks(context)
    pages = max(1, math.ceil(len(blocks) / INDEX_TOC_PAGE_SIZE))
    context.user_data["mom_toc_page"] = max(0, min(page, pages - 1))


def get_mom_subpage(context: ContextTypes.DEFAULT_TYPE) -> int:
    return int(context.user_data.get("mom_subpage", 0))


def set_mom_subpage(context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    pages = context.user_data.get("mom_body_pages") or []
    total = max(1, len(pages))
    context.user_data["mom_subpage"] = max(0, min(page, total - 1))


def load_moment_body_pages(
    context: ContextTypes.DEFAULT_TYPE, block: MomentBlock
) -> list[str]:
    from bot.i18n import get_lang

    pages = split_moment_body(
        block.body or "\n".join(f"• {x}" for x in block.bullets),
        get_lang(context),
    )
    context.user_data["mom_body_pages"] = pages
    context.user_data["mom_subpage"] = 0
    return pages


def get_stored_moment_blocks(context: ContextTypes.DEFAULT_TYPE) -> list[MomentBlock]:
    return blocks_from_stored(context.user_data.get("mom_blocks"))
