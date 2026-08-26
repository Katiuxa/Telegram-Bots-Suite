@echo off
chcp 65001 >nul
title Meta Downloader - Bot Descargador
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creando entorno virtual...
  py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install -U pip -q
pip install -r requirements.txt -q
pip install -U curl-cffi httpx yt-dlp-ejs -q

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo [AVISO] FFmpeg no esta en PATH. YouTube largo necesita FFmpeg.
)

if not exist ".env" (
  echo Copia .env.example a .env y pon TELEGRAM_BOT_TOKEN
  pause
  exit /b 1
)

python BotDescargador.py
pause
