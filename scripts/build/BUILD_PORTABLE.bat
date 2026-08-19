@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

set "FOLDER_ONLY="
if /I "%~1"=="--folder-only" set "FOLDER_ONLY=1"

for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\build\Get-Version.ps1"`) do set "APP_VERSION=%%V"
if not defined APP_VERSION goto :fail

echo === Long Jump Replay %APP_VERSION% portable Windows build ===
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher was not found. Install Python 3.12 x64 from python.org.
  pause
  exit /b 1
)

set "VENV_DIR=.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>nul
  if errorlevel 1 (
    echo Existing .venv is stale. Leaving it untouched and creating a fresh environment.
    set "VENV_DIR=.venv-build-%RANDOM%"
    set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
  )
)

if not exist "%VENV_DIR%" (
  py -3.12 -m venv "%VENV_DIR%"
  if errorlevel 1 py -3 -m venv "%VENV_DIR%"
  if errorlevel 1 goto :fail
)

call "%VENV_DIR%\Scripts\activate.bat" || goto :fail
python -c "import sys; assert sys.version_info[:2] == (3, 12)" || goto :fail
python -m pip install --upgrade pip || goto :fail
python -m pip install -r requirements-build.txt || goto :fail
call "%REPO_ROOT%\scripts\run\RUN_TESTS.bat" || goto :fail
python app.py --self-test --self-test-report SELF_TEST_SOURCE.txt || goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\build\Write-VersionInfo.ps1" || goto :fail

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
python -m PyInstaller --noconfirm --clean packaging\LongJumpReplay.spec || goto :fail

dist\LongJumpReplay\LongJumpReplay.exe --self-test --self-test-report dist\LongJumpReplay\SELF_TEST_FROZEN.txt
if errorlevel 1 goto :fail

copy /y README.md dist\LongJumpReplay\README.txt >nul

if exist release rmdir /s /q release
mkdir release
xcopy /e /i /y dist\LongJumpReplay release\LongJumpReplay >nul
if not defined FOLDER_ONLY (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'release\LongJumpReplay\*' -DestinationPath 'release\LongJumpReplay-%APP_VERSION%-Windows-x64.zip' -Force"
  if errorlevel 1 goto :fail
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash 'release\LongJumpReplay-%APP_VERSION%-Windows-x64.zip' -Algorithm SHA256).Hash; Set-Content -Path 'release\LongJumpReplay-%APP_VERSION%-Windows-x64.zip.sha256' -Value ($h + '  LongJumpReplay-%APP_VERSION%-Windows-x64.zip')"
  if errorlevel 1 goto :fail
)

echo.
echo BUILD COMPLETE
if defined FOLDER_ONLY (
  echo Application: release\LongJumpReplay
  echo Launch:      release\LongJumpReplay\LongJumpReplay.exe
) else (
  echo Share: release\LongJumpReplay-%APP_VERSION%-Windows-x64.zip
  echo Hash:  release\LongJumpReplay-%APP_VERSION%-Windows-x64.zip.sha256
  echo The recipient only extracts the ZIP and runs LongJumpReplay.exe.
)
if not defined LJR_NO_PAUSE pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above.
if not defined LJR_NO_PAUSE pause
exit /b 1
