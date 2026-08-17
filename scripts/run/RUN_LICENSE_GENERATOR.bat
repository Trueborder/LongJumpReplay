@echo off
setlocal
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

if not defined LONGJUMP_LICENSE_KEY_PATH set "LONGJUMP_LICENSE_KEY_PATH=%REPO_ROOT%\tools\.license_private_key.json"
if not exist "%LONGJUMP_LICENSE_KEY_PATH%" (
    echo Private signing key not found:
    echo   %LONGJUMP_LICENSE_KEY_PATH%
    echo This owner-only file is intentionally not stored in Git.
    echo Restore it from your offline backup, or point LONGJUMP_LICENSE_KEY_PATH
    echo at its current location, then run this script again.
    set "EXITCODE=1"
    goto :done
)

set "PYTHON="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON=py -3.12"
if not defined PYTHON if exist ".venv-build-9105\Scripts\python.exe" set "PYTHON=.venv-build-9105\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python"

%PYTHON% tools\license_generator.py
set "EXITCODE=%errorlevel%"
if not "%EXITCODE%"=="0" (
    echo.
    echo License generator exited with code %EXITCODE%.
)

:done
if not "%LONGJUMP_NO_PAUSE%"=="1" (
    echo.
    pause
)
exit /b %EXITCODE%
