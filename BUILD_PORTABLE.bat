@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay 2.3 portable Windows build ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install Python 3.12 x64 from python.org.
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
python -m PyInstaller --noconfirm --clean LongJumpReplay.spec || goto :fail

dist\LongJumpReplay\LongJumpReplay.exe --self-test --self-test-report dist\LongJumpReplay\SELF_TEST_FROZEN.txt
if errorlevel 1 goto :fail

copy /y README_SHARE.txt dist\LongJumpReplay\README.txt >nul
copy /y START_SYNTHETIC.bat dist\LongJumpReplay\START_SYNTHETIC.bat >nul
copy /y SELF_TEST_APPLICATION.bat dist\LongJumpReplay\SELF_TEST_APPLICATION.bat >nul

if exist release rmdir /s /q release
mkdir release
xcopy /e /i /y dist\LongJumpReplay release\LongJumpReplay >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'release\LongJumpReplay\*' -DestinationPath 'release\LongJumpReplay-2.3-Windows-x64.zip' -Force"
if errorlevel 1 goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash 'release\LongJumpReplay-2.3-Windows-x64.zip' -Algorithm SHA256).Hash; Set-Content -Path 'release\LongJumpReplay-2.3-Windows-x64.zip.sha256' -Value ($h + '  LongJumpReplay-2.3-Windows-x64.zip')"

echo.
echo BUILD COMPLETE
echo Share: release\LongJumpReplay-2.3-Windows-x64.zip
echo Hash:  release\LongJumpReplay-2.3-Windows-x64.zip.sha256
echo The recipient only extracts the ZIP and runs LongJumpReplay.exe.
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above.
pause
exit /b 1
