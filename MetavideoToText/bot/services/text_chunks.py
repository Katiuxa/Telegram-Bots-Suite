"""Partir textos largos en fragmentos seguros para Telegram."""

from bot.config import TELEGRAM_SAFE_CHARS
from bot.services.format_timestamps import SECTION_SEP


def split_for_telegram(text: str, limit: int = TELEGRAM_SAFE_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]

    if "\n\n" in text:
        parts: list[str] = []
        for block in text.split("\n\n"):
            block = block.strip()
            if not block:
                continue
            if len(block) <= limit:
                parts.append(block)
            else:
                parts.extend(split_for_telegram(block, limit))
        if parts:
            return parts

    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest[:limit]
        split_at = cut.rfind("\n\n")
        if split_at < limit // 3:
            split_at = cut.rfind("\n")
        if split_at < limit // 3:
            split_at = cut.rfind(". ")
        if split_at < limit // 3:
            split_at = cut.rfind(" ")
        if split_at < 100:
            split_at = limit
        chunks.append(rest[:split_at].rstrip())
        rest = rest[split_at:].lstrip()

    return chunks


def split_moments_for_telegram(text: str, limit: int = TELEGRAM_SAFE_CHARS) -> list[str]:
    """Parte por capítulos (━━━), no por una línea interminable."""
    if SECTION_SEP not in text:
        return split_for_telegram(text, limit)

    header, _, body = text.partition(SECTION_SEP)
    sections = [s.strip() for s in body.split(SECTION_SEP) if s.strip()]
    chunks: list[str] = []
    current = header.strip()

    for section in sections:
        candidate = (current + SECTION_SEP + section).strip() if current else section
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(section) <= limit:
            current = section
        else:
            for part in split_for_telegram(section, limit):
                chunks.append(part)
            current = ""
    if current:
        chunks.append(current)
    return chunks or [text]


def pack_into_pages(
    parts: list[str],
    *,
    first_page_max: int,
    page_max: int,
    oversized_split,
) -> list[str]:
    """Une fragmentos pequeños en pantallas casi llenas (mínimo de mensajes)."""
    pages: list[str] = []
    batch: list[str] = []
    batch_len = 0

    def limit_for_next_page() -> int:
        return first_page_max if not pages else page_max

    def flush() -> None:
        nonlocal batch, batch_len
        if batch:
            pages.append("\n\n".join(batch))
            batch = []
            batch_len = 0

    for raw in parts:
        chunk = (raw or "").strip()
        if not chunk:
            continue

        if len(chunk) > page_max:
            flush()
            pages.extend(oversized_split(chunk))
            continue

        sep = "\n\n" if batch else ""
        add = len(sep) + len(chunk)
        cap = limit_for_next_page()

        if batch_len + add <= cap:
            batch.append(chunk)
            batch_len += add
            continue

        flush()
        cap = limit_for_next_page()
        if len(chunk) <= cap:
            batch = [chunk]
            batch_len = len(chunk)
        else:
            pages.extend(oversized_split(chunk))

    flush()
    return pages
