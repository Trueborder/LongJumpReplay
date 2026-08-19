@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO_ROOT%\scripts\release\Publish-Release.ps1" %*
exit /b %ERRORLEVEL%
