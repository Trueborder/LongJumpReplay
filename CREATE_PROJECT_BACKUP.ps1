[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupRoot = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'LongJumpReplay_Backups'
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$destination = Join-Path $backupRoot "LongJumpReplay-source-$stamp.zip"

$staging = Join-Path $env:TEMP "LongJumpReplay-backup-$stamp"
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
    $exclude = @('.venv', '__pycache__', '.pytest_cache', 'build', 'dist', 'release', 'cache', 'exports', 'evidence', 'logs', '.git')
    $args = @($PSScriptRoot, $staging, '/E', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/XD')
    $args += $exclude | ForEach-Object { Join-Path $PSScriptRoot $_ }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Robocopy failed with exit code $LASTEXITCODE" }
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $destination -Force
    Write-Host "Backup created: $destination" -ForegroundColor Green
}
finally {
    Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
}
