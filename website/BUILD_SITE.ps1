param([string]$Output = (Join-Path $PSScriptRoot 'dist'))
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path $Output | Out-Null
Get-ChildItem -LiteralPath $Output -Force | Remove-Item -Recurse -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'index.html'),(Join-Path $PSScriptRoot 'styles.css'),(Join-Path $PSScriptRoot 'overrides.css'),(Join-Path $PSScriptRoot 'script.js'),(Join-Path $PSScriptRoot 'installer-overrides.js'),(Join-Path $PSScriptRoot 'site.config.js') -Destination $Output
New-Item -ItemType Directory -Force -Path (Join-Path $Output 'assets'),(Join-Path $Output 'downloads'),(Join-Path $Output 'screenshots') | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot 'assets\long_jump_splash.png') -Destination (Join-Path $Output 'assets\long_jump_splash.png')
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\screenshots\dark-theme-2.3.png') -Destination (Join-Path $Output 'screenshots\dark-theme-2.3.png')
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\screenshots\light-theme-2.3.png') -Destination (Join-Path $Output 'screenshots\light-theme-2.3.png')
$outputStyles = Join-Path $Output 'styles.css'
Set-Content -LiteralPath $outputStyles -Value ((Get-Content -LiteralPath $outputStyles -Raw).Replace("../assets/long_jump_splash.png", "assets/long_jump_splash.png")) -Encoding utf8
$outputHtml = Join-Path $Output 'index.html'
$html = Get-Content -LiteralPath $outputHtml -Raw
$html = $html.Replace("../docs/screenshots/", "screenshots/")
$html = $html.Replace("downloads/LongJumpReplay-2.3.msi", "downloads/LongJumpReplay-Setup-2.3.exe")
$html = $html.Replace("Windows MSI installer", "Windows installer")
$html = $html.Replace("portable MSI installer", "Windows installer")
$html = $html.Replace("The MSI installs LongJumpReplay", "The installer places LongJumpReplay")
Set-Content -LiteralPath $outputHtml -Value $html -Encoding utf8
if (Test-Path (Join-Path $projectRoot 'release\LongJumpReplay-Setup-2.3.exe')) { Copy-Item -LiteralPath (Join-Path $projectRoot 'release\LongJumpReplay-Setup-2.3.exe') -Destination (Join-Path $Output 'downloads\LongJumpReplay-Setup-2.3.exe') }
if (Test-Path (Join-Path $projectRoot 'release\LongJumpReplay-Setup-2.3.exe.sha256')) { Copy-Item -LiteralPath (Join-Path $projectRoot 'release\LongJumpReplay-Setup-2.3.exe.sha256') -Destination (Join-Path $Output 'downloads\LongJumpReplay-Setup-2.3.exe.sha256') }
Write-Host "Website built to $Output"
