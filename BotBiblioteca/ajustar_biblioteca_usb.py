#!/usr/bin/env python3
"""Ajusta una colección de epubs al espacio real de un USB y regenera SQLite.

Incidencia: el árbol de epubs pesaba más que el USB de 128 GB. Se fueron
eliminando ficheros al azar hasta caber, y a la vez se reconstruyó biblioteca.db
solo con los que quedaban. Si el índice apunta a un fichero borrado, el bot
responde error físico en USB.
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ajustar-usb")


def espacio_usb(path: Path) -> tuple[int, int]:
    st = os.statvfs(path)
    total = st.f_frsize * st.f_blocks
    libre = st.f_frsize * st.f_bavail
    return total, libre


def listar_epubs(raiz: Path) -> list[Path]:
    return [p for p in raiz.rglob("*.epub") if p.is_file()]


def borrar_hasta_caber(epubs: list[Path], raiz: Path, margen_bytes: int) -> list[Path]:
    """Borra al azar hasta que (tamaño de ficheros + margen) <= capacidad del USB."""
    random.shuffle(epubs)
    total, _libre = espacio_usb(raiz)
    techo = max(0, total - margen_bytes)
    ocupado = sum(p.stat().st_size for p in epubs)
    log.info("USB total=%s MiB  colección=%s MiB  techo=%s MiB", total // 1048576, ocupado // 1048576, techo // 1048576)

    borrados = 0
    while ocupado > techo and epubs:
        victima = epubs.pop()
        try:
            tam = victima.stat().st_size
            victima.unlink()
            ocupado -= tam
            borrados += 1
            if borrados % 50 == 0:
                log.info("Borrados %s ficheros; colección ahora %s MiB", borrados, ocupado // 1048576)
        except OSError as exc:
            log.warning("No se pudo borrar %s: %s", victima, exc)
    log.info("Fin recorte: %s borrados, %s epubs vivos, %s MiB", borrados, len(epubs), ocupado // 1048576)
    return epubs


def reconstruir_sqlite(epubs: list[Path], raiz: Path, db_path: Path) -> None:
    tmp = db_path.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(tmp)
    try:
        conn.execute(
            "CREATE TABLE libros (titulo TEXT, autor TEXT, ruta TEXT PRIMARY KEY)"
        )
        filas = []
        for p in epubs:
            try:
                rel = p.relative_to(raiz).as_posix()
            except ValueError:
                rel = str(p)
            filas.append((p.stem.replace("_", " "), p.parent.name.replace("_", " "), rel))
        conn.executemany("INSERT OR REPLACE INTO libros VALUES (?, ?, ?)", filas)
        conn.commit()
    except sqlite3.Error:
        log.exception("Fallo al escribir SQLite temporal")
        conn.close()
        if tmp.exists():
            tmp.unlink()
        raise
    conn.close()
    os.replace(tmp, db_path)
    log.info("SQLite regenerado en %s (%s filas)", db_path, len(epubs))


def main() -> int:
    parser = argparse.ArgumentParser(description="Recorta epubs al USB y regenera biblioteca.db")
    parser.add_argument("--usb", default=os.environ.get("USB_PATH", "/media/admin/KINGSTON"))
    parser.add_argument(
        "--libros",
        default=os.environ.get("RUTA_LIBROS", ""),
        help="Raíz de epubs. Por defecto: USB/Biblioteca Ebooks Espanol/biblioteca",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("DB_PATH", ""),
        help="Ruta de biblioteca.db. Por defecto: USB/biblioteca.db",
    )
    parser.add_argument("--margen-mb", type=int, default=2048, help="Espacio libre a reservar (MiB)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    usb = Path(args.usb)
    if not usb.is_dir():
        log.error("USB no montado: %s", usb)
        return 1
    raiz = Path(args.libros) if args.libros else usb / "Biblioteca Ebooks Espanol" / "biblioteca"
    db_path = Path(args.db) if args.db else usb / "biblioteca.db"
    if not raiz.is_dir():
        log.error("No existe el árbol de epubs: %s", raiz)
        return 1

    epubs = listar_epubs(raiz)
    log.info("Epubs encontrados: %s", len(epubs))
    if args.dry_run:
        total, libre = espacio_usb(usb)
        ocupado = sum(p.stat().st_size for p in epubs)
        log.info("dry-run total=%s libre=%s colección=%s", total, libre, ocupado)
        return 0

    vivos = borrar_hasta_caber(epubs, usb, args.margen_mb * 1048576)
    reconstruir_sqlite(vivos, raiz, db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
