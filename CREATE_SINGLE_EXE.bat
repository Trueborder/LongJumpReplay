@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay - create single EXE ===

rem Prefer the project environment, then the Python launcher, then python on PATH.
set "PYTHON="
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; print(sys.version)" >nul 2>nul
  if not errorlevel 1 set "PYTHON=.venv\Scripts\python.exe"
)
if not defined PYTHON (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON=py -3.12"
)
if not defined PYTHON (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON goto :python_missing

if not exist ".venv\Scripts\python.exe" (
  echo Creating project virtual environment...
  %PYTHON% -m venv .venv || goto :fail
  set "PYTHON=.venv\Scripts\python.exe"
)

echo Installing build dependencies...
%PYTHON% -m pip install --upgrade pip || goto :fail
%PYTHON% -m pip install -r requirements-build.txt || goto :fail

echo Running source self-test...
%PYTHON% app.py --self-test --self-test-report SELF_TEST_SOURCE.txt || goto :fail

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building one-file Windows executable...
%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name LongJumpReplay --icon "%CD%\assets\long_jump_replay.ico" --version-file "%CD%\windows_version_info.txt" --add-data "%CD%\config.json;." --add-data "%CD%\assets\long_jump_replay.ico;assets" --add-data "%CD%\assets\long_jump_splash.png;assets" --hidden-import hid app.py || goto :fail

if not exist release mkdir release
copy /y "dist\LongJumpReplay.exe" "release\LongJumpReplay-3.1.exe" >nul || goto :fail

echo Running frozen self-test...
"release\LongJumpReplay-3.1.exe" --self-test --self-test-report "release\SELF_TEST_SINGLE_EXE.txt"
if errorlevel 1 goto :fail

powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash 'release\LongJumpReplay-3.1.exe' -Algorithm SHA256).Hash; Set-Content -Path 'release\LongJumpReplay-3.1.exe.sha256' -Value ($h + '  LongJumpReplay-3.1.exe')" || goto :fail

echo.
echo BUILD COMPLETE: release\LongJumpReplay-3.1.exe
echo Self-test:     release\SELF_TEST_SINGLE_EXE.txt
pause
exit /b 0

:python_missing
echo.
echo Python 3.12 was not found. Install Python 3.12 x64 with the launcher enabled,
echo then run this file again.
pause
exit /b 1

:fail
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
