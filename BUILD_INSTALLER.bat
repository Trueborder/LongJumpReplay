@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay 2.3 Windows installer build ===
where python >nul 2>nul || goto :python_missing
python -c "import sys; assert sys.version_info >= (3, 12)" || goto :python_missing
python -m pip install -r requirements-build.txt || goto :fail
python -m pytest || goto :fail
python app.py --self-test --self-test-report SELF_TEST_SOURCE.txt || goto :fail

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
python -m PyInstaller --noconfirm --clean --onefile --noupx --windowed --name LongJumpReplay --icon assets\long_jump_replay.ico --version-file windows_version_info.txt --add-data "config.json;." --add-data "assets\long_jump_replay.ico;assets" --add-data "assets\long_jump_splash.png;assets" --hidden-import hid app.py || goto :fail

if not exist release mkdir release
copy /y dist\LongJumpReplay.exe release\LongJumpReplay.exe >nul || goto :fail
python -m PyInstaller --noconfirm --clean --onefile --windowed --uac-admin --name LongJumpReplay-Setup --icon assets\long_jump_replay.ico --add-binary "release\LongJumpReplay.exe;payload" --add-data "README_SHARE.txt;payload" --add-data "THIRD_PARTY_NOTICES.txt;payload" installer\setup.py || goto :fail
copy /y dist\LongJumpReplay-Setup.exe release\LongJumpReplay-Setup-2.3.exe >nul || goto :fail
release\LongJumpReplay-Setup-2.3.exe --self-test 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash 'release\LongJumpReplay-Setup-2.3.exe' -Algorithm SHA256).Hash; Set-Content -Path 'release\LongJumpReplay-Setup-2.3.exe.sha256' -Value ($h + '  LongJumpReplay-Setup-2.3.exe')" || goto :fail

echo BUILD COMPLETE: release\LongJumpReplay-Setup-2.3.exe
echo Hash:          release\LongJumpReplay-Setup-2.3.exe.sha256
exit /b 0

:python_missing
echo Python 3.12 and the Python Launcher are required.
exit /b 1
:fail
echo BUILD FAILED. Read the error above.
exit /b 1
