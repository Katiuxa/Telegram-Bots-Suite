# Meta Media to Text

Bot Telegram: enlace o fichero de vídeo/audio → transcripción. Corre en la Raspberry Pi 3B (1 GB) como `metavideototext-bot.service`. Uso propio, amigos y seguidores de Instagram.

## Problema y qué se hizo

1. **Cuota Groq.** Un solo modelo se acaba. `bot/services/groq_router.py` ordena modelos por calidad y salta al siguiente en 429 (cooldown). Prioriza las claves/modelos que aún tienen margen para que el bot no se quede mudo.

2. **Subtítulos de YouTube.** A veces no vienen o vienen mal. No se insistió en diarización (quién habla). El bot **pulsa el texto** con LLM para que se lea; la separación de interlocutores se hace **fuera**, pasando el archivo a Gemini. Menos lógica en la Pi, menos RAM y menos fallos a medias.

3. **Vídeo +18.** yt-dlp con cookies de la cuenta del navegador abre contenido con edad. Se probó y se dejó: riesgo de bloqueo de cuenta. En `.env` `YTDLP_BROWSER` vacío en la Pi.

4. **Disco.** `temp/` se limpia (`cleanup_temp`). Con la SD de 8 GB esto era crítico; ahora la SD es 128 GB, pero 1 GB de RAM sigue limitando ffmpeg (hilos bajos).

No hay Whisper local ni Ollama en esta placa.

## Stack

Python · python-telegram-bot · yt-dlp · ffmpeg · Groq Whisper · systemd

## Instalación (Pi)

```bash
sudo apt-get install -y ffmpeg python3-venv
cd /home/admin/MetavideoToText_bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # TELEGRAM_BOT_TOKEN, GROQ_API_KEY o GROQ_API_KEYS
```

Unidad: `metavideototext-bot.service` (copia en esta carpeta).

```bash
sudo systemctl enable --now metavideototext-bot
journalctl -u metavideototext-bot -f
```

Tests locales (PC):

```bash
python -m pytest tests -q
```

## Qué demuestra

Límites de API, no reventar una cuenta con cookies, recortar alcance del bot (Gemini fuera), y vivir con 1 GB.
