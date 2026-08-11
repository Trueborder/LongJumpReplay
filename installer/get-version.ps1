[CmdletBinding()]
param([switch]$Label)

$source = Join-Path $PSScriptRoot "..\src\__init__.py"
$text = Get-Content -LiteralPath $source -Raw
if ($text -notmatch '__version__\s*=\s*["'']([^"'']+)["'']') {
    throw "Could not read __version__ from $source"
}

$fullVersion = $Matches[1]
if ($Label) {
    $parts = $fullVersion.Split('.')
    if ($parts.Count -ge 2) {
        Write-Output ($parts[0] + "." + $parts[1])
    }
    else {
        Write-Output $fullVersion
    }
}
else {
    Write-Output $fullVersion
}
