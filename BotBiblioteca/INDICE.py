#!/usr/bin/env python3
"""Genera un índice comprimido de epubs (ruta relativa, título, autor)."""
from __future__ import annotations

import gzip
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("indice")

RUTA_BASE = Path(os.environ.get("RUTA_LIBROS", ""))
ARCHIVO_SALIDA = Path(os.environ.get("INDICE_SALIDA", ""))


def generar_indice(raiz: Path, salida: Path) -> int:
    if not raiz.exists():
        log.error("La ruta no existe: %s", raiz)
        return 1
    indice = []
    errores = 0
    for archivo_epub in raiz.rglob("*.epub"):
        try:
            indice.append(
                {
                    "t": archivo_epub.stem.replace("_", " "),
                    "a": archivo_epub.parent.name.replace("_", " "),
                    "p": archivo_epub.relative_to(raiz).as_posix(),
                }
            )
            if len(indice) % 1000 == 0:
                log.info("Indexados %s libros", len(indice))
        except OSError as exc:
            errores += 1
            log.warning("Omitido %s: %s", archivo_epub, exc)

    log.info("Escaneo fin: %s libros, %s errores", len(indice), errores)
    salida.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(indice, ensure_ascii=False, separators=(",", ":"))
    try:
        with gzip.open(salida, "wt", encoding="utf-8") as f:
            f.write(json_str)
    except OSError:
        log.exception("No se pudo escribir %s", salida)
        return 1
    log.info("Índice en %s", salida)
    return 0


if __name__ == "__main__":
    if not RUTA_BASE:
        log.error("Define RUTA_LIBROS")
        sys.exit(1)
    salida = ARCHIVO_SALIDA if str(ARCHIVO_SALIDA) else RUTA_BASE / "indice.json.gz"
    sys.exit(generar_indice(RUTA_BASE, salida))
