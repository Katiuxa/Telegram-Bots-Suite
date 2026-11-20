# Telegram-Bots-Suite

Python bots on a Raspberry Pi 3B (1 GB, Debian, systemd). One repo: shared base dependencies (Telegram, HTTP, `.env`, venv) and independent folders.

Personal use, friends, and Instagram followers. There is no local LLM on the Pi.

## Folders

| Folder | Role |
|---|---|
| [MetavideoToText](MetavideoToText/) | Video/audio to text (yt-dlp, ffmpeg, Groq, polish) |
| [BotMail](BotMail/) | Disposable mail.tm inboxes plus SQLite |
| [BotBiblioteca](BotBiblioteca/) | Biblioteca Secreta: SQLite search by title or author, then sends the EPUB from the USB drive |
| [OnlyNews](OnlyNews/) | Extracts the article text and photos from the HTML |
| [BotConversor](BotConversor/) | Calibre `ebook-convert` |
| [BotDescargador](BotDescargador/) | yt-dlp (TikTok, Reels, YouTube) |

Tokens live in `.env` (each folder has `.env.example`). No keys in the code.

## Start (any one bot)

```bash
cd MetavideoToText   # or BotMail, OnlyNews, ...
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
set -a; . ./.env; set +a
python bot/main.py   # or the .py file in that folder
```

On the Pi, systemd starts them. They do not run from an interactive session.

Home lab: [debian-homelab](https://github.com/Katiuxa/debian-homelab).
