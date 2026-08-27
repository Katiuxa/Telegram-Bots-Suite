# Biblioteca Secreta

Bot de Telegram para un catálogo **personal** de epubs en la Raspberry Pi. En el panel maestro de la Pi aparece como `BibliotecaSecreta` (`bot_ebooks.service`).

Los libros y `biblioteca.db` viven en el USB Kingston (`/media/admin/KINGSTON`). **No van en este repositorio.**

## Qué hace

1. El usuario escribe un **título** o un **autor**.
2. El bot consulta **SQLite** (`libros`: titulo, autor, ruta). La búsqueda es `LIKE` por palabras y luego se filtra en Python normalizando tildes.
3. Lista paginada (10 resultados) con botones de Telegram.
4. Al elegir un libro: ficha (título, autor, formato EPUB).
5. **Enviar EPUB:** abre el fichero en el USB y lo manda con `send_document`. Si la ruta del índice no existe en disco, responde error de USB (índice descuadrado).
6. **Sinopsis** opcional: Google Books API (solo metadatos públicos; si no hay resumen, lo dice).

`INDICE.py` puede generar un `indice.json.gz` auxiliar. `ajustar_biblioteca_usb.py` recorta la colección al espacio real del pendrive y regenera la base para que no queden rutas muertas.

## Problema y qué se hizo

La colección **pesaba más que el USB de 128 GB**. No cabía entera.

Se recortó el árbol de ficheros y se **regeneró SQLite** solo con lo que quedó. Si el índice apunta a un epub borrado, el bot no inventa el archivo: avisa de error físico en USB.

Con la MicroSD de 8 GB el sistema no podía hospedar esa biblioteca; los datos van al USB, no a la SD.

```bash
export USB_PATH=/media/admin/KINGSTON
python3 ajustar_biblioteca_usb.py --margen-mb 2048
python3 ajustar_biblioteca_usb.py --dry-run
```

## Stack

Python · SQLite · pyTelegramBotAPI · USB montado en Debian · systemd

## Ejecución

```bash
cp .env.example .env
# TELEGRAM_BOT_TOKEN, USB_PATH, DB_PATH, RUTA_LIBROS
python3 BotEbooks.py
```

Unidad: `bot_ebooks.service`. Comprobar `findmnt $USB_PATH` antes de arrancar.

## Qué demuestra

Índice coherente con el disco, consulta SQL en un volumen externo, y envío del fichero por Telegram solo si existe en el USB.
