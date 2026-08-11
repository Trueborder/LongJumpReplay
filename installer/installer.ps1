[CmdletBinding()]
param(
    [string]$PayloadZip = (Join-Path $PSScriptRoot "payload.zip"),
    [string]$ExpectedVersion = "",
    [string]$TargetDirectory = (Join-Path $env:ProgramFiles "LongJumpReplay")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param(
        [int]$Number,
        [int]$Total,
        [string]$Message
    )

    Write-Host "[$Number/$Total] $Message" -ForegroundColor Cyan
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Normalize-Version {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    return $Value.Trim().TrimStart("v")
}

function Get-FullPath {
    param([string]$Path)

    return [IO.Path]::GetFullPath($Path)
}

function Assert-SafeInstallTarget {
    param([string]$Path)

    $programFiles = [Environment]::GetFolderPath("ProgramFiles")
    if ([string]::IsNullOrWhiteSpace($programFiles)) {
        $programFiles = $env:ProgramFiles
    }

    if ([string]::IsNullOrWhiteSpace($programFiles)) {
        throw "The Windows Program Files directory could not be determined."
    }

    $programFiles = (Get-FullPath $programFiles).TrimEnd("\")
    $target = (Get-FullPath $Path).TrimEnd("\")
    $allowedPrefix = "$programFiles\"

    if ($target -eq $programFiles -or -not $target.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to install outside Program Files: $target"
    }

    if ([IO.Path]::GetFileName($target) -ne "LongJumpReplay") {
        throw "Refusing to overwrite an unexpected installation directory: $target"
    }

    return $target
}

function Assert-ZipEntriesAreSafe {
    param(
        [string]$ZipPath,
        [string]$ExtractionDirectory
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($ZipPath)
    $root = (Get-FullPath $ExtractionDirectory).TrimEnd("\") + "\"

    try {
        foreach ($entry in $archive.Entries) {
            $candidate = Get-FullPath (Join-Path $ExtractionDirectory $entry.FullName)
            if (-not $candidate.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
                throw "The payload contains an unsafe archive path: $($entry.FullName)"
            }
        }
    }
    finally {
        $archive.Dispose()
    }
}

function Start-ElevatedInstaller {
    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-PayloadZip", $PayloadZip,
        "-ExpectedVersion", $ExpectedVersion,
        "-TargetDirectory", $TargetDirectory
    )

    try {
        $elevated = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $arguments -Wait -PassThru -ErrorAction Stop
        exit $elevated.ExitCode
    }
    catch {
        Write-Host "Administrator approval was cancelled or could not be requested." -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
}

$workDirectory = $null
$stagedInstall = $null
$backupInstall = $null
$oldInstallMoved = $false
$newInstallMoved = $false

try {
    Write-Step 1 5 "Checking administrator rights..."
    if (-not (Test-IsAdministrator)) {
        Write-Host "Administrator rights are required. Requesting elevation..." -ForegroundColor Yellow
        Start-ElevatedInstaller
    }
    Write-Host "Administrator rights confirmed." -ForegroundColor Green

    Write-Step 2 5 "Preparing target directory..."
    $safeTarget = Assert-SafeInstallTarget $TargetDirectory
    $targetParent = Split-Path -Parent $safeTarget
    if (-not (Test-Path -LiteralPath $targetParent)) {
        New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
    }

    if (Test-Path -LiteralPath $safeTarget) {
        if (-not (Get-Item -LiteralPath $safeTarget).PSIsContainer) {
            throw "The installation target exists but is not a directory: $safeTarget"
        }
        Write-Host "Existing application files will be replaced safely." -ForegroundColor Gray
    }
    else {
        Write-Host "The application directory will be created." -ForegroundColor Gray
    }

    Write-Step 3 5 "Extracting and validating the application payload..."
    $PayloadZip = Get-FullPath $PayloadZip
    if (-not (Test-Path -LiteralPath $PayloadZip -PathType Leaf)) {
        throw "The embedded application ZIP was not found: $PayloadZip"
    }

    $workDirectory = Join-Path ([IO.Path]::GetTempPath()) ("LongJumpReplay-Install-" + [Guid]::NewGuid().ToString("N"))
    $extractionDirectory = Join-Path $workDirectory "extracted"
    New-Item -ItemType Directory -Path $extractionDirectory -Force | Out-Null
    Assert-ZipEntriesAreSafe -ZipPath $PayloadZip -ExtractionDirectory $extractionDirectory
    Expand-Archive -LiteralPath $PayloadZip -DestinationPath $extractionDirectory -Force

    $manifestPath = Join-Path $extractionDirectory "VERSION.txt"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "The payload version manifest is missing."
    }

    $payloadVersion = Normalize-Version (Get-Content -LiteralPath $manifestPath -Raw)
    $expected = Normalize-Version $ExpectedVersion
    if ([string]::IsNullOrWhiteSpace($payloadVersion)) {
        throw "The payload version manifest is empty."
    }
    if (-not [string]::IsNullOrWhiteSpace($expected) -and $payloadVersion -ne $expected) {
        throw "Payload version mismatch. Expected $expected but found $payloadVersion."
    }

    $applicationSource = Join-Path $extractionDirectory "application"
    $mainExecutable = Join-Path $applicationSource "LongJumpReplay.exe"
    if (-not (Test-Path -LiteralPath $mainExecutable -PathType Leaf)) {
        throw "The payload does not contain application\LongJumpReplay.exe."
    }

    $stagedInstall = Join-Path $targetParent (".LongJumpReplay-stage-" + [Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $stagedInstall -Force | Out-Null
    Get-ChildItem -LiteralPath $applicationSource -Force | Copy-Item -Destination $stagedInstall -Recurse -Force

    $runningApp = Get-Process -Name "LongJumpReplay" -ErrorAction SilentlyContinue
    if ($null -ne $runningApp) {
        throw "LongJumpReplay is currently running. Close it and run the installer again."
    }

    $backupInstall = Join-Path $targetParent (".LongJumpReplay-backup-" + [Guid]::NewGuid().ToString("N"))
    if (Test-Path -LiteralPath $safeTarget) {
        Move-Item -LiteralPath $safeTarget -Destination $backupInstall -Force
        $oldInstallMoved = $true
    }

    try {
        Move-Item -LiteralPath $stagedInstall -Destination $safeTarget -Force
        $newInstallMoved = $true
    }
    catch {
        if ($oldInstallMoved -and (Test-Path -LiteralPath $backupInstall) -and -not (Test-Path -LiteralPath $safeTarget)) {
            Move-Item -LiteralPath $backupInstall -Destination $safeTarget -Force
            $oldInstallMoved = $false
        }
        throw
    }

    if ($oldInstallMoved -and (Test-Path -LiteralPath $backupInstall)) {
        try {
            Remove-Item -LiteralPath $backupInstall -Recurse -Force
        }
        catch {
            Write-Host "Warning: the temporary previous installation backup could not be removed: $backupInstall" -ForegroundColor Yellow
        }
    }
    Write-Host "Installed LongJumpReplay $payloadVersion to $safeTarget." -ForegroundColor Green

    Write-Step 4 5 "Creating the all-users desktop shortcut..."
    $desktopDirectory = [Environment]::GetFolderPath("CommonDesktopDirectory")
    if ([string]::IsNullOrWhiteSpace($desktopDirectory) -or -not (Test-Path -LiteralPath $desktopDirectory)) {
        $desktopDirectory = Join-Path $env:PUBLIC "Desktop"
    }
    New-Item -ItemType Directory -Path $desktopDirectory -Force | Out-Null

    $shortcutPath = Join-Path $desktopDirectory "Long Jump Replay.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $safeTarget "LongJumpReplay.exe"
    $shortcut.WorkingDirectory = $safeTarget
    $shortcut.IconLocation = "$($shortcut.TargetPath),0"
    $shortcut.Description = "Long Jump Replay"
    $shortcut.Save()

    Write-Step 5 5 "Installation completed successfully."
    Write-Host "Shortcut: $shortcutPath" -ForegroundColor Green
    Write-Host "Installed version: $payloadVersion" -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "INSTALLATION FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    if ($null -ne $stagedInstall -and (Test-Path -LiteralPath $stagedInstall)) {
        Remove-Item -LiteralPath $stagedInstall -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $workDirectory -and (Test-Path -LiteralPath $workDirectory)) {
        Remove-Item -LiteralPath $workDirectory -Recurse -Force -ErrorAction SilentlyContinue
    }
}
