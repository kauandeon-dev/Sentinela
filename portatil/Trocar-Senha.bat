@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
"%~dp0python\python.exe" "%~dp0app\portatil.py" --senha
pause
