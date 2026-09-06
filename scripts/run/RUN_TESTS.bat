@echo off
setlocal EnableExtensions
for %%I in ("%~dp0..\..") do set "REPO_ROOT=%%~fI"
cd /d "%REPO_ROOT%"

echo === Long Jump Replay source tests ===
python -m pytest --ignore-glob="*_gui.py" || goto :fail

for %%T in (tests\*_gui.py) do (
  echo.
  echo === GUI test group: %%T ===
  call :run_gui_group "%%T" || goto :fail
)

echo.
echo TESTS COMPLETE
exit /b 0

:run_gui_group
python -m pytest %1
if not errorlevel 1 exit /b 0
echo.
echo GUI group failed once; retrying in a fresh process: %~1
python -m pytest %1
exit /b %ERRORLEVEL%

:fail
echo.
echo TESTS FAILED. Read the error above.
exit /b 1
