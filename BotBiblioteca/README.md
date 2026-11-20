# Biblioteca Secreta

Telegram bot for a **personal** EPUB catalog on the Raspberry Pi. On the Pi's master panel it shows up as `BibliotecaSecreta` (`bot_ebooks.service`).

The books and `biblioteca.db` live on the Kingston USB drive (`/media/admin/KINGSTON`). **They are not in this repository.**

## What it does

1. The user types a **title** or an **author**.
2. The bot queries **SQLite** (`libros`: titulo, autor, ruta). The search is a `LIKE` by words, then Python filters the hits while normalizing accents.
3. A paged list (10 results) uses Telegram buttons.
4. Choosing a book shows a card (title, author, EPUB format).
5. **Send EPUB:** opens the file on the USB drive and sends it with `send_document`. If the indexed path is not on disk, it replies with a USB error (the index is out of date).
6. Optional **synopsis:** Google Books API (public metadata only; if there is no summary, it says so).

`INDICE.py` can build an extra `indice.json.gz`. `ajustar_biblioteca_usb.py` trims the collection to the real space on the drive and rebuilds the database so dead paths do not remain.

## The problem and what was done

The collection **weighed more than the 128 GB USB drive**. It did not fit whole.

The file tree was trimmed and **SQLite was rebuilt** with only what remained. If the index points at a deleted EPUB, the bot does not invent the file: it reports a physical error on the USB drive.

With the 8 GB MicroSD the system could not host that library. The data stays on the USB drive, not on the SD card.

```bash
export USB_PATH=/media/admin/KINGSTON
python3 ajustar_biblioteca_usb.py --margen-mb 2048
python3 ajustar_biblioteca_usb.py --dry-run
```

## Stack

Python · SQLite · pyTelegramBotAPI · USB drive mounted on Debian · systemd

## Run

```bash
cp .env.example .env
# TELEGRAM_BOT_TOKEN, USB_PATH, DB_PATH, RUTA_LIBROS
python3 BotEbooks.py
```

Unit: `bot_ebooks.service`. Check `findmnt $USB_PATH` before starting it.

## What it shows

An index that matches the disk, SQL queries on an external volume, and a Telegram file send only when the file exists on the USB drive.
