# MetaMailbox

Bot Telegram: crea y consulta buzones temporales (API mail.tm). Estado en SQLite (`correos_bot.db`).

## Problema y qué se hizo

Enviar **hacia Gmail** (y en general Google) **no funciona**: Google rechaza el origen (correo temporal / relay no autenticado como remitente Google). El resto de destinos, sin incidencia relevante.

mail.tm **no envía por su API**. El envío, si se usa, va por SMTP externo (Brevo u otro) en `smtp.env` — ver `smtp.env.example`. Las credenciales SMTP no van en el código.

## Stack

Python · pyTelegramBotAPI · SQLite · mail.tm REST · SMTP opcional

## Ejecución

```bash
cd meta-mailbox
python3 -m venv .venv
. .venv/bin/activate
pip install pyTelegramBotAPI requests
cp .env.example .env
# TELEGRAM_BOT_TOKEN=
python botmail.py
```

En la Pi: `botmail.service`.

## Qué demuestra

Leer un rechazo de correo (destino Gmail) y no pelearlo con hacks: es política del receptor, no un bug del bot.
