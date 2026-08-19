@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

for /f "usebackq delims=" %%V in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\build\Get-Version.ps1"`) do set "APP_VERSION=%%V"
if not defined APP_VERSION goto :fail

echo ============================================================
echo   LongJumpReplay %APP_VERSION% customer installer
echo ============================================================

set "LJR_NO_PAUSE=1"
call "%REPO_ROOT%\scripts\build\BUILD_RELEASE.bat" --no-pause
if errorlevel 1 goto :fail

set "ISCC="
if defined INNO_SETUP_HOME if exist "%INNO_SETUP_HOME%\ISCC.exe" set "ISCC=%INNO_SETUP_HOME%\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php
  echo or set INNO_SETUP_HOME to the folder containing ISCC.exe.
  goto :fail
)

"%ISCC%" /Qp "/DMyAppVersion=%APP_VERSION%" "/DSourceDir=%REPO_ROOT%\release\LongJumpReplay" "/DReleaseDir=%REPO_ROOT%\release" "/DRepoRoot=%REPO_ROOT%" "%REPO_ROOT%\packaging\LongJumpReplay.iss"
if errorlevel 1 goto :fail

set "INSTALLER=%REPO_ROOT%\release\LongJumpReplay-Setup-%APP_VERSION%.exe"
if not exist "%INSTALLER%" goto :fail
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -LiteralPath '%INSTALLER%' -Algorithm SHA256).Hash; Set-Content -LiteralPath '%INSTALLER%.sha256' -Value ($h + '  LongJumpReplay-Setup-%APP_VERSION%.exe') -Encoding ASCII"
if errorlevel 1 goto :fail

echo.
echo Installer: %INSTALLER%
echo Hash:      %INSTALLER%.sha256
if /I not "%~1"=="--no-pause" pause
exit /b 0

:fail
echo.
echo INSTALLER BUILD FAILED. Read the error above.
if /I not "%~1"=="--no-pause" pause
exit /b 1
