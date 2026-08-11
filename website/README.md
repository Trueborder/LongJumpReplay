# LongJumpReplay website

This is a dependency-free static sales site for LongJumpReplay.

1. Edit `site.config.js` to change the contact email, domain, price, or installer URL.
2. Build the Windows installer with `..\BUILD_INSTALLER.bat`.
3. Run `.\BUILD_SITE.ps1` from this directory.
4. Upload the generated `dist` directory to any static host.

The public download is the Windows setup EXE only. The installer is expected at
`dist\downloads\LongJumpReplay-Setup-2.3.exe` after a successful installer build.
