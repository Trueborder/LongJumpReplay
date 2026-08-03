# Upgrade to Long Jump Replay 2.3

1. Extract the 2.3 project to a new folder.
2. Keep the old folder until the new build has been tested with your camera.
3. To reuse settings, copy the old `config.json` beside the 2.3 application. Missing 2.3 fields are added automatically.
4. Run `SELF_TEST.bat` and then `RUN_SYNTHETIC.bat`.
5. Open Settings and verify:
   - Competition → enabled/disabled mode
   - Attempts & decisions → Require a decision before continuing
   - Performance → desired preset
   - Camera and Board calibration
6. Build a shareable Windows package with `BUILD_PORTABLE.bat`.
7. Share `release\LongJumpReplay-2.3-Windows-x64.zip`.

The old cache is compatible where metadata is valid, but starting a new competition with a clean temporary cache is recommended.
