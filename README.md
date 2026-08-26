# Telegram-Bots-Suite

Bots Python en una Raspberry Pi 3B (1 GB, Debian, systemd). Un repo: mismas dependencias base (Telegram, HTTP, `.env`, venv) y carpetas independientes.

Uso personal, amigos y seguidores de Instagram. No hay LLM local en la Pi.

## Carpetas

| Carpeta | Función |
|---|---|
| [MetavideoToText](MetavideoToText/) | Vídeo/audio → texto (yt-dlp, ffmpeg, Groq, pulido) |
| [BotMail](BotMail/) | Buzones temporales mail.tm + SQLite |
| [BotBiblioteca](BotBiblioteca/) | Catálogo SQLite de epubs en USB 128 GB |
| [OnlyNews](OnlyNews/) | Extrae artículo + fotos del HTML |
| [BotConversor](BotConversor/) | Calibre `ebook-convert` |
| [BotDescargador](BotDescargador/) | yt-dlp (TikTok, Reels, YouTube) |

Tokens en `.env` (cada carpeta tiene `.env.example`). Nada de claves en el código.

## Arranque (uno cualquiera)

```bash
cd MetavideoToText   # o BotMail, OnlyNews, ...
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
set -a; . ./.env; set +a
python bot/main.py   # o el .py de esa carpeta
```

En la Pi lo lanza systemd, no una sesión interactiva.

Home Lab: [debian-homelab](https://github.com/Katiuxa/debian-homelab).
