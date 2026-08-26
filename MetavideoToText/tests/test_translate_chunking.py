"""Regression: oversized ASR block must be split before Groq."""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bot.services.translate import _chunk_formatted_text, _split_oversized


def test_split_oversized_respects_max():
    text = ("palabra " * 800).strip()  # ~5600 chars
    parts = _split_oversized(text, 2000)
    assert len(parts) >= 2
    assert all(len(p) <= 2100 for p in parts)
    assert "".join(parts).replace(" ", "") == text.replace(" ", "")


def test_chunk_single_giant_paragraph():
    body = ("Esto es una frase larga de prueba. " * 400).strip()
    chunks = _chunk_formatted_text(body, 2500)
    assert len(chunks) >= 3
    assert all(len(c) <= 2600 for c in chunks)


if __name__ == "__main__":
    test_split_oversized_respects_max()
    test_chunk_single_giant_paragraph()
    print("ok")
