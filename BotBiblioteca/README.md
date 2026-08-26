# MetaBiblioteca

Catálogo Telegram sobre epubs en un USB Kingston de 128 GB montado en la Pi (`/media/admin/KINGSTON`). Índice en SQLite (`biblioteca.db`). Búsqueda por título/autor (LIKE + normalización de tildes).

## Problema y qué se hizo

La colección **pesaba más que el USB**. No cabía entera.

Se **borraron libros al azar** hasta entrar en 128 GB. Mientras se borraba, se **regeneraba la base**: las filas de los ficheros eliminados desaparecían. Si el índice y el disco se descuadran, el bot responde error físico en USB.

Con MicroSD de 8 GB el sistema no podía hospedar esa biblioteca; los datos van al USB, no a la SD.

```bash
# recorte + SQLite nuevo (en la Pi, USB montado)
export USB_PATH=/media/admin/KINGSTON
python3 ajustar_biblioteca_usb.py --margen-mb 2048
# simulación:
python3 ajustar_biblioteca_usb.py --dry-run
```

`INDICE.py` genera un `indice.json.gz` auxiliar (rutas relativas POSIX) si hace falta un listado compacto.

## Stack

Python · SQLite · pyTelegramBotAPI · USB ext4/exFAT según formato del pendrive

## Ejecución

```bash
cp .env.example .env
# TELEGRAM_BOT_TOKEN, USB_PATH, DB_PATH, RUTA_LIBROS
python3 BotEbooks.py
```

Unidad: `bot_ebooks.service`. Comprobar `findmnt $USB_PATH` antes de arrancar.

## Qué demuestra

Capacidad real vs árbol de ficheros, índice coherente con el disco, y no dejar un SQLite que apunta a rutas muertas.
