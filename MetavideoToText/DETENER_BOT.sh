#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"

if [ -f .bot.pid ]; then
  PID="$(tr -d '\r\n' < .bot.pid)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    echo "[*] Deteniendo PID $PID..."
    kill "$PID" 2>/dev/null || true
    sleep 2
    kill -9 "$PID" 2>/dev/null || true
  fi
  rm -f .bot.pid
fi

pkill -f "MetavideoToText_bot.*run.py" 2>/dev/null || true
pkill -f "run.py" 2>/dev/null || true
echo "[*] Bot detenido."
