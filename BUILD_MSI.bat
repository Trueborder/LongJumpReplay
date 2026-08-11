@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay 2.3 MSI build ===
where py >nul 2>nul || goto :python_missing
where wix >nul 2>nul || goto :wix_missing
if not exist .venv py -3.12 -m venv .venv || goto :fail
call .venv\Scripts\activate.bat || goto :fail
python -m pip install -r requirements-build.txt || goto :fail
python -m pytest || goto :fail
python app.py --self-test --self-test-report SELF_TEST_SOURCE.txt || goto :fail
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --clean --onefile --windowed --name LongJumpReplay --icon assets\long_jump_replay.ico --version-file windows_version_info.txt --add-data "config.json;." --add-data "assets\long_jump_replay.ico;assets" --add-data "assets\long_jump_splash.png;assets" --hidden-import hid app.py || goto :fail
if not exist release mkdir release
copy /y dist\LongJumpReplay.exe release\LongJumpReplay.exe >nul || goto :fail
wix build installer\LongJumpReplay.wxs -d BinDir="%CD%\release" -d ProjectDir="%CD%" -o release\LongJumpReplay-2.3.msi || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash 'release\LongJumpReplay-2.3.msi' -Algorithm SHA256).Hash; Set-Content -Path 'release\LongJumpReplay-2.3.msi.sha256' -Value ($h + '  LongJumpReplay-2.3.msi')" || goto :fail
echo BUILD COMPLETE: release\LongJumpReplay-2.3.msi
exit /b 0

:python_missing
echo Python 3.12 and the Python Launcher are required.
exit /b 1
:wix_missing
echo WiX Toolset 4 is required. Install wix.exe and put it on PATH.
exit /b 1
:fail
echo BUILD FAILED. Read the error above.
exit /b 1
