@echo off
setlocal
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

where py >nul 2>&1
if not errorlevel 1 (
    py -3.12 tools\license_generator.py
    exit /b %errorlevel%
)

if exist ".venv-build-9105\Scripts\python.exe" (
    ".venv-build-9105\Scripts\python.exe" tools\license_generator.py
    exit /b %errorlevel%
)

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" tools\license_generator.py
    exit /b %errorlevel%
)

python tools\license_generator.py
exit /b %errorlevel%
