# MetaMailbox

Telegram bot: creates and checks disposable inboxes (mail.tm API). State is stored in SQLite (`correos_bot.db`).

## The problem and what was done

Sending **to Gmail** (and to Google in general) **does not work**: Google rejects the origin (a disposable address / a relay that is not authenticated as a Google sender). Other destinations have no meaningful issue.

mail.tm **does not send through its API**. Sending, when it is used, goes through an external SMTP service (Brevo or another) in `smtp.env`. See `smtp.env.example`. SMTP credentials are not in the code.

## Stack

Python · pyTelegramBotAPI · SQLite · mail.tm REST · optional SMTP

## Run

```bash
cd meta-mailbox
python3 -m venv .venv
. .venv/bin/activate
pip install pyTelegramBotAPI requests
cp .env.example .env
# TELEGRAM_BOT_TOKEN=
python botmail.py
```

On the Pi: `botmail.service`.

## What it shows

Reading a mail rejection (Gmail as the destination) and not fighting it with hacks: it is the recipient's policy, not a bug in the bot.
