@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.12 x64 from python.org first.
  pause
  exit /b 1
)
if not exist .venv (
  py -3.12 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
  if errorlevel 1 goto :fail
)
call .venv\Scripts\activate.bat || goto :fail
python -m pip install --upgrade pip || goto :fail
python -m pip install -r requirements-build.txt || goto :fail
call "%CD%\RUN_TESTS.bat" || goto :fail
python app.py --self-test || goto :fail
echo.
echo Installation and tests completed successfully.
pause
exit /b 0
:fail
echo Installation or test failed. Read the error above.
pause
exit /b 1
