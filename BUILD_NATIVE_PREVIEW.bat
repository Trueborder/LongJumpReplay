@echo off
setlocal
set "DOTNET_EXE=%USERPROFILE%\.dotnet\dotnet.exe"
if not exist "%DOTNET_EXE%" set "DOTNET_EXE=dotnet"
set "OUTPUT=%~dp0release\LongJumpReplay-NativePreview-Windows-x64"
"%DOTNET_EXE%" publish "%~dp0native\LongJumpReplay.App\LongJumpReplay.App.csproj" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -o "%OUTPUT%"
if errorlevel 1 (
  echo Native preview build failed.
  pause
  exit /b 1
)
echo Built: %OUTPUT%\LongJumpReplay.App.exe
