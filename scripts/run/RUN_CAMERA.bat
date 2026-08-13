@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"
if not exist .venv (echo Run scripts\setup\INSTALL_WINDOWS.bat first.& pause & exit /b 1)
call .venv\Scripts\activate.bat
python app.py --windowed
