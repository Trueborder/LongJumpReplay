@echo off
setlocal
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

if not defined LONGJUMP_LICENSE_KEY_PATH set "LONGJUMP_LICENSE_KEY_PATH=%REPO_ROOT%\tools\.license_private_key.json"
if not exist "%LONGJUMP_LICENSE_KEY_PATH%" (
    echo Private signing key not found:
    echo   %LONGJUMP_LICENSE_KEY_PATH%
    echo This owner-only file is intentionally not stored in Git.
    exit /b 1
)

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
