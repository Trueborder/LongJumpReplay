[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
if (Get-Command codex -ErrorAction SilentlyContinue) {
    Write-Host "Codex is already installed:" -ForegroundColor Green
    codex --version
    exit 0
}

Write-Host "This runs OpenAI's official Windows Codex installer from chatgpt.com." -ForegroundColor Cyan
$answer = Read-Host "Continue? Type YES"
if ($answer -cne 'YES') {
    Write-Host "Cancelled."
    exit 1
}

Invoke-Expression (Invoke-RestMethod 'https://chatgpt.com/codex/install.ps1')
Write-Host "Open a new PowerShell window, run 'codex', and sign in with ChatGPT." -ForegroundColor Green
