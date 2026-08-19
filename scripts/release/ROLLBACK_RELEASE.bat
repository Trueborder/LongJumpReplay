@echo off
setlocal EnableExtensions
if "%~1"=="" (
  echo Usage: ROLLBACK_RELEASE.bat 3.3.0
  exit /b 2
)
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\release\Rollback-Release.ps1" -Version "%~1"
exit /b %ERRORLEVEL%
