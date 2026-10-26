@echo off
chcp 65001 >nul
title Sentinela
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist "%~dp0python\python.exe" (
  echo Pasta incompleta: falta "python\python.exe".
  echo Extraia o ZIP inteiro antes de abrir ^(botao direito no ZIP - Extrair Tudo^).
  pause & exit /b 1
)
"%~dp0python\python.exe" "%~dp0app\portatil.py" %*
rem 3 = roda em segundo plano (ja estava, ou acabou de passar): nada mais a fazer aqui
if %errorlevel%==3 (ping -n 5 127.0.0.1 >nul & exit /b 0)
echo.
echo Sentinela encerrado.
pause
