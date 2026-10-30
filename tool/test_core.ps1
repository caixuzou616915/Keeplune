param(
    [Parameter(Mandatory = $true)]
    [string]$FlutterRoot
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$flutter = Join-Path $FlutterRoot 'bin\flutter.bat'
if (-not (Test-Path $flutter -PathType Leaf)) {
    throw "Flutter SDK not found: $flutter"
}

$harness = Join-Path ([IO.Path]::GetTempPath()) ("offline-vault-verify-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $harness | Out-Null
$originalLocation = Get-Location
$utf8 = New-Object Text.UTF8Encoding($false)
try {
    # Resolve a host-only test graph; all application and test sources stay in the project.
    $manifest = Get-Content (Join-Path $root 'pubspec.yaml') -Raw
    $manifest = $manifest -replace '(?m)^name:[^\r\n]*', 'name: offline_vault_verification'
    $manifest = $manifest -replace '(?m)^  pdfrx:[^\r\n]*\r?\n', ''
    [IO.File]::WriteAllText((Join-Path $harness 'pubspec.yaml'), $manifest, $utf8)
    Copy-Item (Join-Path $root 'pubspec.lock') (Join-Path $harness 'pubspec.lock')
    Set-Location $harness
    & $flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'Verification dependencies could not be resolved.' }

    $configPath = Join-Path $harness '.dart_tool\package_config.json'
    $config = Get-Content $configPath -Raw | ConvertFrom-Json
    $config.packages += [PSCustomObject]@{
        name = 'offline_vault'
        rootUri = ([Uri]($root + '\')).AbsoluteUri
        packageUri = 'lib/'
        languageVersion = '3.13'
    }
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 20), $utf8)
    $tests = Get-ChildItem (Join-Path $root 'test') -Filter '*_test.dart' -File |
        ForEach-Object { $_.FullName }
    Write-Output 'Testing original sources. Native PDF rendering and platform channels are not exercised.'
    & $flutter test --no-pub --packages $configPath --reporter expanded @tests
    $result = $LASTEXITCODE
} finally {
    Set-Location $originalLocation
    Remove-Item -LiteralPath $harness -Recurse -Force
}
exit $result
