@echo off
chcp 65001 >nul
title Instalar servicio Bot Descargador en la Pi
cd /d "%~dp0"
call "%~dp0deploy\_ssh_env.cmd"
if errorlevel 1 pause & exit /b 1

echo Copiando unit systemd...
%SCP% deploy\botdescargador.service %PI_USER%@%PI_HOST%:/tmp/botdescargador.service
%SSH% "sudo cp /tmp/botdescargador.service /etc/systemd/system/botdescargador.service && sudo systemctl daemon-reload && sudo systemctl enable botdescargador.service"
echo Listo. Ejecuta ACTUALIZAR_PI.cmd
pause
