@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat || goto :fail
call RUN_TESTS.bat || goto :fail
python app.py --self-test || goto :fail
pause
exit /b 0

:fail
echo Tests or self-test failed. Read the error above.
pause
exit /b 1
