@echo off
chcp 65001 >nul
title Sentinela - Encerrar
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist "%~dp0python\python.exe" (
  echo Pasta incompleta: falta "python\python.exe".
  echo Extraia o ZIP inteiro antes de abrir ^(botao direito no ZIP - Extrair Tudo^).
  pause & exit /b 1
)
"%~dp0python\python.exe" "%~dp0app\portatil.py" --parar
echo.
pause
