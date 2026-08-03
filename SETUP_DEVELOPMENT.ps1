[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipGit
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Require-Command([string]$Name, [string]$Message) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw $Message
    }
}

Require-Command 'py' 'Python Launcher was not found. Install Python 3.12 x64 from python.org.'

Write-Host "Creating Python 3.12 environment..." -ForegroundColor Cyan
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv with Python 3.12.' }
}

$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $Python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

if (-not $SkipTests) {
    Write-Host "Running tests..." -ForegroundColor Cyan
    & $Python -m pytest
    if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }

    Write-Host "Running synthetic self-test..." -ForegroundColor Cyan
    & $Python app.py --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Application self-test failed.' }
}

if (-not $SkipGit) {
    if (Get-Command git -ErrorAction SilentlyContinue) {
        if (-not (Test-Path '.git')) {
            git init | Out-Host
            git branch -M main 2>$null
            Write-Host "Git repository initialized. Review files, then create the first commit." -ForegroundColor Green
            Write-Host "  git add -A"
            Write-Host "  git commit -m `"Initial Long Jump Replay 2.3 Codex handoff`""
        } else {
            Write-Host "Existing Git repository detected." -ForegroundColor Green
        }
    } else {
        Write-Host "Git is not installed. Install Git for Windows before serious development." -ForegroundColor Yellow
    }
}

Write-Host "" 
Write-Host "Development setup completed." -ForegroundColor Green
Write-Host "Run the app: .\RUN_SYNTHETIC.bat"
Write-Host "Start Codex: .\START_CODEX.ps1"
