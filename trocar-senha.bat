@echo off
cd /d "%~dp0"
docker compose exec -u sentinela sentinela python -m sentinela passwd admin
pause
