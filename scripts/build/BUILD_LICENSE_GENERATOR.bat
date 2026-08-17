@echo off
setlocal
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

if not defined LONGJUMP_LICENSE_KEY_PATH set "LONGJUMP_LICENSE_KEY_PATH=%REPO_ROOT%\tools\.license_private_key.json"
set "LICENSE_KEY=%LONGJUMP_LICENSE_KEY_PATH%"
if not exist "%LICENSE_KEY%" (
    echo Private signing key not found:
    echo   %LICENSE_KEY%
    echo Restore the owner-only key file or set LONGJUMP_LICENSE_KEY_PATH.
    goto :fail
)

set "PYTHON="
if exist ".venv-build-9105\Scripts\python.exe" set "PYTHON=.venv-build-9105\Scripts\python.exe"
if not defined PYTHON if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
if not defined PYTHON (
    where py >nul 2>&1
    if not errorlevel 1 set "PYTHON=py -3.12"
)
if not defined PYTHON set "PYTHON=python"

%PYTHON% -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name LongJumpReplay-License-Generator ^
    --distpath release --workpath build\LongJumpReplay-License-Generator ^
    --specpath build\generated tools\license_generator.py
if errorlevel 1 goto :fail

echo.
echo Built admin-only license generator:
echo   release\LongJumpReplay-License-Generator\LongJumpReplay-License-Generator.exe
echo Keep the private key in the owner-only tools folder. The EXE must run with
echo LONGJUMP_LICENSE_KEY_PATH set when it is moved outside this repository.
set "EXITCODE=0"
goto :done

:fail
echo License generator build failed.
set "EXITCODE=1"
goto :done

:done
if not "%LONGJUMP_NO_PAUSE%"=="1" (
    echo.
    pause
)
exit /b %EXITCODE%
