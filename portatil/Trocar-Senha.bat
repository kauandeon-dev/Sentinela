@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0python\python.exe" "%~dp0app\portatil.py" --senha
pause
