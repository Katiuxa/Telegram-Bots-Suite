"""Título y descripción automáticos para exportaciones (URL + reglas + Groq)."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from html import unescape
from pathlib import Path

import httpx

from bot.config import (
    AUTO_PDF,
    DOCUMENT_TITLE_DEFAULT,
    EXPORT_TOC,
    GROQ_API_KEY,
    MAX_CHARS_FOR_TELEGRAM,
    METADATA_DESCRIPTION_MAX,
    METADATA_ENABLED,
    ROOT,
)
from bot.i18n import t
from bot.services.formatter import structure_document
from bot.services.llm import generate_meta_description

logger = logging.getLogger(__name__)

_DESCRIPTION_MAX = METADATA_DESCRIPTION_MAX
_GENERIC_LABELS = frozenset(
    {"audio", "vídeo", "video", "enlace", "link"}
)
_OG_TITLE_RE = re.compile(
    r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_TW_TITLE_RE = re.compile(
    r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
_WHITESPACE_RE = re.compile(r"\s+")


def format_document_title(title: str) -> str:
    cleaned = _WHITESPACE_RE.sub(" ", title.strip())
    if not cleaned:
        return cleaned
    return " ".join(
        word[:1].upper() + word[1:].lower() if word else word
        for word in cleaned.split(" ")
    )


def sanitize_filename_part(text: str, *, max_len: int = 48) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text.strip())
    cleaned = _WHITESPACE_RE.sub("_", cleaned)
    cleaned = cleaned.strip("._")
    if not cleaned:
        return "transcripcion"
    return cleaned[:max_len]


async def _fetch_url_title(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=12.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; MetavideoToText/1.0)"},
        ) as client:
            response = await client.get(url)
    except (httpx.HTTPError, OSError) as exc:
        logger.debug("No se pudo obtener título de %s: %s", url, exc)
        return None

    if response.status_code >= 400:
        return None

    html = response.text[:120_000]
    for pattern in (_OG_TITLE_RE, _TW_TITLE_RE, _TITLE_TAG_RE):
        match = pattern.search(html)
        if match:
            title = unescape(match.group(1).strip())
            title = _WHITESPACE_RE.sub(" ", title)
            if title and title.lower() not in ("instagram", "tiktok", "youtube"):
                return title[:240]
    return None


def _fetch_ytdlp_title(url: str) -> str | None:
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--no-warnings",
        "--print",
        "title",
        "--skip-download",
        url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            cwd=str(ROOT),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("yt-dlp title falló para %s: %s", url, exc)
        return None
    if proc.returncode != 0:
        return None
    title = (proc.stdout or "").strip().splitlines()[0] if proc.stdout else ""
    title = _WHITESPACE_RE.sub(" ", title)
    return title[:240] if title else None


async def _resolve_title(
    source: str | None,
    label: str | None,
    current_title: str | None,
) -> str | None:
    if current_title and current_title.strip():
        return format_document_title(current_title)

    if source:
        title = _fetch_ytdlp_title(source)
        if title:
            return format_document_title(title)
        title = await _fetch_url_title(source)
        if title:
            return format_document_title(title)

    if label:
        lab = label.strip()
        if lab.lower() not in _GENERIC_LABELS and len(lab) > 2:
            return format_document_title(lab)
    return None


def _truncate_description(text: str) -> str:
    text = _WHITESPACE_RE.sub(" ", text.strip())
    if len(text) <= _DESCRIPTION_MAX:
        return text
    cut = text[:_DESCRIPTION_MAX]
    last_dot = cut.rfind(". ")
    if last_dot > _DESCRIPTION_MAX // 2:
        return cut[: last_dot + 1].strip()
    return cut.rstrip(" ,;") + "…"


async def finalize_transcript_document(
    *,
    formatted: str,
    lang: str | None,
    source: str | None = None,
    label: str | None = None,
) -> tuple[str, dict[str, str]]:
    """
    Tras Whisper: estructura el documento, título (URL/archivo), descripción
    (última frase → Groq si hay clave) y metadatos para exportar.
    """
    if not METADATA_ENABLED:
        return formatted, {}

    title_guess = await _resolve_title(source, label, None) or DOCUMENT_TITLE_DEFAULT
    title_out, desc_fallback, body_out = structure_document(formatted, title_guess, None)

    description = desc_fallback
    if GROQ_API_KEY and desc_fallback:
        llm_desc = await generate_meta_description(
            title_out, body_out, lang=lang or "es"
        )
        if llm_desc:
            description = llm_desc

    description = _truncate_description(description) if description else ""

    updates: dict[str, str] = {"doc_title": title_out}
    if description:
        updates["doc_description"] = description
    if source and source.strip():
        updates["doc_source"] = source.strip()

    return formatted, updates


async def enrich_transcript_metadata(
    *,
    plain: str,
    lang: str | None,
    source: str | None = None,
    label: str | None = None,
    current_title: str | None = None,
    current_description: str | None = None,
) -> dict[str, str]:
    """Compatibilidad: delega en finalize_transcript_document."""
    _, updates = await finalize_transcript_document(
        formatted=plain,
        lang=lang,
        source=source,
        label=label,
    )
    if current_title and "doc_title" not in updates:
        updates["doc_title"] = format_document_title(current_title)
    if current_description:
        updates["doc_description"] = _truncate_description(current_description)
    return updates


async def maybe_generate_auto_pdf(
    context,
    *,
    title: str,
    description: str,
    body_plain_len: int,
) -> Path | None:
    """PDF automático si AUTO_PDF y el texto es corto."""
    import asyncio

    from bot.services.pdf_export import export_transcript_pdf

    if not AUTO_PDF or body_plain_len > MAX_CHARS_FOR_TELEGRAM:
        context.user_data.pop("auto_pdf_path", None)
        return None

    formatted = context.user_data.get("last_formatted") or ""
    prefix = export_file_prefix_from_context(context, "transcripcion")
    ui_lang = None
    try:
        from bot.i18n import get_lang

        ui_lang = get_lang(context)
    except Exception:
        ui_lang = "es"
    src_url = context.user_data.get("doc_source")
    source_line = (
        f"{t('metainfo_source', ui_lang)}: {src_url}" if src_url else None
    )

    def _build() -> Path:
        return export_transcript_pdf(
            title=title,
            description=description,
            body=formatted,
            include_toc=EXPORT_TOC,
            prefix=prefix,
            source=source_line,
        )

    try:
        path = await asyncio.to_thread(_build)
        context.user_data["auto_pdf_path"] = str(path)
        return path
    except Exception:
        logger.exception("AUTO_PDF")
        context.user_data.pop("auto_pdf_path", None)
        return None


def get_document_metadata(context) -> dict[str, str]:
    title = context.user_data.get("doc_title")
    description = context.user_data.get("doc_description")
    source = context.user_data.get("doc_source")
    meta: dict[str, str] = {}
    if isinstance(title, str) and title.strip():
        meta["title"] = title.strip()
    if isinstance(description, str) and description.strip():
        meta["description"] = description.strip()
    if isinstance(source, str) and source.strip():
        meta["source"] = source.strip()
    return meta


def apply_metadata_updates(context, updates: dict[str, str]) -> None:
    for key in ("doc_title", "doc_description", "doc_source"):
        if key in updates and updates[key]:
            context.user_data[key] = updates[key]


def clear_document_metadata(context) -> None:
    for key in ("doc_title", "doc_description", "doc_source"):
        context.user_data.pop(key, None)


def metainfo_block(meta: dict[str, str], lang: str | None) -> str:
    lines: list[str] = []
    title = meta.get("title") or meta.get("doc_title")
    if title:
        lines.append(format_document_title(title))
    description = meta.get("description") or meta.get("doc_description")
    if description:
        lines.append(description)
    source = meta.get("source") or meta.get("doc_source")
    if source:
        lines.append(f"{t('metainfo_source', lang)}: {source}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n\n"


def prepend_metainfo(content: str, meta: dict[str, str], lang: str | None) -> str:
    block = metainfo_block(meta, lang)
    if not block:
        return content
    return block + content


def export_title(context, *, fallback: str | None = None) -> str:
    meta = get_document_metadata(context)
    return meta.get("title") or fallback or DOCUMENT_TITLE_DEFAULT


def export_file_prefix_from_context(context, base: str) -> str:
    from bot.services.transcript_active import export_file_prefix

    meta = get_document_metadata(context)
    if meta.get("title"):
        return sanitize_filename_part(meta["title"])
    return export_file_prefix(context, base)
