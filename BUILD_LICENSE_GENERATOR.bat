@echo off
setlocal
cd /d "%~dp0"

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
echo The EXE reads the private key from the project tools folder. Keep that file private.
exit /b 0

:fail
echo License generator build failed.
exit /b 1
