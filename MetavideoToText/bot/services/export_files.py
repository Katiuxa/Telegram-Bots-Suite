import re
import textwrap
import unicodedata
from datetime import datetime
from pathlib import Path

from bot.config import ROOT, TEMP_DIR

# Fuentes Windows con soporte completo español (ñ, tildes)
_FONT_CANDIDATES = (
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path(r"C:\Windows\Fonts\segoeui.ttf"),
    Path(r"C:\Windows\Fonts\calibri.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ROOT / "fonts" / "DejaVuSans.ttf",
)


def _normalize_pdf_text(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "")
    return t.replace("\r", "").replace("\x00", "").strip()


def _pdf_multi_cell(pdf, family: str, text: str, *, size: int = 11, lh: float = 6) -> None:
    text = _normalize_pdf_text(text)
    if not text:
        return
    pdf.set_font(family, size=size)
    w = pdf.epw
    try:
        pdf.set_x(pdf.l_margin)
        pdf.multi_cell(w, lh, text)
    except Exception:
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                pdf.ln(lh)
                continue
            for chunk in textwrap.wrap(line, width=90) or [line]:
                try:
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(w, lh, chunk)
                except Exception:
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(w, lh, chunk[:120])


def _plain_for_file(text: str) -> str:
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    t = t.replace("───", "—")
    t = unicodedata.normalize("NFC", t)
    return t.strip()


def _resolve_unicode_font() -> Path | None:
    for p in _FONT_CANDIDATES:
        if p.is_file():
            return p
    return None


def write_txt(
    text: str,
    prefix: str = "transcripcion",
    *,
    title: str | None = None,
    description: str | None = None,
    source: str | None = None,
) -> Path:
    plain = _plain_for_file(text)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TEMP_DIR / f"{prefix}_{stamp}.txt"
    header_lines: list[str] = []
    if title:
        header_lines.append(title.strip())
    if description:
        header_lines.append(description.strip())
    if source:
        header_lines.append(source.strip())
    if header_lines:
        header_lines.append("—" * 40)
        plain = "\n".join(header_lines) + "\n\n" + plain
    path.write_text(plain, encoding="utf-8-sig", newline="\n")
    return path


def write_pdf(
    text: str,
    prefix: str = "transcripcion",
    *,
    title: str | None = None,
    description: str | None = None,
    source: str | None = None,
) -> Path:
    from fpdf import FPDF

    plain = _plain_for_file(text)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = TEMP_DIR / f"{prefix}_{stamp}.pdf"
    font_path = _resolve_unicode_font()
    if not font_path:
        raise RuntimeError(
            "No encontré fuente Arial/DejaVu para PDF con tildes. Usa TXT."
        )

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    family = "UniFont"
    pdf.add_font(family, "", str(font_path))
    pdf.set_font(family, size=11)

    if title:
        pdf.set_font(family, size=14)
        _pdf_multi_cell(pdf, family, title.strip(), size=14, lh=8)
        pdf.ln(3)
        pdf.set_font(family, size=11)
    if description:
        _pdf_multi_cell(pdf, family, description.strip(), size=10, lh=6)
        pdf.ln(2)
    if source:
        _pdf_multi_cell(pdf, family, source.strip(), size=9, lh=5)
        pdf.ln(4)

    for block in re.split(r"\n{2,}", plain):
        block = block.strip()
        if not block:
            continue
        _pdf_multi_cell(pdf, family, block, size=11, lh=6)
        pdf.ln(4)

    pdf.output(str(path))
    return path
