[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    throw 'Missing .venv. Run SETUP_DEVELOPMENT.ps1 first.'
}

Write-Host "[1/3] Compiling Python files" -ForegroundColor Cyan
& $Python -m compileall -q app.py src tests
if ($LASTEXITCODE -ne 0) { throw 'compileall failed.' }

Write-Host "[2/3] Running tests" -ForegroundColor Cyan
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { throw 'pytest failed.' }

Write-Host "[3/3] Running synthetic pipeline self-test" -ForegroundColor Cyan
& $Python app.py --self-test
if ($LASTEXITCODE -ne 0) { throw 'self-test failed.' }

Write-Host "All development checks passed." -ForegroundColor Green
