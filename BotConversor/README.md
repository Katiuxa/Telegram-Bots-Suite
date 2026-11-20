# TooEpub2PDF (Calibre)

Telegram bot that converts EPUB/PDF/MOBI/DOCX/ODT with **Calibre** (`ebook-convert`). Unit: `botconversor.service`.

## The problem and what was done

With the **8 GB MicroSD full**, there was no room for the working file. The emergency variant (`EpubPDFbot.py`) writes to **`/tmp` (tmpfs, so RAM)** and deletes the file in `finally`. On a 1 GB Pi 3B that avoids filling the disk, and it can also eat the memory: the file has to go as soon as the job ends.

The SD card is now **128 GB**. The bot in use is `BotConversor.py` (temp on disk, a progress bar that reads Calibre's `%`, and cancellation of the process). Conversion timeout: 600 s.

## Stack

Calibre (`ebook-convert`) · Python · pyTelegramBotAPI

## Run

```bash
sudo apt-get install -y calibre
export TELEGRAM_BOT_TOKEN=...
python3 BotConversor.py
```

## What it shows

Moving scratch space into RAM when the system volume is at 100%, and not leaving junk in tmpfs on a 1 GB machine.
