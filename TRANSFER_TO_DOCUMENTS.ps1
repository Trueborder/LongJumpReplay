[CmdletBinding()]
param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'LongJumpReplay')
)

$ErrorActionPreference = 'Stop'
$Source = (Resolve-Path $PSScriptRoot).Path
$Destination = [System.IO.Path]::GetFullPath($Destination)

Write-Host "Long Jump Replay Codex transfer" -ForegroundColor Cyan
Write-Host "Source:      $Source"
Write-Host "Destination: $Destination"

if ($Source.TrimEnd('\') -ieq $Destination.TrimEnd('\')) {
    Write-Host "The project is already in the requested Documents folder." -ForegroundColor Green
    exit 0
}

if (Test-Path $Destination) {
    $items = @(Get-ChildItem -Force $Destination -ErrorAction SilentlyContinue)
    if ($items.Count -gt 0) {
        Write-Host "The destination already contains files." -ForegroundColor Yellow
        $choice = Read-Host "Type B to back it up and replace it, M to merge, or C to cancel"
        switch ($choice.ToUpperInvariant()) {
            'B' {
                $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
                $backupRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'LongJumpReplay_Backups'
                New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
                $backup = Join-Path $backupRoot "LongJumpReplay-before-transfer-$stamp"
                Move-Item -Path $Destination -Destination $backup
                Write-Host "Existing project moved to: $backup" -ForegroundColor Yellow
            }
            'M' { Write-Host "Merging into the existing folder." -ForegroundColor Yellow }
            default { Write-Host "Transfer cancelled."; exit 1 }
        }
    }
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$excludedDirs = @('.venv', 'venv', '__pycache__', '.pytest_cache', 'build', 'dist', 'release', 'cache', 'exports', 'evidence', 'logs', '.git')
$excludedFiles = @('*.pyc', '*.pyo', '*.log', 'SELF_TEST_SOURCE.txt', 'SELF_TEST_FROZEN.txt', 'SELF_TEST_SINGLE_EXE.txt')

$arguments = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
$arguments += '/XD'
$arguments += $excludedDirs | ForEach-Object { Join-Path $Source $_ }
$arguments += '/XF'
$arguments += $excludedFiles

& robocopy @arguments | Out-Null
$code = $LASTEXITCODE
if ($code -ge 8) {
    throw "Robocopy failed with exit code $code"
}

Write-Host "Transfer complete." -ForegroundColor Green
Write-Host "Next:" -ForegroundColor Cyan
Write-Host "  cd `"$Destination`""
Write-Host "  Set-ExecutionPolicy -Scope Process Bypass"
Write-Host "  .\SETUP_DEVELOPMENT.ps1"
