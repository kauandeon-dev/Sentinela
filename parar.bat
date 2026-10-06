@echo off
cd /d "%~dp0"
docker compose stop
echo Sentinela parado. As copias e configuracoes continuam nas pastas dados e backups.
pause
