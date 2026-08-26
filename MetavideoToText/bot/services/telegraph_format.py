"""Páginas Telegraph para «Leer en Telegram» — solo texto legible, sin minutos."""

from __future__ import annotations

import re

from bot.i18n import t
from bot.services.format_text import format_transcript
from bot.services.transcript_lang import normalize_transcript_lang
from bot.services.transcribe import TranscriptSegment


def _plain_md(text: str) -> str:
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", text or "")
    s = re.sub(r"\*([^*]+)\*", r"\1", s)
    s = re.sub(r"_([^_]+)_", r"\1", s)
    return s.strip()


def _p(text: str) -> dict:
    return {"tag": "p", "children": [_plain_md(text)]}


def _h4(text: str) -> dict:
    return {"tag": "h4", "children": [_plain_md(text)]}


def _hr() -> dict:
    return {"tag": "hr"}


def _nodes_from_transcript_text(text: str) -> list[dict]:
    nodes: list[dict] = []
    for block in re.split(r"\n{2,}", text):
        block = block.strip()
        if not block:
            continue
        if len(block) > 280:
            nodes.append({"tag": "blockquote", "children": [_plain_md(block)]})
        else:
            nodes.append(_p(block))
    return nodes


def build_transcript_telegraph(
    segments: list[TranscriptSegment],
    *,
    lang: str = "es",
) -> tuple[str, list[dict]]:
    if not segments:
        return t("tg_title", lang), []

    code = normalize_transcript_lang(lang)
    plain = format_transcript(segments, lang=code)
    words = len(re.findall(r"\w+", plain, flags=re.UNICODE))
    title = t("tg_title", lang)

    nodes: list[dict] = [
        {"tag": "h3", "children": [title]},
        _p(t("tg_intro", lang, words=words)),
        _hr(),
    ]
    nodes.extend(_nodes_from_transcript_text(plain))

    if nodes and nodes[-1].get("tag") == "hr":
        nodes.pop()

    nodes.append(_hr())
    nodes.append({"tag": "p", "children": [{"tag": "em", "children": [t("tg_footer", lang)]}]})
    return title, nodes
