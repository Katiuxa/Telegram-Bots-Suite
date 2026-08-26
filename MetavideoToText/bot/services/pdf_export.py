"""PDF estructurado (título, descripción, cuerpo; índice opcional)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from bot.config import TEMP_DIR
from bot.services.export_files import _pdf_multi_cell, _plain_for_file, _resolve_unicode_font
from bot.services.formatter import MAX_CHARS_TITLE

logger = logging.getLogger(__name__)


def export_transcript_pdf(
    *,
    title: str,
    description: str,
    body: str,
    include_toc: bool = False,
    prefix: str = "transcripcion",
    source: str | None = None,
) -> Path:
    from fpdf import FPDF

    font_path = _resolve_unicode_font()
    if not font_path:
        raise RuntimeError("No hay fuente Unicode para PDF.")

    plain = _plain_for_file(body)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TEMP_DIR / f"{prefix}_{stamp}.pdf"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    family = "UniFont"
    pdf.add_font(family, "", str(font_path))

    _pdf_multi_cell(pdf, family, (title or "Transcripción").strip()[:MAX_CHARS_TITLE], size=14, lh=8)
    pdf.ln(3)

    if description:
        _pdf_multi_cell(pdf, family, description.strip(), size=10, lh=6)
        pdf.ln(2)
    if source:
        _pdf_multi_cell(pdf, family, source.strip(), size=9, lh=5)
        pdf.ln(4)
    elif description:
        pdf.ln(2)

    for block in re.split(r"\n{2,}", plain):
        block = block.strip()
        if not block:
            continue
        _pdf_multi_cell(pdf, family, block, size=11, lh=6)
        pdf.ln(4)

    try:
        pdf.output(str(path))
    except Exception as e:
        logger.exception("FPDF output failed: %s", e)
        raise RuntimeError(f"Error al guardar PDF: {e}") from e
    return path
