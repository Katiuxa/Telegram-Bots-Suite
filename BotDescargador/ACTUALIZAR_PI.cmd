@echo off
chcp 65001 >nul
title Actualizar Bot Descargador en la Pi
cd /d "%~dp0"

call "%~dp0deploy\_ssh_env.cmd"
if errorlevel 1 pause & exit /b 1

echo === Subiendo Bot Descargador a la Pi (sin contraseña) ===
%SSH% "mkdir -p %PI_DIR%/deploy %PI_DIR%/temp"
%SSH% "test -f %PI_DIR%/BotDescargador.py && cp %PI_DIR%/BotDescargador.py %PI_DIR%/BotDescargador.py.bak || true"
%SCP% BotDescargador.py ytdlp_runner.py instagram_fallback.py job_control.py requirements.txt .env.example %PI_USER%@%PI_HOST%:%PI_DIR%/
%SCP% deploy\update_on_pi.sh deploy\botdescargador.service %PI_USER%@%PI_HOST%:%PI_DIR%/deploy/

echo === Actualizando en la Pi ===
%SSH% "sed -i 's/\r$//' %PI_DIR%/deploy/update_on_pi.sh && bash %PI_DIR%/deploy/update_on_pi.sh"
%SSH% "grep -q '.venv/bin/python' /etc/systemd/system/botdescargador.service 2>/dev/null || (sudo cp %PI_DIR%/deploy/botdescargador.service /etc/systemd/system/botdescargador.service && sudo systemctl daemon-reload)"

echo.
echo Listo. Prueba un enlace largo en Telegram.
pause
