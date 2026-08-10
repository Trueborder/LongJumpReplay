@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay 2.3 single EXE build ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install Python 3.12 x64 first.
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
python -m pytest || goto :fail
python app.py --self-test --self-test-report SELF_TEST_SOURCE.txt || goto :fail

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LongJumpReplay --icon assets\long_jump_replay.ico --version-file windows_version_info.txt --add-data "config.json;." --add-data "assets\long_jump_splash.png;assets" --hidden-import hid app.py || goto :fail

if not exist release mkdir release
copy /y dist\LongJumpReplay.exe release\LongJumpReplay-2.3.exe >nul
release\LongJumpReplay-2.3.exe --self-test --self-test-report release\SELF_TEST_SINGLE_EXE.txt
if errorlevel 1 goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash 'release\LongJumpReplay-2.3.exe' -Algorithm SHA256).Hash; Set-Content -Path 'release\LongJumpReplay-2.3.exe.sha256' -Value ($h + '  LongJumpReplay-2.3.exe')"

echo.
echo BUILD COMPLETE: release\LongJumpReplay-2.3.exe
echo Self-test:     release\SELF_TEST_SINGLE_EXE.txt
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
