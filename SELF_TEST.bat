@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python -m pytest
python app.py --self-test
pause
