@echo off
chcp 65001 >nul
title Reiniciar Bot Descargador en la Pi
cd /d "%~dp0"

call "%~dp0deploy\_ssh_env.cmd"
if errorlevel 1 pause & exit /b 1

echo === Reiniciando botdescargador.service ===
%SSH% "sudo systemctl restart botdescargador.service && sleep 2 && systemctl is-active botdescargador.service"

echo.
pause
