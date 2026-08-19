$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$source = Get-Content -Raw -LiteralPath (Join-Path $repositoryRoot "src\__init__.py")
$match = [regex]::Match($source, '(?m)^__version__\s*=\s*"(?<version>\d+\.\d+\.\d+)"\s*$')
if (-not $match.Success) {
    throw "Could not read __version__ from src\__init__.py"
}
$match.Groups["version"].Value
