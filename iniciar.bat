@echo off
chcp 65001 >nul
title Sentinela
cd /d "%~dp0"
echo.
echo  === Sentinela - Backup Automatizado ===
echo.
where docker >nul 2>nul
if errorlevel 1 (
  echo  O Docker nao foi encontrado.
  echo  Instale o Docker Desktop: https://www.docker.com/products/docker-desktop/
  echo  Depois abra o Docker Desktop e rode este arquivo de novo.
  pause & exit /b 1
)
docker info >nul 2>nul
if errorlevel 1 (
  echo  O Docker Desktop esta instalado, mas nao esta aberto.
  echo  Abra o Docker Desktop, espere ficar "running" e rode este arquivo de novo.
  pause & exit /b 1
)
if not exist dados mkdir dados
if not exist backups mkdir backups
if not exist externo mkdir externo
echo  Preparando e iniciando (a primeira vez demora alguns minutos)...
docker compose up -d --build
if errorlevel 1 ( echo. & echo  Falha ao iniciar. Veja a mensagem acima. & pause & exit /b 1 )
echo  Aguardando o painel...
for /l %%i in (1,1,60) do (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8080/api/me -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul && goto pronto
  timeout /t 2 >nul
)
:pronto
echo.
docker compose logs sentinela 2>nul | findstr /c:"Primeiro acesso"
echo.
echo  Painel: http://localhost:8080   (usuario: admin)
echo  Se a senha nao apareceu acima, use a que voce ja definiu.
echo  Parar: parar.bat      Trocar senha: trocar-senha.bat
start "" http://localhost:8080
pause
