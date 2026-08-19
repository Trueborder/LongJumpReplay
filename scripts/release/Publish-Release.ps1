param(
    [string]$Bucket = "longjumpreplay",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$version = & (Join-Path $repositoryRoot "scripts\build\Get-Version.ps1")
$installerName = "LongJumpReplay-Setup-$version.exe"
$installer = Join-Path $repositoryRoot "release\$installerName"
$manifest = Join-Path $repositoryRoot "release\manifest.json"
$privateKey = Join-Path $repositoryRoot "packaging\.update-signing-private.pem"
$wrangler = Join-Path $repositoryRoot "licensing-api\node_modules\.bin\wrangler.cmd"
$verifyRoot = Join-Path $env:TEMP ("LongJumpReplay-publish-" + [guid]::NewGuid().ToString("N"))

function Invoke-Wrangler([string[]]$Arguments) {
    & $wrangler @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Wrangler failed: $($Arguments -join ' ')" }
}

function Assert-SameHash([string]$Expected, [string]$Actual) {
    $left = (Get-FileHash -LiteralPath $Expected -Algorithm SHA256).Hash
    $right = (Get-FileHash -LiteralPath $Actual -Algorithm SHA256).Hash
    if ($left -ne $right) { throw "Remote verification failed for $Actual" }
}

try {
    if (-not (Test-Path -LiteralPath $privateKey)) {
        throw "Update signing key is missing: $privateKey. Restore the backed-up production key."
    }
    if (-not (Test-Path -LiteralPath $wrangler)) {
        throw "Wrangler is missing. Run npm install in licensing-api first."
    }
    if (-not $SkipBuild) {
        & (Join-Path $repositoryRoot "scripts\build\BUILD_INSTALLER.bat") --no-pause
        if ($LASTEXITCODE -ne 0) { throw "Customer installer build failed." }
    }
    if (-not (Test-Path -LiteralPath $installer)) { throw "Installer is missing: $installer" }

    & node (Join-Path $repositoryRoot "scripts\release\make-update-manifest.mjs") `
        --version $version --installer $installer --private-key $privateKey `
        --changelog (Join-Path $repositoryRoot "CHANGELOG.md") --output $manifest
    if ($LASTEXITCODE -ne 0) { throw "Manifest generation failed." }
    & node (Join-Path $repositoryRoot "scripts\release\verify-update-manifest.mjs") `
        --manifest $manifest --installer $installer --private-key $privateKey
    if ($LASTEXITCODE -ne 0) { throw "Local release verification failed." }

    New-Item -ItemType Directory -Path $verifyRoot | Out-Null
    Invoke-Wrangler @("whoami")
    $versionPrefix = "releases/$version"
    $versionedKey = "$versionPrefix/$installerName"
    $archivedManifestKey = "$versionPrefix/manifest.json"

    Invoke-Wrangler @("r2", "object", "put", "$Bucket/$versionedKey", "--file", $installer, "--remote", "--content-type", "application/x-msdownload", "--content-disposition", "attachment; filename=`"$installerName`"", "--cache-control", "public, max-age=31536000, immutable")
    Invoke-Wrangler @("r2", "object", "put", "$Bucket/$archivedManifestKey", "--file", $manifest, "--remote", "--content-type", "application/json; charset=utf-8", "--cache-control", "public, max-age=31536000, immutable")

    $remoteVersioned = Join-Path $verifyRoot $installerName
    Invoke-Wrangler @("r2", "object", "get", "$Bucket/$versionedKey", "--file", $remoteVersioned, "--remote")
    Assert-SameHash $installer $remoteVersioned

    Invoke-Wrangler @("r2", "object", "put", "$Bucket/LJR_setup.exe", "--file", $installer, "--remote", "--content-type", "application/x-msdownload", "--content-disposition", "attachment; filename=`"$installerName`"", "--cache-control", "no-cache, max-age=0, must-revalidate")
    $remoteStable = Join-Path $verifyRoot "LJR_setup.exe"
    Invoke-Wrangler @("r2", "object", "get", "$Bucket/LJR_setup.exe", "--file", $remoteStable, "--remote")
    Assert-SameHash $installer $remoteStable

    Invoke-Wrangler @("r2", "object", "put", "$Bucket/latest.json", "--file", $manifest, "--remote", "--content-type", "application/json; charset=utf-8", "--cache-control", "no-store")
    $remoteLatest = Join-Path $verifyRoot "latest.json"
    Invoke-Wrangler @("r2", "object", "get", "$Bucket/latest.json", "--file", $remoteLatest, "--remote")
    Assert-SameHash $manifest $remoteLatest

    & node (Join-Path $repositoryRoot "scripts\release\verify-update-manifest.mjs") `
        --manifest $remoteLatest --installer $remoteVersioned --private-key $privateKey
    if ($LASTEXITCODE -ne 0) { throw "Published release verification failed." }
    Write-Host "Published and verified LongJumpReplay $version"
    Write-Host "https://files.tomaspisar.cz/releases/$version/$installerName"
} finally {
    if (Test-Path -LiteralPath $verifyRoot) {
        Remove-Item -LiteralPath $verifyRoot -Recurse -Force
    }
}
