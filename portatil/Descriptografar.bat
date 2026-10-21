@echo off
chcp 65001 >nul
title Sentinela - Descriptografar
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist "%~dp0python\python.exe" (
  echo Pasta incompleta: falta "python\python.exe".
  echo Extraia o ZIP inteiro antes de abrir ^(botao direito no ZIP - Extrair Tudo^).
  pause & exit /b 1
)
rem Arraste copias (.sql.gz.enc) para cima deste arquivo: o .sql sai ao lado de cada uma.
rem Aberto sem arquivos, recupera a copia mais recente de cada banco.
"%~dp0python\python.exe" "%~dp0app\portatil.py" --decrypt %*
echo.
pause
