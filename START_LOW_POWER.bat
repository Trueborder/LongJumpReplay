@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Long Jump Replay is not installed yet.
  echo Run INSTALL_WINDOWS.bat first.
  pause
  exit /b 1
)
start "Long Jump Replay" ".venv\Scripts\pythonw.exe" app.py --low-power --windowed
