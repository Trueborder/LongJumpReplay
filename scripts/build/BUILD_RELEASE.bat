@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

set "PORTABLE_DIR=%CD%\release\LongJumpReplay"
set "RELEASE_DIR=%CD%\release"
set "LJR_NO_PAUSE=1"

echo ============================================================
echo   Long Jump Replay - release build
echo ============================================================
echo.

echo [1/2] Building and testing the current application folder...
call "%REPO_ROOT%\scripts\build\BUILD_PORTABLE.bat" --folder-only
if errorlevel 1 goto :fail

echo [2/2] Validating the release payload...
if not exist "%PORTABLE_DIR%\LongJumpReplay.exe" goto :missing_output
if not exist "%PORTABLE_DIR%\_internal" goto :missing_output
if not exist "%PORTABLE_DIR%\_internal\config.json" goto :missing_output
if not exist "%PORTABLE_DIR%\README.txt" goto :missing_output
if not exist "%PORTABLE_DIR%\SELF_TEST_FROZEN.txt" goto :missing_output

copy /y "%CD%\LICENSE.txt" "%PORTABLE_DIR%\LICENSE.txt" >nul || goto :fail
if not exist "%PORTABLE_DIR%\LICENSE.txt" goto :missing_output

echo.
echo ============================================================
echo   RELEASE BUILD COMPLETE
echo ============================================================
echo Release folder: %RELEASE_DIR%
echo Application:    %PORTABLE_DIR%
echo Launch:         %PORTABLE_DIR%\LongJumpReplay.exe
echo.
if /I not "%~1"=="--no-pause" pause
exit /b 0

:missing_output
echo.
echo BUILD FAILED: An expected portable release file was not created.
goto :end_fail

:fail
echo.
echo BUILD FAILED. Read the error above.

:end_fail
if /I not "%~1"=="--no-pause" pause
exit /b 1
