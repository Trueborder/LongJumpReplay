@echo off
setlocal
set "DOTNET_EXE=%USERPROFILE%\.dotnet\dotnet.exe"
if not exist "%DOTNET_EXE%" set "DOTNET_EXE=dotnet"
"%DOTNET_EXE%" run --project "%~dp0native\LongJumpReplay.App\LongJumpReplay.App.csproj" -c Release
if errorlevel 1 pause
