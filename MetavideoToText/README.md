# Meta Media to Text

Telegram bot: a link or a video/audio file becomes a transcript. It runs on the Raspberry Pi 3B (1 GB) as `metavideototext-bot.service`. Personal use, friends, and Instagram followers.

## The problem and what was done

1. **Groq quota.** A single model runs out. `bot/services/groq_router.py` orders models by quality and jumps to the next one on a 429 (cooldown). It prefers the keys and models that still have headroom, so the bot does not go silent.

2. **YouTube subtitles.** Sometimes they are missing or poor. Speaker diarization (who is talking) was not pursued inside the bot. The bot **polishes the text** with an LLM so it reads cleanly. Separating speakers is done **outside**, by passing the file to Gemini. Less logic on the Pi, less RAM, and fewer half-finished failures.

3. **Age-restricted video.** yt-dlp with browser-account cookies can open age-gated content. It was tried and then dropped: account-lock risk. On the Pi, `YTDLP_BROWSER` in `.env` is empty.

4. **Disk.** `temp/` is cleaned (`cleanup_temp`). This was critical with the 8 GB SD. The SD is now 128 GB, but 1 GB of RAM still limits ffmpeg (low thread count).

There is no local Whisper and no Ollama on this board.

## Stack

Python · python-telegram-bot · yt-dlp · ffmpeg · Groq Whisper · systemd

## Install (Pi)

```bash
sudo apt-get install -y ffmpeg python3-venv
cd /home/admin/MetavideoToText_bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # TELEGRAM_BOT_TOKEN, GROQ_API_KEY or GROQ_API_KEYS
```

Unit: `metavideototext-bot.service` (a copy is in this folder).

```bash
sudo systemctl enable --now metavideototext-bot
journalctl -u metavideototext-bot -f
```

Local tests (PC):

```bash
python -m pytest tests -q
```

## What it shows

API limits, not risking an account with cookies, keeping part of the work off the Pi (Gemini stays outside), and living with 1 GB.
