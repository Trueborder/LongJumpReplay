@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PORTABLE_DIR=%CD%\release\LongJumpReplay"
set "FINAL_DIR=%CD%\ProductFinal"
set "STAGING_DIR=%CD%\build\ProductFinal-next"
set "BACKUP_DIR=%CD%\build\ProductFinal-backup"
set "LJR_NO_PAUSE=1"

echo ============================================================
echo   Long Jump Replay - ProductFinal release build
echo ============================================================
echo.

echo [1/3] Building and testing the current portable application...
call "%CD%\BUILD_PORTABLE.bat"
if errorlevel 1 goto :fail

echo [2/3] Staging the verified ProductFinal payload...
if not exist "%PORTABLE_DIR%\LongJumpReplay.exe" goto :missing_output
if not exist "%PORTABLE_DIR%\_internal" goto :missing_output
if not exist "%PORTABLE_DIR%\README.txt" goto :missing_output
if not exist "%PORTABLE_DIR%\SELF_TEST_FROZEN.txt" goto :missing_output

if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%"
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
mkdir "%STAGING_DIR%" || goto :fail

robocopy "%PORTABLE_DIR%" "%STAGING_DIR%" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :fail
copy /y "%CD%\LICENSE.txt" "%STAGING_DIR%\LICENSE.txt" >nul || goto :fail

if not exist "%STAGING_DIR%\LongJumpReplay.exe" goto :missing_output
if not exist "%STAGING_DIR%\_internal\config.json" goto :missing_output
if not exist "%STAGING_DIR%\LICENSE.txt" goto :missing_output

echo [3/3] Replacing ProductFinal with the new verified payload...
if exist "%FINAL_DIR%" (
  move "%FINAL_DIR%" "%BACKUP_DIR%" >nul || goto :swap_fail
)
move "%STAGING_DIR%" "%FINAL_DIR%" >nul || goto :restore_backup
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"

echo.
echo ============================================================
echo   RELEASE BUILD COMPLETE
echo ============================================================
echo Final product: %FINAL_DIR%
echo Launch:        %FINAL_DIR%\LongJumpReplay.exe
echo.
if /I not "%~1"=="--no-pause" pause
exit /b 0

:restore_backup
if exist "%BACKUP_DIR%" move "%BACKUP_DIR%" "%FINAL_DIR%" >nul
goto :swap_fail

:missing_output
echo.
echo BUILD FAILED: An expected portable release file was not created.
goto :end_fail

:swap_fail
echo.
echo BUILD FAILED: ProductFinal could not be replaced. Close any running copy and try again.
goto :end_fail

:fail
echo.
echo BUILD FAILED. The existing ProductFinal folder was not replaced.

:end_fail
if /I not "%~1"=="--no-pause" pause
exit /b 1
