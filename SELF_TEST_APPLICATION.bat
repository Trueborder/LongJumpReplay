@echo off
cd /d "%~dp0"
LongJumpReplay.exe --self-test --self-test-report SELF_TEST_APPLICATION.txt
type SELF_TEST_APPLICATION.txt
pause
