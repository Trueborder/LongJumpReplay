# Windows + Codex setup

This guide moves the project to your Windows Documents folder, prepares Python, Git, and Codex, verifies the code, and starts an interactive Codex session in the correct directory.

## Recommended final location

```text
C:\Users\YOUR_NAME\Documents\LongJumpReplay
```

Do not develop inside Downloads or inside the ZIP. Extract first, then use the transfer script.

## 1. Extract the handoff ZIP

1. Download `LongJumpReplay_2.3_Codex_Handoff.zip`.
2. Right-click it and choose **Extract All**.
3. Open the extracted folder.
4. Right-click `TRANSFER_TO_DOCUMENTS.ps1` and choose **Run with PowerShell**.

If PowerShell blocks the script, open PowerShell in the extracted folder and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\TRANSFER_TO_DOCUMENTS.ps1
```

The script copies source files to `Documents\LongJumpReplay` while excluding `.venv`, caches, build output, and generated media. If a destination already exists, it offers to create a timestamped backup.

## 2. Install required tools

### Python

Install **Python 3.12 x64** from python.org and enable the Python Launcher. Verify:

```powershell
py -3.12 --version
```

### Git

Install Git for Windows. Verify:

```powershell
git --version
```

### Codex CLI

Official Windows installer command:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"
```

Then open a new terminal and verify:

```powershell
codex --version
```

Alternatively, when Node.js/npm is already installed:

```powershell
npm install -g @openai/codex
```

Run `codex` and choose **Sign in with ChatGPT**.

## 3. Prepare the development environment

Open PowerShell and run:

```powershell
cd "$HOME\Documents\LongJumpReplay"
Set-ExecutionPolicy -Scope Process Bypass
.\SETUP_DEVELOPMENT.ps1
```

The script:

- creates `.venv` using Python 3.12;
- installs runtime and build/test dependencies;
- runs the full test suite;
- runs the synthetic pipeline self-test;
- optionally initializes a Git repository.

## 4. Start and inspect the app

Synthetic camera:

```powershell
cd "$HOME\Documents\LongJumpReplay"
.\.venv\Scripts\Activate.ps1
python app.py --synthetic --windowed
```

Webcam:

```powershell
python app.py --windowed
```

Tests:

```powershell
python -m pytest
python app.py --self-test
```

## 5. Start Codex in the project

```powershell
cd "$HOME\Documents\LongJumpReplay"
.\START_CODEX.ps1
```

Or manually:

```powershell
codex
```

Paste the prompt from `CODEX_FIRST_PROMPT.md` for the first session.

## 6. Recommended Git workflow

Before each feature:

```powershell
git status
git switch -c feature/short-name
```

After Codex changes files:

```powershell
git diff
.\RUN_DEVELOPMENT_CHECKS.ps1
git add -A
git commit -m "Describe the tested change"
```

Create a separate branch for each meaningful feature or bug fix. Do not let a long Codex session mix unrelated changes.

## 7. Build a shareable Windows application

```powershell
.\BUILD_PORTABLE.bat
```

Expected output:

```text
release\LongJumpReplay-2.3-Windows-x64.zip
```

The portable folder build is recommended. Test it from a clean extracted folder before sharing.

## 8. Backups

Before large refactors:

```powershell
.\CREATE_PROJECT_BACKUP.ps1
```

Backups are placed next to the project under:

```text
Documents\LongJumpReplay_Backups
```

The script excludes `.venv`, temporary video cache, exports, evidence, build, dist, and release artifacts unless you deliberately archive those separately.
