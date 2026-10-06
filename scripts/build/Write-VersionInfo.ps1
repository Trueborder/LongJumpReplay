$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$version = & (Join-Path $PSScriptRoot "Get-Version.ps1")
$parts = $version.Split('.') | ForEach-Object { [int]$_ }
$target = Join-Path $repositoryRoot "packaging\windows_version_info.txt"
$content = @"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($($parts[0]), $($parts[1]), $($parts[2]), 0),
    prodvers=($($parts[0]), $($parts[1]), $($parts[2]), 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'Novaryn Solutions'),
          StringStruct(u'FileDescription', u'LongJumpReplay'),
          StringStruct(u'FileVersion', u'$version'),
          StringStruct(u'InternalName', u'LongJumpReplay'),
          StringStruct(u'LegalCopyright', u'Copyright © 2026 Novaryn Solutions'),
          StringStruct(u'OriginalFilename', u'LongJumpReplay.exe'),
          StringStruct(u'ProductName', u'LongJumpReplay'),
          StringStruct(u'ProductVersion', u'$version')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@
Set-Content -LiteralPath $target -Value $content -Encoding UTF8
Write-Output $target
