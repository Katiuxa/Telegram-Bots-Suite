# TooEpub2PDF (Calibre)

Bot Telegram que convierte EPUB/PDF/MOBI/DOCX/ODT con **Calibre** (`ebook-convert`). Unidad `botconversor.service`.

## Problema y qué se hizo

Con la **MicroSD de 8 GB llena**, no había sitio para el fichero de trabajo. La variante de emergencia (`EpubPDFbot.py`) escribe en **`/tmp` (tmpfs = RAM)** y borra en el `finally`. En una Pi 3B de 1 GB eso evita tumbar el disco y a la vez puede comerse la memoria: hay que borrar en cuanto termina.

Hoy la SD es de **128 GB**. El bot que se usa es `BotConversor.py` (temp en disco, barra de progreso leyendo el `%` de Calibre, cancelación del proceso). Timeout de conversión 600 s.

## Stack

Calibre (`ebook-convert`) · Python · pyTelegramBotAPI

## Ejecución

```bash
sudo apt-get install -y calibre
export TELEGRAM_BOT_TOKEN=...
python3 BotConversor.py
```

## Qué demuestra

Mover el scratch a RAM cuando el volumen de sistema está al 100 %, y no dejar basura en tmpfs en un equipo de 1 GB.
