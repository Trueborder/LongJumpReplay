param(
    [Parameter(Mandatory = $true)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Version,
    [string]$Bucket = "longjumpreplay"
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$privateKey = Join-Path $repositoryRoot "packaging\.update-signing-private.pem"
$wrangler = Join-Path $repositoryRoot "licensing-api\node_modules\.bin\wrangler.cmd"
$temporary = Join-Path $env:TEMP ("LongJumpReplay-rollback-" + [guid]::NewGuid().ToString("N"))
$installerName = "LongJumpReplay-Setup-$Version.exe"

function Invoke-Wrangler([string[]]$Arguments) {
    & $wrangler @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Wrangler failed: $($Arguments -join ' ')" }
}

try {
    New-Item -ItemType Directory -Path $temporary | Out-Null
    $installer = Join-Path $temporary $installerName
    $manifest = Join-Path $temporary "manifest.json"
    Invoke-Wrangler @("r2", "object", "get", "$Bucket/releases/$Version/$installerName", "--file", $installer, "--remote")
    Invoke-Wrangler @("r2", "object", "get", "$Bucket/releases/$Version/manifest.json", "--file", $manifest, "--remote")
    & node (Join-Path $repositoryRoot "scripts\release\verify-update-manifest.mjs") --manifest $manifest --installer $installer --private-key $privateKey
    if ($LASTEXITCODE -ne 0) { throw "Archived release verification failed." }
    Invoke-Wrangler @("r2", "object", "put", "$Bucket/LJR_setup.exe", "--file", $installer, "--remote", "--content-type", "application/x-msdownload", "--content-disposition", "attachment; filename=`"$installerName`"", "--cache-control", "no-cache, max-age=0, must-revalidate")
    Invoke-Wrangler @("r2", "object", "put", "$Bucket/latest.json", "--file", $manifest, "--remote", "--content-type", "application/json; charset=utf-8", "--cache-control", "no-store")
    Write-Host "Rolled the stable channel back to LongJumpReplay $Version"
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
