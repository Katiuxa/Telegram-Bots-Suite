#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"

echo ""
echo "  MetavideoToText_bot - lanzador Linux"
echo ""

if [ -f .bot.pid ]; then
  OLDPID="$(tr -d '\r\n' < .bot.pid)"
  if [ -n "$OLDPID" ] && kill -0 "$OLDPID" 2>/dev/null; then
    echo "[*] Deteniendo instancia anterior (PID $OLDPID)..."
    kill "$OLDPID" 2>/dev/null || true
    sleep 2
    kill -9 "$OLDPID" 2>/dev/null || true
  fi
  rm -f .bot.pid
fi

if [ ! -d .venv ]; then
  echo "[*] Creando entorno virtual..."
  python3 -m venv .venv
fi

. .venv/bin/activate
pip install -r requirements.txt -q

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[AVISO] FFmpeg no encontrado. sudo apt install -y ffmpeg"
fi

echo "[*] Arrancando bot (Ctrl+C para parar)..."
python run.py &
BPID=$!
echo "$BPID" > .bot.pid
wait "$BPID"
rm -f .bot.pid
