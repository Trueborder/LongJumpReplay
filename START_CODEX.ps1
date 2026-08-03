[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Write-Host "Codex CLI is not installed or is not on PATH." -ForegroundColor Red
    Write-Host "Official Windows install command:" -ForegroundColor Yellow
    Write-Host 'powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"'
    exit 1
}

Write-Host "Starting Codex in: $PSScriptRoot" -ForegroundColor Cyan
Write-Host "For the first session, paste the prompt from CODEX_FIRST_PROMPT.md." -ForegroundColor Yellow
& codex
