[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$VersionFull = "",
    [string]$VersionLabel = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FullPath {
    param([string]$Path)
    return [IO.Path]::GetFullPath($Path)
}

$ProjectRoot = Get-FullPath $ProjectRoot
$versionSource = Join-Path $ProjectRoot "src\__init__.py"
if ([string]::IsNullOrWhiteSpace($VersionFull) -or [string]::IsNullOrWhiteSpace($VersionLabel)) {
    $versionText = Get-Content -LiteralPath $versionSource -Raw
    if ($versionText -notmatch '__version__\s*=\s*["'']([^"'']+)["'']') {
        throw "Could not read __version__ from $versionSource"
    }
    $VersionFull = $Matches[1]
    $versionParts = $VersionFull.Split('.')
    if ($versionParts.Count -ge 2) {
        $VersionLabel = $versionParts[0] + "." + $versionParts[1]
    }
    else {
        $VersionLabel = $VersionFull
    }
}
$releaseDirectory = Join-Path $ProjectRoot "release"
$portableDirectory = Join-Path $releaseDirectory "LongJumpReplay"
$portableExecutable = Join-Path $portableDirectory "LongJumpReplay.exe"
$installerScript = Join-Path $ProjectRoot "installer\installer.ps1"
$buildDirectory = Join-Path $ProjectRoot "build\iexpress"
$payloadDirectory = Join-Path $buildDirectory "payload"
$applicationDirectory = Join-Path $payloadDirectory "application"
$payloadZip = Join-Path $buildDirectory "LongJumpReplay-$VersionLabel-Windows-x64.zip"
$sedPath = Join-Path $buildDirectory "LongJumpReplay-Setup-$VersionLabel.sed"
$outputInstaller = Join-Path $releaseDirectory "LongJumpReplay-Setup-$VersionLabel.exe"
$hashPath = "$outputInstaller.sha256"
$iexpress = Join-Path $env:WINDIR "System32\iexpress.exe"

try {
    Write-Host "Preparing native Windows installer for LongJumpReplay $VersionFull..." -ForegroundColor Cyan

    if (-not (Test-Path -LiteralPath $iexpress -PathType Leaf)) {
        throw "IExpress was not found at $iexpress. Enable the Windows IExpress component or run on Windows."
    }
    if (-not (Test-Path -LiteralPath $portableExecutable -PathType Leaf)) {
        throw "The portable payload is missing: $portableExecutable"
    }
    if (-not (Test-Path -LiteralPath $installerScript -PathType Leaf)) {
        throw "The deployment script is missing: $installerScript"
    }

    if (Test-Path -LiteralPath $buildDirectory) {
        Remove-Item -LiteralPath $buildDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $applicationDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null

    Get-ChildItem -LiteralPath $portableDirectory -Force | Copy-Item -Destination $applicationDirectory -Recurse -Force
    Set-Content -LiteralPath (Join-Path $payloadDirectory "VERSION.txt") -Value $VersionFull -Encoding UTF8
    Copy-Item -LiteralPath $installerScript -Destination (Join-Path $buildDirectory "installer.ps1") -Force

    Compress-Archive -Path (Join-Path $payloadDirectory "*") -DestinationPath $payloadZip -CompressionLevel Optimal -Force

    $targetName = $outputInstaller
    $sourceRoot = $buildDirectory
    $sedContent = @"
[Version]
Class=IEXPRESS
SEDVersion=3

[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=1
UseLongFileName=1
InsideCompressed=1
CAB_Fixed_Size=0
CAB_Resv_CodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=%DisplayLicense%
FinishMessage=%FinishMessage%
TargetName=%TargetName%
FriendlyName=%FriendlyName%
AppLaunched=%AppLaunched%
PostInstallCmd=%PostInstallCmd%
AdminQuietInstCmd=%AdminQuietInstCmd%
UserQuietInstCmd=%UserQuietInstCmd%
SourceFiles=SourceFiles

[SourceFiles]
SourceFiles0=$sourceRoot\

[SourceFiles0]
%FILE0%=
%FILE1%=

[Strings]
FILE0="installer.ps1"
FILE1="LongJumpReplay-$VersionLabel-Windows-x64.zip"
InstallPrompt=Preparing Long Jump Replay $VersionLabel. Administrator approval is required.
DisplayLicense=
FinishMessage=Long Jump Replay $VersionLabel was installed successfully.
TargetName="$targetName"
FriendlyName=Long Jump Replay $VersionLabel Installer
AppLaunched="PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File installer.ps1 -PayloadZip LongJumpReplay-$VersionLabel-Windows-x64.zip -ExpectedVersion $VersionFull"
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
"@

    Set-Content -LiteralPath $sedPath -Value $sedContent -Encoding ASCII
    Write-Host "Embedding the application ZIP with IExpress..." -ForegroundColor Cyan
    $process = Start-Process -FilePath $iexpress -ArgumentList "/N", $sedPath -Wait -PassThru -NoNewWindow
    if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $outputInstaller -PathType Leaf)) {
        throw "IExpress failed to create the installer (exit code $($process.ExitCode))."
    }

    $hash = (Get-FileHash -LiteralPath $outputInstaller -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $hashPath -Value "$hash  $(Split-Path -Leaf $outputInstaller)" -Encoding ASCII

    Write-Host "INSTALLER BUILD COMPLETE" -ForegroundColor Green
    Write-Host "Installer: $outputInstaller" -ForegroundColor Green
    Write-Host "Checksum:  $hashPath" -ForegroundColor Green
}
catch {
    Write-Error $_.Exception.Message
    exit 1
}
