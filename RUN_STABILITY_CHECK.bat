@echo off
setlocal
"%~dp0.venv\Scripts\python.exe" "%~dp0tools\soak_diagnostics.py" --seconds 30 --output "%~dp0stability-report.json"
if errorlevel 1 pause
