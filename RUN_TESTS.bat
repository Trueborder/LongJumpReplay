@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo === Long Jump Replay source tests ===
python -m pytest --ignore-glob="*_gui.py" || goto :fail

for %%T in (tests\*_gui.py) do (
  echo.
  echo === GUI test group: %%T ===
  python -m pytest "%%T" || goto :fail
)

echo.
echo TESTS COMPLETE
exit /b 0

:fail
echo.
echo TESTS FAILED. Read the error above.
exit /b 1
