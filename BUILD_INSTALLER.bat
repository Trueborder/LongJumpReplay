@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay native installer build ===

echo.
echo [1/2] Building a fresh portable payload...
set "LJR_NO_PAUSE=1"
call "%~dp0BUILD_PORTABLE.bat"
if errorlevel 1 goto :fail

echo.
echo [2/2] Creating the self-extracting installer with Windows IExpress...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\build-iexpress.ps1" -ProjectRoot "%CD%"
if errorlevel 1 goto :fail

echo.
echo BUILD COMPLETE: see the versioned installer in release\
if not defined CI pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Read the error above.
if not defined CI pause
exit /b 1
