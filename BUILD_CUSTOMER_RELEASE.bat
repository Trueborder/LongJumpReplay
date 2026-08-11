@echo off
setlocal EnableExtensions
cd /d "%~dp0"

for /f "usebackq delims=" %%V in (`powershell.exe -NoProfile -File "%CD%\installer\get-version.ps1"`) do set "VERSION_FULL=%%V"
for /f "usebackq delims=" %%V in (`powershell.exe -NoProfile -File "%CD%\installer\get-version.ps1" -Label`) do set "VERSION_LABEL=%%V"

if not defined VERSION_FULL goto :fail_version
if not defined VERSION_LABEL goto :fail_version

set "CI=1"
set "SETUP_NAME=LongJumpReplay-Setup-%VERSION_LABEL%.exe"
set "RELEASE_DIR=%CD%\release"
set "STAGING_DIR=%CD%\build\customer-release"

echo ============================================================
echo   Long Jump Replay %VERSION_FULL% - complete customer release
echo ============================================================
echo.

echo [1/4] Building the native PowerShell/IExpress installer...
call "%CD%\BUILD_INSTALLER.bat"
if errorlevel 1 goto :fail
if not exist "%RELEASE_DIR%\%SETUP_NAME%" goto :missing_output

echo [2/4] Staging customer documentation...
if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%"
mkdir "%STAGING_DIR%" || goto :fail
copy /y "%RELEASE_DIR%\%SETUP_NAME%" "%STAGING_DIR%\%SETUP_NAME%" >nul || goto :fail

if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%" || goto :fail
mkdir "%RELEASE_DIR%" || goto :fail
mkdir "%RELEASE_DIR%\documentation" || goto :fail
copy /y "%STAGING_DIR%\%SETUP_NAME%" "%RELEASE_DIR%\%SETUP_NAME%" >nul || goto :fail
copy /y "%CD%\README.md" "%RELEASE_DIR%\documentation\README.md" >nul || goto :fail
copy /y "%CD%\README_CZ.md" "%RELEASE_DIR%\documentation\README_CZ.md" >nul || goto :fail
copy /y "%CD%\CHANGELOG_%VERSION_LABEL%.md" "%RELEASE_DIR%\documentation\CHANGELOG_%VERSION_LABEL%.md" >nul || goto :fail
copy /y "%CD%\LICENSE.txt" "%RELEASE_DIR%\documentation\LICENSE.txt" >nul || goto :fail
copy /y "%CD%\THIRD_PARTY_NOTICES.txt" "%RELEASE_DIR%\documentation\THIRD_PARTY_NOTICES.txt" >nul || goto :fail

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$h=(Get-FileHash -LiteralPath '%RELEASE_DIR%\%SETUP_NAME%' -Algorithm SHA256).Hash; Set-Content -LiteralPath '%RELEASE_DIR%\%SETUP_NAME%.sha256' -Encoding ascii -Value ($h + '  %SETUP_NAME%')" || goto :fail

echo [3/4] Building the deployable customer website...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CD%\website\BUILD_SITE.ps1" -Output "%RELEASE_DIR%\website" || goto :fail
if not exist "%RELEASE_DIR%\website\index.html" goto :missing_output
if not exist "%RELEASE_DIR%\website\downloads\%SETUP_NAME%" goto :missing_output

echo [4/4] Writing the release manifest and checksums...
(
  echo Long Jump Replay %VERSION_FULL% customer release
  echo.
  echo Customer installer:
  echo   %SETUP_NAME%
  echo.
  echo Deployable sales website:
  echo   website\index.html
  echo.
  echo Customer documentation:
  echo   documentation\
  echo.
  echo The private license key and owner-only tools are intentionally excluded.
) > "%RELEASE_DIR%\CUSTOMER_RELEASE.txt"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path -LiteralPath '%RELEASE_DIR%').Path; Get-ChildItem -LiteralPath $root -Recurse -File | Where-Object Name -ne 'SHA256SUMS.txt' | Sort-Object FullName | ForEach-Object { $relative=$_.FullName.Substring($root.Length + 1); $hash=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash; $hash + '  ' + $relative } | Set-Content -LiteralPath (Join-Path $root 'SHA256SUMS.txt') -Encoding ascii" || goto :fail

if exist "%RELEASE_DIR%\LongJumpReplay.exe" goto :fail
if exist "%RELEASE_DIR%\LongJumpReplay-License-Generator.exe" goto :fail

echo.
echo ============================================================
echo   CUSTOMER RELEASE COMPLETE
echo ============================================================
echo Installer: %RELEASE_DIR%\%SETUP_NAME%
echo Website:   %RELEASE_DIR%\website
echo Checksums: %RELEASE_DIR%\SHA256SUMS.txt
echo.
if /I not "%~1"=="--no-pause" pause
exit /b 0

:fail_version
echo BUILD FAILED: Could not read the current version from src\__init__.py.
goto :end_fail

:missing_output
echo BUILD FAILED: An expected customer-release file was not created.
goto :end_fail

:fail
echo BUILD FAILED. Read the error above.

:end_fail
if /I not "%~1"=="--no-pause" pause
exit /b 1
