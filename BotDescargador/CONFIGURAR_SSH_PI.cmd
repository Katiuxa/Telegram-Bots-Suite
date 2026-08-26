@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === SSH sin contraseña (Pi: admin / 1234) ===
echo Solo UNA vez. La contraseña NO se guarda en ningun archivo del bot.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\setup_ssh_key.ps1" -PiPassword "1234"

echo.
pause
