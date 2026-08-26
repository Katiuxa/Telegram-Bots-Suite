"""Fecha/hora de la última actualización desplegada (BOT_VERSION.txt)."""

from datetime import datetime, timezone
from pathlib import Path

from bot.config import ROOT

VERSION_FILE = ROOT / "BOT_VERSION.txt"


def stamp_build_version() -> str:
    """Escribe marca de tiempo local (al actualizar o lanzar)."""
    text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    VERSION_FILE.write_text(text + "\n", encoding="utf-8")
    return text


def get_build_version() -> str:
    if VERSION_FILE.is_file():
        line = VERSION_FILE.read_text(encoding="utf-8").strip().splitlines()
        if line:
            return line[0]
    return "desarrollo (sin desplegar)"


def get_build_version_utc() -> str:
    """Solo si hace falta comparar entre PC y Pi."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
